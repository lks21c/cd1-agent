"""
AWS Cost Explorer Client for CD1 Agent.

AWS Cost Explorer (Production) 또는 Mock (Testing)을 지원하는 통합 클라이언트.
Cross-Account AssumeRole을 통한 다중 계정 비용 조회 지원.
"""
import json
import os
import random
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()


class CostData:
    """비용 데이터 구조체."""

    def __init__(self, date: str, service: str, amount: float, currency: str = "USD"):
        self.date = date
        self.service = service
        self.amount = amount
        self.currency = currency

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "service": self.service,
            "amount": self.amount,
            "currency": self.currency
        }


class AccountConfig:
    """Cross-Account 설정."""

    def __init__(self, role_arn: str, account_alias: str, external_id: Optional[str] = None):
        self.role_arn = role_arn
        self.account_alias = account_alias
        self.external_id = external_id
        # Extract account ID from ARN
        self.account_id = role_arn.split(":")[4] if role_arn else "unknown"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountConfig":
        return cls(
            role_arn=data["role_arn"],
            account_alias=data.get("account_alias", ""),
            external_id=data.get("external_id")
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_arn": self.role_arn,
            "account_alias": self.account_alias,
            "account_id": self.account_id,
            "external_id": self.external_id
        }


class BaseCostExplorerProvider(ABC):
    """Cost Explorer Provider 추상 클래스."""

    @abstractmethod
    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[str]] = None,
        filter_expression: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        비용 및 사용량 데이터 조회.

        Args:
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)
            granularity: DAILY, MONTHLY, HOURLY
            group_by: 그룹화 기준 (SERVICE, LINKED_ACCOUNT, etc.)
            filter_expression: 필터 조건

        Returns:
            비용 데이터 딕셔너리
        """
        pass

    @abstractmethod
    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "MONTHLY",
        metric: str = "UNBLENDED_COST"
    ) -> Dict[str, Any]:
        """비용 예측 데이터 조회."""
        pass


class AWSCostExplorerProvider(BaseCostExplorerProvider):
    """AWS Cost Explorer Provider (Production)."""

    def __init__(self, session=None):
        """
        초기화.

        Args:
            session: boto3 session (Cross-Account 시 assumed role session)
        """
        import boto3

        if session:
            self.client = session.client('ce')
        else:
            self.client = boto3.client('ce')

        self.logger = logger.bind(service="aws_cost_explorer")

    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[str]] = None,
        filter_expression: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """AWS Cost Explorer 비용 데이터 조회."""
        self.logger.info(
            "cost_explorer_query",
            start_date=start_date,
            end_date=end_date,
            granularity=granularity
        )

        params = {
            "TimePeriod": {
                "Start": start_date,
                "End": end_date
            },
            "Granularity": granularity,
            "Metrics": ["UnblendedCost", "UsageQuantity"]
        }

        if group_by:
            params["GroupBy"] = [
                {"Type": "DIMENSION", "Key": dim} for dim in group_by
            ]

        if filter_expression:
            params["Filter"] = filter_expression

        # Handle pagination
        results = []
        next_token = None

        while True:
            if next_token:
                params["NextPageToken"] = next_token

            response = self.client.get_cost_and_usage(**params)
            results.extend(response.get("ResultsByTime", []))

            next_token = response.get("NextPageToken")
            if not next_token:
                break

        return self._transform_response(results, group_by)

    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "MONTHLY",
        metric: str = "UNBLENDED_COST"
    ) -> Dict[str, Any]:
        """AWS Cost Explorer 비용 예측 조회."""
        self.logger.info(
            "cost_forecast_query",
            start_date=start_date,
            end_date=end_date
        )

        response = self.client.get_cost_forecast(
            TimePeriod={
                "Start": start_date,
                "End": end_date
            },
            Granularity=granularity,
            Metric=metric
        )

        return {
            "total": {
                "amount": float(response.get("Total", {}).get("Amount", 0)),
                "unit": response.get("Total", {}).get("Unit", "USD")
            },
            "forecast_by_time": [
                {
                    "date": item["TimePeriod"]["Start"],
                    "mean_value": float(item.get("MeanValue", 0))
                }
                for item in response.get("ForecastResultsByTime", [])
            ]
        }

    def _transform_response(
        self,
        results: List[Dict],
        group_by: Optional[List[str]]
    ) -> Dict[str, Any]:
        """API 응답을 내부 포맷으로 변환."""
        costs_by_date = {}
        total_cost = 0.0

        for result in results:
            date = result["TimePeriod"]["Start"]
            costs_by_date[date] = {}

            if group_by and "Groups" in result:
                for group in result["Groups"]:
                    service_name = group["Keys"][0]
                    amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    costs_by_date[date][service_name] = amount
                    total_cost += amount
            else:
                # No grouping
                amount = float(result["Total"]["UnblendedCost"]["Amount"])
                costs_by_date[date]["total"] = amount
                total_cost += amount

        return {
            "costs_by_date": costs_by_date,
            "total_cost": total_cost,
            "currency": "USD"
        }


class MockCostExplorerProvider(BaseCostExplorerProvider):
    """Mock Cost Explorer Provider for testing."""

    # 주요 AWS 서비스 목록
    SERVICES = [
        "Amazon EC2",
        "Amazon RDS",
        "Amazon S3",
        "AWS Lambda",
        "Amazon DynamoDB",
        "Amazon CloudWatch",
        "Amazon SQS",
        "Amazon SNS",
        "AWS Step Functions",
        "Amazon API Gateway",
        "Amazon EKS",
        "Amazon ElastiCache"
    ]

    def __init__(self, account_id: str = "123456789012", seed: Optional[int] = None):
        """
        초기화.

        Args:
            account_id: 계정 ID (다른 계정별로 다른 데이터 생성)
            seed: 랜덤 시드 (재현 가능한 테스트용)
        """
        self.account_id = account_id
        self.logger = logger.bind(service="mock_cost_explorer", account_id=account_id)
        self.call_count = 0
        self._injected_anomalies: List[Dict] = []

        # Account-specific seed for consistent mock data per account
        if seed is None:
            seed = int(hashlib.md5(account_id.encode()).hexdigest()[:8], 16)
        self._seed = seed

    def inject_anomaly(
        self,
        date: str,
        service: str,
        anomaly_type: str = "spike",
        multiplier: float = 3.0
    ) -> None:
        """
        테스트용 이상 현상 주입.

        Args:
            date: 이상 현상 발생 날짜
            service: 서비스 이름
            anomaly_type: 이상 유형 (spike, gradual, drop)
            multiplier: 비용 배율
        """
        self._injected_anomalies.append({
            "date": date,
            "service": service,
            "type": anomaly_type,
            "multiplier": multiplier
        })
        self.logger.info(
            "anomaly_injected",
            date=date,
            service=service,
            type=anomaly_type
        )

    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[str]] = None,
        filter_expression: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Mock 비용 데이터 생성."""
        self.call_count += 1
        self.logger.info(
            "mock_cost_query",
            start_date=start_date,
            end_date=end_date,
            granularity=granularity
        )

        random.seed(self._seed)

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        costs_by_date = {}
        total_cost = 0.0

        # Determine step based on granularity
        if granularity == "HOURLY":
            delta = timedelta(hours=1)
            date_format = "%Y-%m-%dT%H:00:00Z"
        elif granularity == "MONTHLY":
            delta = timedelta(days=30)
            date_format = "%Y-%m-01"
        else:  # DAILY
            delta = timedelta(days=1)
            date_format = "%Y-%m-%d"

        current = start
        day_index = 0

        while current < end:
            date_str = current.strftime(date_format)
            costs_by_date[date_str] = {}

            services = group_by and "SERVICE" in group_by
            if services:
                for service in self.SERVICES:
                    base_cost = self._generate_service_base_cost(service, day_index)
                    cost = self._apply_anomaly(date_str, service, base_cost)
                    costs_by_date[date_str][service] = round(cost, 2)
                    total_cost += cost
            else:
                base_cost = self._generate_total_base_cost(day_index)
                cost = self._apply_anomaly(date_str, "total", base_cost)
                costs_by_date[date_str]["total"] = round(cost, 2)
                total_cost += cost

            current += delta
            day_index += 1

        return {
            "costs_by_date": costs_by_date,
            "total_cost": round(total_cost, 2),
            "currency": "USD"
        }

    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "MONTHLY",
        metric: str = "UNBLENDED_COST"
    ) -> Dict[str, Any]:
        """Mock 비용 예측 생성."""
        self.call_count += 1
        self.logger.info("mock_cost_forecast", start_date=start_date, end_date=end_date)

        random.seed(self._seed)

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        forecasts = []
        current = start

        while current < end:
            # Generate forecast with some variance
            base_forecast = 5000 + random.uniform(-500, 500)
            forecasts.append({
                "date": current.strftime("%Y-%m-%d"),
                "mean_value": round(base_forecast, 2)
            })
            current += timedelta(days=30)

        total_forecast = sum(f["mean_value"] for f in forecasts)

        return {
            "total": {
                "amount": round(total_forecast, 2),
                "unit": "USD"
            },
            "forecast_by_time": forecasts
        }

    def _generate_service_base_cost(self, service: str, day_index: int) -> float:
        """서비스별 기본 비용 생성."""
        # Service-specific base costs
        base_costs = {
            "Amazon EC2": 150.0,
            "Amazon RDS": 80.0,
            "Amazon S3": 20.0,
            "AWS Lambda": 5.0,
            "Amazon DynamoDB": 15.0,
            "Amazon CloudWatch": 10.0,
            "Amazon SQS": 2.0,
            "Amazon SNS": 1.0,
            "AWS Step Functions": 3.0,
            "Amazon API Gateway": 8.0,
            "Amazon EKS": 100.0,
            "Amazon ElastiCache": 50.0
        }

        base = base_costs.get(service, 10.0)

        # Add daily variance (±20%)
        variance = base * random.uniform(-0.2, 0.2)

        # Add weekly pattern (weekends slightly lower)
        weekday_factor = 1.0 if day_index % 7 < 5 else 0.7

        # Add gradual trend (slight increase over time)
        trend_factor = 1.0 + (day_index * 0.002)

        return (base + variance) * weekday_factor * trend_factor

    def _generate_total_base_cost(self, day_index: int) -> float:
        """총 비용 생성."""
        base = 500.0
        variance = base * random.uniform(-0.15, 0.15)
        weekday_factor = 1.0 if day_index % 7 < 5 else 0.75
        trend_factor = 1.0 + (day_index * 0.001)

        return (base + variance) * weekday_factor * trend_factor

    def _apply_anomaly(self, date_str: str, service: str, base_cost: float) -> float:
        """주입된 이상 현상 적용."""
        for anomaly in self._injected_anomalies:
            if anomaly["date"] == date_str and anomaly["service"] == service:
                if anomaly["type"] == "spike":
                    return base_cost * anomaly["multiplier"]
                elif anomaly["type"] == "drop":
                    return base_cost / anomaly["multiplier"]
                elif anomaly["type"] == "gradual":
                    # Gradual increase starts from this date
                    return base_cost * (1 + (anomaly["multiplier"] - 1) * 0.3)

        return base_cost


