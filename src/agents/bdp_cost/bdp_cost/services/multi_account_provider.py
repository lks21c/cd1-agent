"""
Multi-Account Cost Explorer Provider.

STS AssumeRole based multi-account Cost Explorer access for cost drift detection.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AccountConfig:
    """AWS Account configuration for Cost Explorer access."""

    account_id: str
    account_name: str
    role_arn: Optional[str] = None  # None = use current credentials
    region: str = "us-east-1"
    external_id: Optional[str] = None


@dataclass
class ServiceCostData:
    """Service cost data with historical values."""

    service_name: str
    account_id: str
    account_name: str
    current_cost: float
    historical_costs: List[float]
    timestamps: List[str]
    currency: str = "USD"


class BaseMultiAccountProvider(ABC):
    """Abstract base class for multi-account Cost Explorer providers."""

    @abstractmethod
    def get_cost_data(self, days: int = 14) -> Dict[str, List[ServiceCostData]]:
        """Get service-level cost data from all accounts.

        Args:
            days: Number of days of historical data

        Returns:
            Dict mapping account_id to list of ServiceCostData
        """
        pass

    @abstractmethod
    def get_accounts(self) -> List[AccountConfig]:
        """Get list of configured accounts."""
        pass


class MultiAccountCostExplorerProvider(BaseMultiAccountProvider):
    """
    STS AssumeRole based Multi-Account Cost Explorer Provider.

    Accesses Cost Explorer API across multiple AWS accounts using
    STS AssumeRole for cross-account access.

    Environment Variables:
        BDP_ACCOUNT_1_ID: Primary account ID
        BDP_ACCOUNT_1_NAME: Primary account name
        BDP_ACCOUNT_1_ROLE_ARN: Role ARN (empty for current credentials)

        BDP_ACCOUNT_2_ID: Secondary account ID
        BDP_ACCOUNT_2_NAME: Secondary account name
        BDP_ACCOUNT_2_ROLE_ARN: Role ARN for cross-account access
    """

    def __init__(
        self,
        accounts: Optional[List[AccountConfig]] = None,
        region: str = "us-east-1",
    ):
        """Initialize multi-account provider.

        Args:
            accounts: List of account configurations. If None, loads from env.
            region: AWS region for Cost Explorer (default: us-east-1)
        """
        self.region = region
        self.accounts = accounts or self._load_accounts_from_env()
        self._sessions: Dict[str, Any] = {}

        logger.info(
            f"MultiAccountCostExplorerProvider initialized with "
            f"{len(self.accounts)} accounts"
        )

    def _load_accounts_from_env(self) -> List[AccountConfig]:
        """Load account configurations from environment variables."""
        accounts = []

        # Support up to 10 accounts
        for i in range(1, 11):
            account_id = os.getenv(f"BDP_ACCOUNT_{i}_ID")
            if not account_id:
                continue

            account_name = os.getenv(f"BDP_ACCOUNT_{i}_NAME", f"account-{i}")
            role_arn = os.getenv(f"BDP_ACCOUNT_{i}_ROLE_ARN") or None
            external_id = os.getenv(f"BDP_ACCOUNT_{i}_EXTERNAL_ID")
            region = os.getenv(f"BDP_ACCOUNT_{i}_REGION", self.region)

            accounts.append(
                AccountConfig(
                    account_id=account_id,
                    account_name=account_name,
                    role_arn=role_arn,
                    region=region,
                    external_id=external_id,
                )
            )

        if not accounts:
            logger.warning("No accounts configured, using default mock account")
            accounts.append(
                AccountConfig(
                    account_id="123456789012",
                    account_name="default",
                    role_arn=None,
                )
            )

        return accounts

    def get_accounts(self) -> List[AccountConfig]:
        """Get list of configured accounts."""
        return self.accounts.copy()

    def _get_session(self, account: AccountConfig) -> Any:
        """Get or create boto3 session for account.

        Args:
            account: Account configuration

        Returns:
            boto3 Session for the account
        """
        import boto3

        if account.account_id in self._sessions:
            return self._sessions[account.account_id]

        if account.role_arn:
            # Cross-account access via STS AssumeRole
            session = self._assume_role(account)
        else:
            # Use current credentials
            session = boto3.Session(region_name=account.region)

        self._sessions[account.account_id] = session
        return session

    def _assume_role(self, account: AccountConfig) -> Any:
        """Assume IAM role for cross-account access.

        Args:
            account: Account configuration with role_arn

        Returns:
            boto3 Session with assumed role credentials
        """
        import boto3

        sts_client = boto3.client("sts", region_name=account.region)

        assume_role_params: Dict[str, Any] = {
            "RoleArn": account.role_arn,
            "RoleSessionName": f"bdp-cost-{account.account_id}",
            "DurationSeconds": 3600,  # 1 hour
        }

        if account.external_id:
            assume_role_params["ExternalId"] = account.external_id

        logger.info(f"Assuming role {account.role_arn} for account {account.account_id}")

        response = sts_client.assume_role(**assume_role_params)
        credentials = response["Credentials"]

        return boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=account.region,
        )

    def get_cost_data(self, days: int = 14) -> Dict[str, List[ServiceCostData]]:
        """Get service-level cost data from all configured accounts.

        Args:
            days: Number of days of historical data

        Returns:
            Dict mapping account_id to list of ServiceCostData
        """
        result: Dict[str, List[ServiceCostData]] = {}

        for account in self.accounts:
            try:
                account_data = self._get_account_cost_data(account, days)
                result[account.account_id] = account_data
                logger.info(
                    f"Retrieved {len(account_data)} services from "
                    f"account {account.account_name}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to get cost data for account {account.account_name}: {e}"
                )
                result[account.account_id] = []

        return result

    def _get_account_cost_data(
        self, account: AccountConfig, days: int
    ) -> List[ServiceCostData]:
        """Get cost data for a single account.

        Args:
            account: Account configuration
            days: Number of days of historical data

        Returns:
            List of ServiceCostData for each service
        """
        session = self._get_session(account)
        ce_client = session.client("ce", region_name="us-east-1")

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        response = ce_client.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d"),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        # Aggregate by service
        service_data: Dict[str, Dict[str, Any]] = {}

        for period in response.get("ResultsByTime", []):
            timestamp = period["TimePeriod"]["Start"]

            for group in period.get("Groups", []):
                service_name = group["Keys"][0] if group["Keys"] else "Unknown"
                cost = float(
                    group.get("Metrics", {})
                    .get("UnblendedCost", {})
                    .get("Amount", 0)
                )

                if service_name not in service_data:
                    service_data[service_name] = {
                        "historical_costs": [],
                        "timestamps": [],
                    }

                service_data[service_name]["historical_costs"].append(cost)
                service_data[service_name]["timestamps"].append(timestamp)

        # Convert to ServiceCostData
        result = []
        for service_name, data in service_data.items():
            costs = data["historical_costs"]
            current_cost = costs[-1] if costs else 0.0

            result.append(
                ServiceCostData(
                    service_name=service_name,
                    account_id=account.account_id,
                    account_name=account.account_name,
                    current_cost=current_cost,
                    historical_costs=costs,
                    timestamps=data["timestamps"],
                )
            )

        return result


class LocalStackMultiAccountProvider(BaseMultiAccountProvider):
    """
    LocalStack-based Multi-Account Cost Explorer Provider.

    Reads cost data from DynamoDB tables that simulate multi-account
    Cost Explorer data. Used for testing with LocalStack.

    DynamoDB Schema (bdp-cost-history):
        PK: ACCOUNT#{account_id}#SERVICE#{service_name}
        SK: DATE#{yyyy-mm-dd}
        Attributes: cost, account_name, service_name, timestamp
    """

    def __init__(
        self,
        accounts: Optional[List[AccountConfig]] = None,
        endpoint_url: Optional[str] = None,
        table_name: str = "bdp-cost-history",
        region: str = "ap-northeast-2",
    ):
        """Initialize LocalStack provider.

        Args:
            accounts: Account configurations for simulated accounts
            endpoint_url: LocalStack endpoint URL
            table_name: DynamoDB table name
            region: AWS region
        """
        import boto3

        self.accounts = accounts or self._default_accounts()
        self.endpoint_url = endpoint_url or os.getenv(
            "LOCALSTACK_ENDPOINT", "http://localhost:4566"
        )
        self.table_name = table_name
        self.region = region

        self.dynamodb = boto3.client(
            "dynamodb",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
        )

        logger.info(
            f"LocalStackMultiAccountProvider initialized: "
            f"endpoint={self.endpoint_url}, table={self.table_name}"
        )

    def _default_accounts(self) -> List[AccountConfig]:
        """Get default simulated accounts."""
        return [
            AccountConfig(
                account_id="111111111111",
                account_name="bdp-prod",
            ),
            AccountConfig(
                account_id="222222222222",
                account_name="hyundaicard-member",
            ),
        ]

    def get_accounts(self) -> List[AccountConfig]:
        """Get list of configured accounts."""
        return self.accounts.copy()

    def get_cost_data(self, days: int = 14) -> Dict[str, List[ServiceCostData]]:
        """Get cost data from LocalStack DynamoDB.

        Args:
            days: Number of days of historical data

        Returns:
            Dict mapping account_id to list of ServiceCostData
        """
        result: Dict[str, List[ServiceCostData]] = {}

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        for account in self.accounts:
            try:
                # Scan for account data
                response = self.dynamodb.scan(
                    TableName=self.table_name,
                    FilterExpression="begins_with(pk, :account_prefix) AND sk BETWEEN :start AND :end",
                    ExpressionAttributeValues={
                        ":account_prefix": {"S": f"ACCOUNT#{account.account_id}"},
                        ":start": {"S": f"DATE#{start_date.strftime('%Y-%m-%d')}"},
                        ":end": {"S": f"DATE#{end_date.strftime('%Y-%m-%d')}"},
                    },
                )

                account_data = self._parse_dynamodb_response(
                    response.get("Items", []), account
                )
                result[account.account_id] = account_data

            except Exception as e:
                logger.error(f"Failed to get LocalStack data for {account.account_id}: {e}")
                result[account.account_id] = []

        return result

    def _parse_dynamodb_response(
        self, items: List[Dict[str, Any]], account: AccountConfig
    ) -> List[ServiceCostData]:
        """Parse DynamoDB items into ServiceCostData.

        Args:
            items: DynamoDB items
            account: Account configuration

        Returns:
            List of ServiceCostData
        """
        # Group by service
        service_data: Dict[str, Dict[str, Any]] = {}

        for item in items:
            pk = item.get("pk", {}).get("S", "")
            # Extract service name from PK: ACCOUNT#xxx#SERVICE#service_name
            parts = pk.split("#")
            service_name = parts[3] if len(parts) > 3 else "Unknown"

            sk = item.get("sk", {}).get("S", "")
            timestamp = sk.replace("DATE#", "") if sk.startswith("DATE#") else sk

            cost = float(item.get("cost", {}).get("N", "0"))

            if service_name not in service_data:
                service_data[service_name] = {
                    "historical_costs": [],
                    "timestamps": [],
                }

            service_data[service_name]["historical_costs"].append(cost)
            service_data[service_name]["timestamps"].append(timestamp)

        # Convert to ServiceCostData
        result = []
        for service_name, data in service_data.items():
            # Sort by timestamp
            sorted_pairs = sorted(
                zip(data["timestamps"], data["historical_costs"]),
                key=lambda x: x[0],
            )
            timestamps = [p[0] for p in sorted_pairs]
            costs = [p[1] for p in sorted_pairs]
            current_cost = costs[-1] if costs else 0.0

            result.append(
                ServiceCostData(
                    service_name=service_name,
                    account_id=account.account_id,
                    account_name=account.account_name,
                    current_cost=current_cost,
                    historical_costs=costs,
                    timestamps=timestamps,
                )
            )

        return result


class MockMultiAccountProvider(BaseMultiAccountProvider):
    """Mock provider for unit testing."""

    def __init__(
        self,
        accounts: Optional[List[AccountConfig]] = None,
        mock_data: Optional[Dict[str, List[ServiceCostData]]] = None,
    ):
        """Initialize mock provider.

        Args:
            accounts: Account configurations
            mock_data: Pre-configured mock data
        """
        self.accounts = accounts or [
            AccountConfig(
                account_id="123456789012",
                account_name="test-account-1",
            ),
            AccountConfig(
                account_id="987654321098",
                account_name="test-account-2",
            ),
        ]
        self.mock_data = mock_data
        self.call_history: List[Dict[str, Any]] = []

    def get_accounts(self) -> List[AccountConfig]:
        """Get list of configured accounts."""
        return self.accounts.copy()

    def get_cost_data(self, days: int = 14) -> Dict[str, List[ServiceCostData]]:
        """Get mock cost data.

        Args:
            days: Number of days (for recording)

        Returns:
            Mock cost data
        """
        self.call_history.append({"method": "get_cost_data", "days": days})

        if self.mock_data:
            return self.mock_data

        # Generate mock data
        return self._generate_mock_data(days)

    def _generate_mock_data(self, days: int) -> Dict[str, List[ServiceCostData]]:
        """Generate realistic mock cost data."""
        import random

        result: Dict[str, List[ServiceCostData]] = {}

        services = [
            ("Amazon Athena", 250000, 0.15),  # KRW base, variance ratio
            ("AWS Lambda", 50000, 0.10),
            ("Amazon S3", 100000, 0.08),
            ("Amazon EC2", 500000, 0.12),
            ("Amazon DynamoDB", 80000, 0.10),
        ]

        for account in self.accounts:
            account_services = []
            end_date = datetime.utcnow()

            for service_name, base_cost, variance in services:
                historical_costs = []
                timestamps = []

                for day in range(days):
                    date = end_date - timedelta(days=days - day - 1)
                    # Add some variance
                    daily_variance = random.uniform(-variance, variance)
                    cost = base_cost * (1 + daily_variance)

                    historical_costs.append(cost)
                    timestamps.append(date.strftime("%Y-%m-%d"))

                account_services.append(
                    ServiceCostData(
                        service_name=service_name,
                        account_id=account.account_id,
                        account_name=account.account_name,
                        current_cost=historical_costs[-1] if historical_costs else 0,
                        historical_costs=historical_costs,
                        timestamps=timestamps,
                        currency="KRW",
                    )
                )

            result[account.account_id] = account_services

        return result


def create_provider(
    provider_type: Optional[str] = None,
    accounts: Optional[List[AccountConfig]] = None,
    **kwargs: Any,
) -> BaseMultiAccountProvider:
    """Factory function to create appropriate provider.

    Args:
        provider_type: Provider type (real, localstack, mock)
        accounts: Account configurations
        **kwargs: Additional provider-specific arguments

    Returns:
        Provider instance
    """
    provider_type = provider_type or os.getenv("BDP_PROVIDER", "mock")

    if provider_type == "localstack":
        return LocalStackMultiAccountProvider(accounts=accounts, **kwargs)
    elif provider_type == "real":
        return MultiAccountCostExplorerProvider(accounts=accounts, **kwargs)
    else:
        return MockMultiAccountProvider(accounts=accounts, **kwargs)
