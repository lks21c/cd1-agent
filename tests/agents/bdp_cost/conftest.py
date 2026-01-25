"""
BDP Compact Agent Test Fixtures.

LocalStack 및 Mock 기반 테스트 픽스처 제공.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Generator, List

import pytest


# ============================================================================
# LocalStack Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def bdp_localstack_endpoint() -> str:
    """LocalStack endpoint URL."""
    return os.getenv("LOCALSTACK_ENDPOINT", "http://localhost:4566")


@pytest.fixture(scope="session")
def bdp_tables_created(localstack_available: bool, bdp_localstack_endpoint: str) -> bool:
    """BDP Compact DynamoDB 테이블 생성 확인.

    Returns:
        테이블 생성 성공 여부
    """
    if not localstack_available:
        return False

    try:
        import boto3

        dynamodb = boto3.client(
            "dynamodb",
            endpoint_url=bdp_localstack_endpoint,
            region_name="ap-northeast-2",
        )

        tables = dynamodb.list_tables()["TableNames"]
        required_tables = ["bdp-cost-history", "bdp-anomaly-tracking"]
        missing_tables = [t for t in required_tables if t not in tables]

        if missing_tables:
            for table_name in missing_tables:
                try:
                    dynamodb.create_table(
                        TableName=table_name,
                        AttributeDefinitions=[
                            {"AttributeName": "pk", "AttributeType": "S"},
                            {"AttributeName": "sk", "AttributeType": "S"},
                        ],
                        KeySchema=[
                            {"AttributeName": "pk", "KeyType": "HASH"},
                            {"AttributeName": "sk", "KeyType": "RANGE"},
                        ],
                        BillingMode="PAY_PER_REQUEST",
                    )
                except dynamodb.exceptions.ResourceInUseException:
                    pass

        return True

    except Exception as e:
        pytest.skip(f"Failed to create BDP tables: {e}")
        return False


@pytest.fixture
def skip_without_bdp_tables(bdp_tables_created: bool):
    """BDP 테이블 없으면 테스트 스킵."""
    if not bdp_tables_created:
        pytest.skip("BDP DynamoDB tables are not available")


# ============================================================================
# Mock Data Fixtures
# ============================================================================


@pytest.fixture
def mock_account_id():
    """Mock 계정 ID."""
    return "111111111111"


@pytest.fixture
def mock_account_name():
    """Mock 계정 이름."""
    return "test-account"


@pytest.fixture
def mock_service_cost_data(mock_account_id, mock_account_name):
    """Mock 서비스 비용 데이터."""
    from src.agents.bdp_cost.services.cost_explorer_provider import ServiceCostData

    end_date = datetime.utcnow()
    days = 14

    services: List[ServiceCostData] = []

    # Athena - 정상 패턴
    athena_costs = [250000 + (i * 1000) for i in range(days)]
    athena_timestamps = [
        (end_date - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
        for i in range(days)
    ]
    services.append(
        ServiceCostData(
            service_name="Amazon Athena",
            account_id=mock_account_id,
            account_name=mock_account_name,
            current_cost=athena_costs[-1],
            historical_costs=athena_costs,
            timestamps=athena_timestamps,
            currency="KRW",
        )
    )

    # Lambda - 정상 패턴
    lambda_costs = [80000 + (i % 5) * 2000 for i in range(days)]
    services.append(
        ServiceCostData(
            service_name="AWS Lambda",
            account_id=mock_account_id,
            account_name=mock_account_name,
            current_cost=lambda_costs[-1],
            historical_costs=lambda_costs,
            timestamps=athena_timestamps,
            currency="KRW",
        )
    )

    return services


@pytest.fixture
def mock_spike_data(mock_account_id, mock_account_name):
    """스파이크가 포함된 Mock 데이터."""
    from src.agents.bdp_cost.services.cost_explorer_provider import ServiceCostData

    end_date = datetime.utcnow()
    days = 14
    timestamps = [
        (end_date - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
        for i in range(days)
    ]

    # Athena - 마지막 3일 스파이크
    athena_costs = [250000] * 11 + [350000, 450000, 580000]

    return [
        ServiceCostData(
            service_name="Amazon Athena",
            account_id=mock_account_id,
            account_name=mock_account_name,
            current_cost=580000,
            historical_costs=athena_costs,
            timestamps=timestamps,
            currency="KRW",
        )
    ]


# ============================================================================
# Provider Fixtures
# ============================================================================


@pytest.fixture
def mock_provider(mock_service_cost_data, mock_account_id, mock_account_name):
    """Mock Cost Explorer Provider."""
    from src.agents.bdp_cost.services.cost_explorer_provider import MockCostExplorerProvider

    return MockCostExplorerProvider(
        account_id=mock_account_id,
        account_name=mock_account_name,
        mock_data=mock_service_cost_data,
    )


@pytest.fixture
def mock_spike_provider(mock_spike_data, mock_account_id, mock_account_name):
    """스파이크 데이터가 포함된 Mock Provider."""
    from src.agents.bdp_cost.services.cost_explorer_provider import MockCostExplorerProvider

    return MockCostExplorerProvider(
        account_id=mock_account_id,
        account_name=mock_account_name,
        mock_data=mock_spike_data,
    )


# ============================================================================
# Handler Fixtures
# ============================================================================


@pytest.fixture
def bdp_handler_mock():
    """Mock 모드 BDP Handler."""
    original_env = {}
    env_vars = {
        "BDP_PROVIDER": "mock",
        "EVENT_PROVIDER": "mock",
        "RDS_PROVIDER": "mock",
        "BDP_SENSITIVITY": "0.7",
        "BDP_CURRENCY": "KRW",
    }

    for key, value in env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        from src.agents.bdp_cost.handler import BDPCostHandler

        handler = BDPCostHandler()
        yield handler
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def localstack_bdp_handler(
    localstack_available: bool,
    bdp_localstack_endpoint: str,
    bdp_tables_created: bool,
) -> Generator[Any, None, None]:
    """LocalStack 모드 BDP Handler."""
    if not localstack_available:
        pytest.skip("LocalStack is not available")

    if not bdp_tables_created:
        pytest.skip("BDP tables are not created")

    original_env = {}
    env_vars = {
        "BDP_PROVIDER": "localstack",
        "LOCALSTACK_ENDPOINT": bdp_localstack_endpoint,
        "AWS_REGION": "ap-northeast-2",
        "EVENT_PROVIDER": "localstack",
        "RDS_PROVIDER": "mock",
    }

    for key, value in env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        from src.agents.bdp_cost.handler import BDPCostHandler

        handler = BDPCostHandler()
        yield handler
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# ============================================================================
# Baseline Data Injection
# ============================================================================


@pytest.fixture
def inject_bdp_baseline(
    localstack_available: bool,
    bdp_localstack_endpoint: str,
    bdp_tables_created: bool,
) -> Generator[bool, None, None]:
    """LocalStack에 기준 비용 데이터 주입."""
    if not localstack_available or not bdp_tables_created:
        yield False
        return

    import boto3

    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=bdp_localstack_endpoint,
        region_name="ap-northeast-2",
    )

    services = [
        ("Amazon Athena", 250000, 15),
        ("AWS Lambda", 80000, 10),
        ("Amazon S3", 120000, 8),
    ]

    # Single account architecture - only one account
    account_id = "111111111111"
    account_name = "test-account"

    now = datetime.utcnow()

    try:
        for service_name, base_cost, variance_pct in services:
            for day in range(14):
                date = now - timedelta(days=day)
                date_str = date.strftime("%Y-%m-%d")

                import random
                variance = base_cost * variance_pct / 100
                cost = base_cost + random.uniform(-variance, variance)

                dynamodb.put_item(
                    TableName="bdp-cost-history",
                    Item={
                        "pk": {"S": f"ACCOUNT#{account_id}#SERVICE#{service_name}"},
                        "sk": {"S": f"DATE#{date_str}"},
                        "account_id": {"S": account_id},
                        "account_name": {"S": account_name},
                        "service_name": {"S": service_name},
                        "cost": {"N": str(round(cost, 2))},
                        "currency": {"S": "KRW"},
                        "timestamp": {"S": f"{date_str}T23:59:59Z"},
                    },
                )

        yield True
    except Exception:
        yield False


# ============================================================================
# Scenario Test Fixtures
# ============================================================================


@pytest.fixture
def all_scenarios():
    """모든 테스트 시나리오 정의."""
    from tests.agents.bdp_cost.scenarios.scenario_factory import ScenarioFactory

    return ScenarioFactory.get_all_scenarios()


@pytest.fixture
def scenario_cost_data(all_scenarios):
    """모든 시나리오에 대한 ServiceCostData 생성."""
    from tests.agents.bdp_cost.scenarios.scenario_factory import ScenarioFactory

    return [ScenarioFactory.generate_cost_data(s) for s in all_scenarios]


@pytest.fixture
def scenario_detector():
    """시나리오 테스트용 탐지기."""
    from src.agents.bdp_cost.services.anomaly_detector import CostDriftDetector

    return CostDriftDetector(sensitivity=0.7)


@pytest.fixture
def scenario_summary_generator():
    """시나리오 테스트용 요약 생성기."""
    from src.agents.bdp_cost.services.summary_generator import SummaryGenerator

    return SummaryGenerator(currency="KRW", enable_chart=True)


@pytest.fixture
def scenario_chart_generator():
    """시나리오 테스트용 차트 생성기."""
    from src.agents.bdp_cost.services.chart_generator import CostTrendChartGenerator

    return CostTrendChartGenerator()


@pytest.fixture
def scenario_report_generator():
    """시나리오 테스트용 HTML 리포트 생성기."""
    from src.agents.bdp_cost.services.html_report_generator import HTMLReportGenerator

    return HTMLReportGenerator()