class CostExplorerClient:
    """통합 Cost Explorer 클라이언트 - Provider 자동 선택."""

    def __init__(
        self,
        mock_mode: Optional[bool] = None,
        account_configs: Optional[List[AccountConfig]] = None
    ):
        """
        CostExplorerClient 초기화.

        Args:
            mock_mode: True면 mock provider 사용, None이면 환경 변수에서 결정
            account_configs: Cross-Account 설정 목록

        환경 변수:
            AWS_MOCK: 'true'로 설정 시 mock provider 사용
            COST_TARGET_ACCOUNTS: JSON 형태의 계정 설정
        """
        if mock_mode is None:
            mock_mode = os.environ.get('AWS_MOCK', '').lower() == 'true'

        self.mock_mode = mock_mode
        self.logger = logger.bind(service="cost_explorer_client", mock_mode=mock_mode)

        # Load account configs from environment if not provided
        if account_configs is None:
            accounts_json = os.environ.get('COST_TARGET_ACCOUNTS', '[]')
            try:
                accounts_data = json.loads(accounts_json)
                account_configs = [AccountConfig.from_dict(a) for a in accounts_data]
            except json.JSONDecodeError:
                account_configs = []

        self.account_configs = account_configs

        # Initialize provider for current account
        if mock_mode:
            self._provider = MockCostExplorerProvider()
        else:
            self._provider = AWSCostExplorerProvider()

        self.logger.info(
            "cost_explorer_client_initialized",
            mode="mock" if mock_mode else "aws",
            account_count=len(account_configs)
        )

    def get_provider_for_account(
        self,
        account_config: AccountConfig
    ) -> BaseCostExplorerProvider:
        """
        특정 계정을 위한 Provider 반환 (Cross-Account AssumeRole).

        Args:
            account_config: 대상 계정 설정

        Returns:
            해당 계정용 Provider
        """
        if self.mock_mode:
            return MockCostExplorerProvider(account_id=account_config.account_id)

        # Real AWS: Assume role
        import boto3

        sts_client = boto3.client('sts')

        assume_role_params = {
            'RoleArn': account_config.role_arn,
            'RoleSessionName': 'BDPCostExplorerSession'
        }

        if account_config.external_id:
            assume_role_params['ExternalId'] = account_config.external_id

        self.logger.info(
            "assuming_role",
            role_arn=account_config.role_arn,
            account_alias=account_config.account_alias
        )

        response = sts_client.assume_role(**assume_role_params)

        # Create session with assumed role credentials
        session = boto3.Session(
            aws_access_key_id=response['Credentials']['AccessKeyId'],
            aws_secret_access_key=response['Credentials']['SecretAccessKey'],
            aws_session_token=response['Credentials']['SessionToken']
        )

        return AWSCostExplorerProvider(session=session)

    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[str]] = None,
        filter_expression: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """현재 계정의 비용 데이터 조회."""
        return self._provider.get_cost_and_usage(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            group_by=group_by,
            filter_expression=filter_expression
        )

    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "MONTHLY",
        metric: str = "UNBLENDED_COST"
    ) -> Dict[str, Any]:
        """현재 계정의 비용 예측 조회."""
        return self._provider.get_cost_forecast(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            metric=metric
        )

    def get_all_accounts_costs(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        모든 설정된 계정의 비용 데이터 조회.

        Returns:
            계정 ID를 키로 하는 비용 데이터 딕셔너리
        """
        results = {}

        # Current account
        results["current"] = {
            "account_alias": "Current Account",
            "data": self.get_cost_and_usage(
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
                group_by=group_by
            )
        }

        # Cross-account
        for config in self.account_configs:
            try:
                provider = self.get_provider_for_account(config)
                results[config.account_id] = {
                    "account_alias": config.account_alias,
                    "data": provider.get_cost_and_usage(
                        start_date=start_date,
                        end_date=end_date,
                        granularity=granularity,
                        group_by=group_by
                    )
                }
            except Exception as e:
                self.logger.error(
                    "cross_account_cost_query_failed",
                    account_id=config.account_id,
                    error=str(e)
                )
                results[config.account_id] = {
                    "account_alias": config.account_alias,
                    "error": str(e)
                }

        return results

    def get_stats(self) -> Dict[str, int]:
        """Mock 모드에서 호출 통계 반환."""
        if not self.mock_mode:
            return {}

        return {
            'cost_explorer_calls': self._provider.call_count
        }


# 사용 예시
if __name__ == "__main__":
    # Mock 모드로 테스트
    os.environ['AWS_MOCK'] = 'true'

    # 단일 계정 테스트
    client = CostExplorerClient()
    print(f"Mock mode: {client.mock_mode}")

    # 비용 데이터 조회
    costs = client.get_cost_and_usage(
        start_date="2024-01-01",
        end_date="2024-01-15",
        granularity="DAILY",
        group_by=["SERVICE"]
    )
    print(f"\nTotal cost: ${costs['total_cost']:.2f}")
    print(f"Days: {len(costs['costs_by_date'])}")

    # 첫 날 서비스별 비용 출력
    first_day = list(costs['costs_by_date'].keys())[0]
    print(f"\nCosts for {first_day}:")
    for service, amount in sorted(
        costs['costs_by_date'][first_day].items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]:
        print(f"  {service}: ${amount:.2f}")

    # 이상 현상 주입 테스트
    mock_provider = MockCostExplorerProvider(account_id="test-account")
    mock_provider.inject_anomaly(
        date="2024-01-10",
        service="Amazon EC2",
        anomaly_type="spike",
        multiplier=3.0
    )

    costs_with_anomaly = mock_provider.get_cost_and_usage(
        start_date="2024-01-08",
        end_date="2024-01-12",
        granularity="DAILY",
        group_by=["SERVICE"]
    )

    print("\nEC2 costs (with injected anomaly on 2024-01-10):")
    for date, services in sorted(costs_with_anomaly['costs_by_date'].items()):
        ec2_cost = services.get("Amazon EC2", 0)
        print(f"  {date}: ${ec2_cost:.2f}")

    # 비용 예측 테스트
    forecast = client.get_cost_forecast(
        start_date="2024-02-01",
        end_date="2024-04-01",
        granularity="MONTHLY"
    )
    print(f"\nForecast total: ${forecast['total']['amount']:.2f}")

    # 통계
    print(f"\nCall statistics: {json.dumps(client.get_stats(), indent=2)}")
