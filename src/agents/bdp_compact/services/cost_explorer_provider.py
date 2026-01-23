"""
Single-Account Cost Explorer Provider.

Lambda 실행 역할 기반 단일 계정 Cost Explorer 접근 (STS AssumeRole 제거).
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ServiceCostData:
    """Service cost data with historical values.

    Backward compatible with multi-account provider.
    """

    service_name: str
    account_id: str
    account_name: str
    current_cost: float
    historical_costs: List[float]
    timestamps: List[str]
    currency: str = "USD"


class BaseCostExplorerProvider(ABC):
    """Abstract base class for Cost Explorer providers."""

    @abstractmethod
    def get_cost_data(self, days: int = 14) -> List[ServiceCostData]:
        """Get service-level cost data.

        Args:
            days: Number of days of historical data

        Returns:
            List of ServiceCostData for each service
        """
        pass

    @abstractmethod
    def get_account_info(self) -> Dict[str, str]:
        """Get current account information.

        Returns:
            Dict with account_id and account_name
        """
        pass


class CostExplorerProvider(BaseCostExplorerProvider):
    """
    Single-Account Cost Explorer Provider.

    Uses Lambda execution role permissions to directly access Cost Explorer API.
    No STS AssumeRole - uses current credentials (Lambda execution role).

    Environment Variables:
        BDP_ACCOUNT_NAME: Account name for logging/alerts (default: 'default')
    """

    def __init__(
        self,
        account_name: Optional[str] = None,
        region: str = "us-east-1",
    ):
        """Initialize single-account provider.

        Args:
            account_name: Account name for identification (logs, alerts)
            region: AWS region for Cost Explorer (must be us-east-1)
        """
        import boto3

        self.region = region
        self.account_name = account_name or os.getenv("BDP_ACCOUNT_NAME", "default")
        self._account_id: Optional[str] = None
        self._session = boto3.Session(region_name=region)

        logger.info(
            f"CostExplorerProvider initialized: "
            f"account_name={self.account_name}, region={region}"
        )

    def _get_account_id(self) -> str:
        """Get current account ID from STS GetCallerIdentity.

        Returns:
            AWS account ID
        """
        if self._account_id:
            return self._account_id

        sts_client = self._session.client("sts", region_name=self.region)

        response = sts_client.get_caller_identity()
        self._account_id = response["Account"]
        logger.info(f"Resolved account ID: {self._account_id}")

        return self._account_id

    def get_account_info(self) -> Dict[str, str]:
        """Get current account information.

        Returns:
            Dict with account_id and account_name
        """
        return {
            "account_id": self._get_account_id(),
            "account_name": self.account_name,
        }

    def get_cost_data(self, days: int = 14) -> List[ServiceCostData]:
        """Get service-level cost data from Cost Explorer.

        Args:
            days: Number of days of historical data

        Returns:
            List of ServiceCostData for each service
        """
        account_id = self._get_account_id()

        ce_client = self._session.client(
            "ce",
            region_name="us-east-1",  # Cost Explorer API only available in us-east-1
        )

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
                    account_id=account_id,
                    account_name=self.account_name,
                    current_cost=current_cost,
                    historical_costs=costs,
                    timestamps=data["timestamps"],
                )
            )

        logger.info(f"Retrieved {len(result)} services from account {self.account_name}")
        return result


class LocalStackCostExplorerProvider(BaseCostExplorerProvider):
    """
    LocalStack-based Cost Explorer Provider.

    Reads cost data from DynamoDB tables for testing with LocalStack.

    DynamoDB Schema (bdp-cost-history):
        PK: ACCOUNT#{account_id}#SERVICE#{service_name}
        SK: DATE#{yyyy-mm-dd}
        Attributes: cost, account_name, service_name, timestamp
    """

    def __init__(
        self,
        account_id: str = "111111111111",
        account_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        table_name: str = "bdp-cost-history",
        region: str = "ap-northeast-2",
    ):
        """Initialize LocalStack provider.

        Args:
            account_id: Simulated account ID
            account_name: Account name for identification
            endpoint_url: LocalStack endpoint URL
            table_name: DynamoDB table name
            region: AWS region
        """
        import boto3

        self.account_id = account_id
        self.account_name = account_name or os.getenv("BDP_ACCOUNT_NAME", "localstack-test")
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
            f"LocalStackCostExplorerProvider initialized: "
            f"endpoint={self.endpoint_url}, table={self.table_name}, "
            f"account={self.account_name}"
        )

    def get_account_info(self) -> Dict[str, str]:
        """Get simulated account information.

        Returns:
            Dict with account_id and account_name
        """
        return {
            "account_id": self.account_id,
            "account_name": self.account_name,
        }

    def get_cost_data(self, days: int = 14) -> List[ServiceCostData]:
        """Get cost data from LocalStack DynamoDB.

        Args:
            days: Number of days of historical data

        Returns:
            List of ServiceCostData for each service
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        try:
            # Scan for account data
            response = self.dynamodb.scan(
                TableName=self.table_name,
                FilterExpression="begins_with(pk, :account_prefix) AND sk BETWEEN :start AND :end",
                ExpressionAttributeValues={
                    ":account_prefix": {"S": f"ACCOUNT#{self.account_id}"},
                    ":start": {"S": f"DATE#{start_date.strftime('%Y-%m-%d')}"},
                    ":end": {"S": f"DATE#{end_date.strftime('%Y-%m-%d')}"},
                },
            )

            return self._parse_dynamodb_response(response.get("Items", []))

        except Exception as e:
            logger.error(f"Failed to get LocalStack data: {e}")
            return []

    def _parse_dynamodb_response(
        self, items: List[Dict[str, Any]]
    ) -> List[ServiceCostData]:
        """Parse DynamoDB items into ServiceCostData.

        Args:
            items: DynamoDB items

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
                    account_id=self.account_id,
                    account_name=self.account_name,
                    current_cost=current_cost,
                    historical_costs=costs,
                    timestamps=timestamps,
                )
            )

        logger.info(f"Retrieved {len(result)} services from LocalStack")
        return result


class MockCostExplorerProvider(BaseCostExplorerProvider):
    """Mock provider for unit testing."""

    def __init__(
        self,
        account_id: str = "123456789012",
        account_name: Optional[str] = None,
        mock_data: Optional[List[ServiceCostData]] = None,
    ):
        """Initialize mock provider.

        Args:
            account_id: Mock account ID
            account_name: Mock account name
            mock_data: Pre-configured mock data
        """
        self.account_id = account_id
        self.account_name = account_name or os.getenv("BDP_ACCOUNT_NAME", "test-account")
        self.mock_data = mock_data
        self.call_history: List[Dict[str, Any]] = []

        logger.info(
            f"MockCostExplorerProvider initialized: "
            f"account={self.account_name}, account_id={self.account_id}"
        )

    def get_account_info(self) -> Dict[str, str]:
        """Get mock account information.

        Returns:
            Dict with account_id and account_name
        """
        self.call_history.append({"method": "get_account_info"})
        return {
            "account_id": self.account_id,
            "account_name": self.account_name,
        }

    def get_cost_data(self, days: int = 14) -> List[ServiceCostData]:
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

    def _generate_mock_data(self, days: int) -> List[ServiceCostData]:
        """Generate realistic mock cost data."""
        import random

        result: List[ServiceCostData] = []

        services = [
            ("Amazon Athena", 250000, 0.15),  # KRW base, variance ratio
            ("AWS Lambda", 50000, 0.10),
            ("Amazon S3", 100000, 0.08),
            ("Amazon EC2", 500000, 0.12),
            ("Amazon DynamoDB", 80000, 0.10),
        ]

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

            result.append(
                ServiceCostData(
                    service_name=service_name,
                    account_id=self.account_id,
                    account_name=self.account_name,
                    current_cost=historical_costs[-1] if historical_costs else 0,
                    historical_costs=historical_costs,
                    timestamps=timestamps,
                    currency="KRW",
                )
            )

        return result


def create_provider(
    provider_type: Optional[str] = None,
    **kwargs: Any,
) -> BaseCostExplorerProvider:
    """Factory function to create appropriate provider.

    Args:
        provider_type: Provider type (real, localstack, mock)
        **kwargs: Additional provider-specific arguments

    Returns:
        Provider instance
    """
    provider_type = provider_type or os.getenv("BDP_PROVIDER", "mock")

    if provider_type == "localstack":
        return LocalStackCostExplorerProvider(**kwargs)
    elif provider_type == "real":
        return CostExplorerProvider(**kwargs)
    else:
        return MockCostExplorerProvider(**kwargs)
