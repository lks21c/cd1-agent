"""
Cost Agent Test Fixtures.

Provides LocalStack-specific fixtures for Cost Agent testing.
"""

import os
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, Generator

import pytest


# ============================================================================
# LocalStack Cost Agent Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def cost_localstack_endpoint() -> str:
    """Get LocalStack endpoint URL for cost agent tests."""
    return os.getenv("LOCALSTACK_ENDPOINT", "http://localhost:4566")


@pytest.fixture(scope="session")
def cost_tables_created(localstack_available: bool, cost_localstack_endpoint: str) -> bool:
    """Ensure cost-specific DynamoDB tables are created.

    Returns True if tables are created successfully or already exist.
    """
    if not localstack_available:
        return False

    try:
        import boto3

        dynamodb = boto3.client(
            "dynamodb",
            endpoint_url=cost_localstack_endpoint,
            region_name="ap-northeast-2",
        )

        # Check if tables exist
        tables = dynamodb.list_tables()["TableNames"]

        required_tables = ["cost-service-history", "cost-anomaly-tracking", "cost-forecast-data"]
        missing_tables = [t for t in required_tables if t not in tables]

        if missing_tables:
            # Run the init script to create tables
            script_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "..",
                "infra",
                "localstack",
                "cost",
                "init",
                "03-create-cost-tables.sh",
            )
            if os.path.exists(script_path):
                env = os.environ.copy()
                env["LOCALSTACK_ENDPOINT"] = cost_localstack_endpoint
                subprocess.run(["bash", script_path], env=env, check=True)
            else:
                # Create tables directly
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
        pytest.skip(f"Failed to create cost tables: {e}")
        return False


@pytest.fixture
def skip_without_cost_tables(cost_tables_created: bool):
    """Skip test if cost tables are not available."""
    if not cost_tables_created:
        pytest.skip("Cost DynamoDB tables are not available")


@pytest.fixture
def localstack_cost_handler(
    localstack_available: bool,
    cost_localstack_endpoint: str,
    cost_tables_created: bool,
) -> Generator[Any, None, None]:
    """Create CostDetectionHandler configured for LocalStack.

    Automatically skips if LocalStack is not available.
    """
    if not localstack_available:
        pytest.skip("LocalStack is not available")

    if not cost_tables_created:
        pytest.skip("Cost tables are not created")

    # Set environment variables for LocalStack
    original_env = {}
    env_vars = {
        "COST_PROVIDER": "localstack",
        "LOCALSTACK_ENDPOINT": cost_localstack_endpoint,
        "AWS_REGION": "ap-northeast-2",
        "COST_HISTORY_TABLE": "cost-service-history",
        "COST_ANOMALY_TABLE": "cost-anomaly-tracking",
        "AWS_PROVIDER": "localstack",
    }

    for key, value in env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        from src.agents.cost.handler import CostDetectionHandler

        handler = CostDetectionHandler()
        yield handler
    finally:
        # Restore original environment
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def localstack_cost_client(
    localstack_available: bool,
    cost_localstack_endpoint: str,
    cost_tables_created: bool,
) -> Generator[Any, None, None]:
    """Create CostExplorerClient configured for LocalStack."""
    if not localstack_available:
        pytest.skip("LocalStack is not available")

    if not cost_tables_created:
        pytest.skip("Cost tables are not created")

    from src.agents.cost.services.cost_explorer_client import CostExplorerClient

    client = CostExplorerClient(
        provider_type="localstack",
        endpoint_url=cost_localstack_endpoint,
    )
    yield client


@pytest.fixture
def inject_cost_baseline(
    localstack_available: bool,
    cost_localstack_endpoint: str,
    cost_tables_created: bool,
) -> Generator[bool, None, None]:
    """Inject baseline cost data for testing.

    Returns True if data was injected successfully.
    """
    if not localstack_available or not cost_tables_created:
        yield False
        return

    # Run the baseline injection script
    script_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "infra",
        "localstack",
        "cost",
        "init",
        "04-inject-cost-baseline.sh",
    )

    if os.path.exists(script_path):
        env = os.environ.copy()
        env["LOCALSTACK_ENDPOINT"] = cost_localstack_endpoint
        env["COST_BASELINE_DAYS"] = "14"  # Shorter period for tests
        result = subprocess.run(["bash", script_path], env=env, capture_output=True)
        yield result.returncode == 0
    else:
        # Inject directly via boto3
        yield _inject_baseline_directly(cost_localstack_endpoint)


def _inject_baseline_directly(endpoint_url: str) -> bool:
    """Inject baseline data directly via boto3."""
    import boto3

    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=endpoint_url,
        region_name="ap-northeast-2",
    )

    services = [
        ("AWS Lambda", 60, 20),
        ("Amazon EC2", 200, 10),
        ("Amazon RDS", 150, 7),
        ("Amazon S3", 30, 17),
        ("Amazon DynamoDB", 80, 13),
        ("AWS CloudWatch", 20, 25),
        ("Amazon API Gateway", 40, 25),
    ]

    now = datetime.utcnow()

    for service_name, base_cost, variance_pct in services:
        for day in range(14):
            date = now - timedelta(days=day)
            date_str = date.strftime("%Y-%m-%d")

            # Generate cost with variance
            import random

            variance = base_cost * variance_pct / 100
            cost = base_cost + random.uniform(-variance, variance)

            try:
                dynamodb.put_item(
                    TableName="cost-service-history",
                    Item={
                        "pk": {"S": f"SERVICE#{service_name}"},
                        "sk": {"S": f"DATE#{date_str}"},
                        "service_name": {"S": service_name},
                        "cost": {"N": str(round(cost, 2))},
                        "usage_quantity": {"N": str(int(cost * 100))},
                        "region": {"S": "ap-northeast-2"},
                        "timestamp": {"S": date.strftime("%Y-%m-%dT23:59:59Z")},
                        "currency": {"S": "USD"},
                    },
                )
            except Exception:
                return False

    return True


@pytest.fixture
def inject_ec2_cost_spike(
    localstack_available: bool,
    cost_localstack_endpoint: str,
    cost_tables_created: bool,
    inject_cost_baseline: bool,
) -> Generator[Dict[str, Any], None, None]:
    """Inject EC2 cost spike scenario.

    Returns dict with spike details.
    """
    if not localstack_available or not cost_tables_created:
        yield {}
        return

    import boto3

    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=cost_localstack_endpoint,
        region_name="ap-northeast-2",
    )

    today = datetime.utcnow().strftime("%Y-%m-%d")
    spike_cost = 800.0

    try:
        dynamodb.put_item(
            TableName="cost-service-history",
            Item={
                "pk": {"S": "SERVICE#Amazon EC2"},
                "sk": {"S": f"DATE#{today}"},
                "service_name": {"S": "Amazon EC2"},
                "cost": {"N": str(spike_cost)},
                "usage_quantity": {"N": "8000"},
                "region": {"S": "ap-northeast-2"},
                "timestamp": {"S": f"{today}T23:59:59Z"},
                "currency": {"S": "USD"},
                "scenario": {"S": "ec2-cost-spike"},
                "is_spike": {"BOOL": True},
            },
        )
        yield {
            "service": "Amazon EC2",
            "baseline": 200.0,
            "spike": spike_cost,
            "ratio": 4.0,
            "expected_severity": "high",
            "expected_methods": ["ratio", "stddev"],
        }
    except Exception:
        yield {}


@pytest.fixture
def inject_lambda_cost_spike(
    localstack_available: bool,
    cost_localstack_endpoint: str,
    cost_tables_created: bool,
    inject_cost_baseline: bool,
) -> Generator[Dict[str, Any], None, None]:
    """Inject Lambda cost spike scenario."""
    if not localstack_available or not cost_tables_created:
        yield {}
        return

    import boto3

    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=cost_localstack_endpoint,
        region_name="ap-northeast-2",
    )

    today = datetime.utcnow().strftime("%Y-%m-%d")
    spike_cost = 300.0

    try:
        dynamodb.put_item(
            TableName="cost-service-history",
            Item={
                "pk": {"S": "SERVICE#AWS Lambda"},
                "sk": {"S": f"DATE#{today}"},
                "service_name": {"S": "AWS Lambda"},
                "cost": {"N": str(spike_cost)},
                "usage_quantity": {"N": "150000000"},
                "region": {"S": "ap-northeast-2"},
                "timestamp": {"S": f"{today}T23:59:59Z"},
                "currency": {"S": "USD"},
                "scenario": {"S": "lambda-cost-spike"},
                "is_spike": {"BOOL": True},
            },
        )
        yield {
            "service": "AWS Lambda",
            "baseline": 60.0,
            "spike": spike_cost,
            "ratio": 5.0,
            "expected_severity": "critical",
            "expected_methods": ["ratio", "stddev", "luminol"],
        }
    except Exception:
        yield {}


@pytest.fixture
def inject_multi_service_spike(
    localstack_available: bool,
    cost_localstack_endpoint: str,
    cost_tables_created: bool,
    inject_cost_baseline: bool,
) -> Generator[Dict[str, Any], None, None]:
    """Inject multi-service cost spike scenario."""
    if not localstack_available or not cost_tables_created:
        yield {}
        return

    import boto3

    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=cost_localstack_endpoint,
        region_name="ap-northeast-2",
    )

    today = datetime.utcnow().strftime("%Y-%m-%d")

    services = [
        ("Amazon EC2", 400.0, 4000, 2.0),
        ("AWS Lambda", 180.0, 90000000, 3.0),
        ("Amazon RDS", 225.0, 1575, 1.5),
    ]

    try:
        for service_name, cost, usage, ratio in services:
            dynamodb.put_item(
                TableName="cost-service-history",
                Item={
                    "pk": {"S": f"SERVICE#{service_name}"},
                    "sk": {"S": f"DATE#{today}"},
                    "service_name": {"S": service_name},
                    "cost": {"N": str(cost)},
                    "usage_quantity": {"N": str(usage)},
                    "region": {"S": "ap-northeast-2"},
                    "timestamp": {"S": f"{today}T23:59:59Z"},
                    "currency": {"S": "USD"},
                    "scenario": {"S": "multi-service-spike"},
                    "is_spike": {"BOOL": True},
                },
            )

        yield {
            "services": [s[0] for s in services],
            "total_expected_anomalies": 3,
            "expected_overall_severity": "critical",
        }
    except Exception:
        yield {}
