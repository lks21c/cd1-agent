"""
Cost Explorer Client with Provider Abstraction.

Client for AWS Cost Explorer API with mock support for testing.
Supports real AWS, mock, and LocalStack providers.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class BaseCostExplorerProvider(ABC):
    """Abstract base class for Cost Explorer providers."""

    @abstractmethod
    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[Dict[str, str]]] = None,
        filter_expression: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get cost and usage data."""
        pass

    @abstractmethod
    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        metric: str = "UNBLENDED_COST",
    ) -> Dict[str, Any]:
        """Get cost forecast."""
        pass

    @abstractmethod
    def get_anomalies(
        self,
        start_date: str,
        end_date: str,
        monitor_arn: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get detected cost anomalies from AWS Cost Anomaly Detection."""
        pass


class RealCostExplorerProvider(BaseCostExplorerProvider):
    """Real AWS Cost Explorer provider."""

    def __init__(self, region: Optional[str] = None):
        import boto3

        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.client = boto3.client("ce", region_name=self.region)

    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[Dict[str, str]]] = None,
        filter_expression: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get cost and usage data from AWS Cost Explorer."""
        params: Dict[str, Any] = {
            "TimePeriod": {"Start": start_date, "End": end_date},
            "Granularity": granularity,
            "Metrics": ["UnblendedCost", "UsageQuantity"],
        }

        if group_by:
            params["GroupBy"] = group_by
        if filter_expression:
            params["Filter"] = filter_expression

        response = self.client.get_cost_and_usage(**params)
        return self._parse_cost_response(response)

    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        metric: str = "UNBLENDED_COST",
    ) -> Dict[str, Any]:
        """Get cost forecast from AWS Cost Explorer."""
        response = self.client.get_cost_forecast(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity=granularity,
            Metric=metric,
        )

        return {
            "total_forecast": float(response.get("Total", {}).get("Amount", 0)),
            "unit": response.get("Total", {}).get("Unit", "USD"),
            "forecast_by_time": [
                {
                    "start": item["TimePeriod"]["Start"],
                    "end": item["TimePeriod"]["End"],
                    "mean": float(item.get("MeanValue", 0)),
                    "min": float(item.get("PredictionIntervalLowerBound", 0)),
                    "max": float(item.get("PredictionIntervalUpperBound", 0)),
                }
                for item in response.get("ForecastResultsByTime", [])
            ],
        }

    def get_anomalies(
        self,
        start_date: str,
        end_date: str,
        monitor_arn: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get detected anomalies from AWS Cost Anomaly Detection."""
        params: Dict[str, Any] = {
            "DateInterval": {"StartDate": start_date, "EndDate": end_date},
        }

        if monitor_arn:
            params["MonitorArn"] = monitor_arn

        response = self.client.get_anomalies(**params)
        return [
            {
                "anomaly_id": a["AnomalyId"],
                "start_date": a["AnomalyStartDate"],
                "end_date": a.get("AnomalyEndDate"),
                "dimension_value": a.get("DimensionValue"),
                "root_causes": a.get("RootCauses", []),
                "impact": {
                    "max_impact": float(a.get("Impact", {}).get("MaxImpact", 0)),
                    "total_impact": float(a.get("Impact", {}).get("TotalImpact", 0)),
                },
                "feedback": a.get("Feedback"),
            }
            for a in response.get("Anomalies", [])
        ]

    def _parse_cost_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Cost Explorer response into structured format."""
        results = []
        for item in response.get("ResultsByTime", []):
            period_data = {
                "start": item["TimePeriod"]["Start"],
                "end": item["TimePeriod"]["End"],
                "total": {},
                "groups": [],
            }

            if "Total" in item:
                period_data["total"] = {
                    metric: {
                        "amount": float(data.get("Amount", 0)),
                        "unit": data.get("Unit", "USD"),
                    }
                    for metric, data in item["Total"].items()
                }

            for group in item.get("Groups", []):
                group_data = {
                    "keys": group.get("Keys", []),
                    "metrics": {
                        metric: {
                            "amount": float(data.get("Amount", 0)),
                            "unit": data.get("Unit", "USD"),
                        }
                        for metric, data in group.get("Metrics", {}).items()
                    },
                }
                period_data["groups"].append(group_data)

            results.append(period_data)

        return {"results": results, "next_token": response.get("NextPageToken")}


class LocalStackCostExplorerProvider(BaseCostExplorerProvider):
    """
    LocalStack Cost Explorer provider.

    Reads cost data from DynamoDB tables that simulate AWS Cost Explorer.
    Cost Explorer API is not supported by LocalStack, so this provider
    reads from the cost-service-history table populated by init scripts.

    DynamoDB Schema (cost-service-history):
        PK: SERVICE#{service_name}
        SK: DATE#{yyyy-mm-dd}
        Attributes: cost, usage_quantity, region, timestamp
    """

    def __init__(
        self,
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        import boto3

        self.region = region or os.getenv("AWS_REGION", "ap-northeast-2")
        self.endpoint_url = endpoint_url or os.getenv(
            "LOCALSTACK_ENDPOINT", "http://localhost:4566"
        )
        self.table_name = os.getenv("COST_HISTORY_TABLE", "cost-service-history")
        self.forecast_table = os.getenv("COST_FORECAST_TABLE", "cost-forecast-data")
        self.anomaly_table = os.getenv("COST_ANOMALY_TABLE", "cost-anomaly-tracking")

        self.dynamodb = boto3.client(
            "dynamodb",
            region_name=self.region,
            endpoint_url=self.endpoint_url,
        )

        logger.info(
            f"LocalStackCostExplorerProvider initialized: "
            f"endpoint={self.endpoint_url}, table={self.table_name}"
        )

    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[Dict[str, str]]] = None,
        filter_expression: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Get cost and usage data from LocalStack DynamoDB.

        Queries cost-service-history table and transforms to Cost Explorer format.
        """
        logger.debug(f"Querying cost data: {start_date} to {end_date}")

        # Get all services (scan, then filter by date range)
        try:
            response = self.dynamodb.scan(
                TableName=self.table_name,
                FilterExpression="sk BETWEEN :start AND :end",
                ExpressionAttributeValues={
                    ":start": {"S": f"DATE#{start_date}"},
                    ":end": {"S": f"DATE#{end_date}"},
                },
            )
        except Exception as e:
            logger.error(f"Failed to query cost data: {e}")
            return {"results": [], "next_token": None}

        items = response.get("Items", [])

        # Organize by date
        date_data: Dict[str, Dict[str, Any]] = {}

        for item in items:
            # Extract date from sk (DATE#yyyy-mm-dd)
            sk = item.get("sk", {}).get("S", "")
            date_str = sk.replace("DATE#", "") if sk.startswith("DATE#") else sk

            service_name = item.get("service_name", {}).get("S", "Unknown")
            cost = float(item.get("cost", {}).get("N", "0"))
            usage = float(item.get("usage_quantity", {}).get("N", "0"))

            if date_str not in date_data:
                date_data[date_str] = {
                    "total_cost": 0.0,
                    "total_usage": 0.0,
                    "groups": {},
                }

            date_data[date_str]["total_cost"] += cost
            date_data[date_str]["total_usage"] += usage
            date_data[date_str]["groups"][service_name] = {
                "cost": cost,
                "usage": usage,
            }

        # Convert to Cost Explorer response format
        results = []
        for date_str in sorted(date_data.keys()):
            data = date_data[date_str]

            # Calculate next date for end period
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            next_date = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")

            period_data = {
                "start": date_str,
                "end": next_date,
                "total": {
                    "UnblendedCost": {"amount": data["total_cost"], "unit": "USD"},
                    "UsageQuantity": {"amount": data["total_usage"], "unit": "N/A"},
                },
                "groups": [],
            }

            # Add groups if group_by is requested
            if group_by:
                for service, metrics in data["groups"].items():
                    period_data["groups"].append(
                        {
                            "keys": [service],
                            "metrics": {
                                "UnblendedCost": {
                                    "amount": metrics["cost"],
                                    "unit": "USD",
                                },
                                "UsageQuantity": {
                                    "amount": metrics["usage"],
                                    "unit": "N/A",
                                },
                            },
                        }
                    )

            results.append(period_data)

        logger.info(f"Retrieved {len(results)} days of cost data from LocalStack")
        return {"results": results, "next_token": None}

    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        metric: str = "UNBLENDED_COST",
    ) -> Dict[str, Any]:
        """
        Get cost forecast from LocalStack DynamoDB.

        If no forecast data exists, generates a simple projection based on
        historical data.
        """
        logger.debug(f"Getting cost forecast: {start_date} to {end_date}")

        # Try to read from forecast table
        try:
            response = self.dynamodb.scan(
                TableName=self.forecast_table,
                FilterExpression="pk BETWEEN :start AND :end",
                ExpressionAttributeValues={
                    ":start": {"S": f"FORECAST#{start_date}"},
                    ":end": {"S": f"FORECAST#{end_date}"},
                },
            )
            items = response.get("Items", [])

            if items:
                forecasts = []
                for item in items:
                    pk = item.get("pk", {}).get("S", "")
                    date_str = pk.replace("FORECAST#", "")
                    mean = float(item.get("mean", {}).get("N", "0"))
                    min_val = float(item.get("min", {}).get("N", str(mean * 0.9)))
                    max_val = float(item.get("max", {}).get("N", str(mean * 1.1)))

                    forecasts.append(
                        {
                            "start": date_str,
                            "end": date_str,
                            "mean": mean,
                            "min": min_val,
                            "max": max_val,
                        }
                    )

                total = sum(f["mean"] for f in forecasts)
                return {
                    "total_forecast": total,
                    "unit": "USD",
                    "forecast_by_time": forecasts,
                }

        except Exception as e:
            logger.warning(f"Forecast table not available: {e}")

        # Generate forecast from historical data
        return self._generate_forecast_from_history(start_date, end_date)

    def _generate_forecast_from_history(
        self, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """Generate a simple forecast based on historical average."""
        # Get last 14 days of historical data
        end_historical = datetime.utcnow()
        start_historical = end_historical - timedelta(days=14)

        historical = self.get_cost_and_usage(
            start_date=start_historical.strftime("%Y-%m-%d"),
            end_date=end_historical.strftime("%Y-%m-%d"),
        )

        # Calculate daily average
        total_costs = [
            r["total"]["UnblendedCost"]["amount"]
            for r in historical.get("results", [])
            if r.get("total")
        ]

        if total_costs:
            avg_daily = sum(total_costs) / len(total_costs)
        else:
            avg_daily = 500.0  # Default if no history

        # Generate forecast
        forecasts = []
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        while current < end:
            next_date = current + timedelta(days=1)
            forecasts.append(
                {
                    "start": current.strftime("%Y-%m-%d"),
                    "end": next_date.strftime("%Y-%m-%d"),
                    "mean": avg_daily,
                    "min": avg_daily * 0.85,
                    "max": avg_daily * 1.15,
                }
            )
            current = next_date

        return {
            "total_forecast": sum(f["mean"] for f in forecasts),
            "unit": "USD",
            "forecast_by_time": forecasts,
        }

    def get_anomalies(
        self,
        start_date: str,
        end_date: str,
        monitor_arn: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get detected cost anomalies from LocalStack DynamoDB.

        Reads from cost-anomaly-tracking table. Returns empty list if
        no anomalies have been injected.
        """
        logger.debug(f"Querying anomalies: {start_date} to {end_date}")

        try:
            response = self.dynamodb.scan(
                TableName=self.anomaly_table,
                FilterExpression="sk BETWEEN :start AND :end",
                ExpressionAttributeValues={
                    ":start": {"S": f"COST#{start_date}"},
                    ":end": {"S": f"COST#{end_date}"},
                },
            )

            anomalies = []
            for item in response.get("Items", []):
                pk = item.get("pk", {}).get("S", "")
                anomaly_id = pk.replace("ANOMALY#", "")

                anomalies.append(
                    {
                        "anomaly_id": anomaly_id,
                        "start_date": item.get("start_date", {}).get("S"),
                        "end_date": item.get("end_date", {}).get("S"),
                        "dimension_value": item.get("dimension_value", {}).get("S"),
                        "root_causes": [],
                        "impact": {
                            "max_impact": float(
                                item.get("max_impact", {}).get("N", "0")
                            ),
                            "total_impact": float(
                                item.get("total_impact", {}).get("N", "0")
                            ),
                        },
                        "feedback": item.get("feedback", {}).get("S"),
                    }
                )

            return anomalies

        except Exception as e:
            logger.warning(f"Failed to query anomalies: {e}")
            return []


class MockCostExplorerProvider(BaseCostExplorerProvider):
    """Mock Cost Explorer provider for testing."""

    def __init__(self, mock_data: Optional[Dict[str, Any]] = None):
        self.mock_data = mock_data or {}
        self.call_history: List[Dict[str, Any]] = []

    def _record_call(self, method: str, **kwargs: Any) -> None:
        """Record method call for verification."""
        self.call_history.append({"method": method, **kwargs})

    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[Dict[str, str]]] = None,
        filter_expression: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return mock cost and usage data."""
        self._record_call(
            "get_cost_and_usage",
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )

        if "cost_and_usage" in self.mock_data:
            return self.mock_data["cost_and_usage"]

        # Generate mock data
        results = []
        current = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        services = ["Lambda", "EC2", "RDS", "S3", "DynamoDB"]
        base_costs = {"Lambda": 50, "EC2": 200, "RDS": 150, "S3": 30, "DynamoDB": 80}

        while current < end:
            next_date = current + timedelta(days=1)
            period_data = {
                "start": current.strftime("%Y-%m-%d"),
                "end": next_date.strftime("%Y-%m-%d"),
                "total": {
                    "UnblendedCost": {"amount": 0.0, "unit": "USD"},
                    "UsageQuantity": {"amount": 0.0, "unit": "N/A"},
                },
                "groups": [],
            }

            total_cost = 0.0
            for service in services:
                # Add some variation
                variation = (hash(f"{current}{service}") % 30) - 15
                cost = base_costs[service] + variation
                total_cost += cost

                if group_by:
                    period_data["groups"].append(
                        {
                            "keys": [f"AWS {service}"],
                            "metrics": {
                                "UnblendedCost": {"amount": cost, "unit": "USD"},
                                "UsageQuantity": {"amount": cost * 10, "unit": "N/A"},
                            },
                        }
                    )

            period_data["total"]["UnblendedCost"]["amount"] = total_cost
            results.append(period_data)
            current = next_date

        return {"results": results, "next_token": None}

    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        metric: str = "UNBLENDED_COST",
    ) -> Dict[str, Any]:
        """Return mock cost forecast."""
        self._record_call(
            "get_cost_forecast",
            start_date=start_date,
            end_date=end_date,
        )

        if "cost_forecast" in self.mock_data:
            return self.mock_data["cost_forecast"]

        # Generate mock forecast
        forecasts = []
        current = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        base_daily = 500.0

        while current < end:
            next_date = current + timedelta(days=1)
            variation = (hash(current.isoformat()) % 50) - 25
            mean = base_daily + variation

            forecasts.append(
                {
                    "start": current.strftime("%Y-%m-%d"),
                    "end": next_date.strftime("%Y-%m-%d"),
                    "mean": mean,
                    "min": mean * 0.9,
                    "max": mean * 1.1,
                }
            )
            current = next_date

        total = sum(f["mean"] for f in forecasts)
        return {
            "total_forecast": total,
            "unit": "USD",
            "forecast_by_time": forecasts,
        }

    def get_anomalies(
        self,
        start_date: str,
        end_date: str,
        monitor_arn: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock anomalies."""
        self._record_call(
            "get_anomalies",
            start_date=start_date,
            end_date=end_date,
        )

        if "anomalies" in self.mock_data:
            return self.mock_data["anomalies"]

        # Return empty by default (no anomalies)
        return []


class CostExplorerClient:
    """
    Unified Cost Explorer client with provider abstraction.

    Usage:
        # Real AWS
        client = CostExplorerClient(use_mock=False)

        # Mock for testing
        client = CostExplorerClient(use_mock=True, mock_data={...})

        # LocalStack (via environment variable)
        # Set COST_PROVIDER=localstack
        client = CostExplorerClient(provider_type="localstack")

        # Get cost data
        costs = client.get_cost_and_usage(
            start_date="2024-01-01",
            end_date="2024-01-31"
        )

        # Get cost by service
        costs = client.get_cost_by_service(days=30)

    Provider types:
        - mock: In-memory mock data (default for testing)
        - real: Real AWS Cost Explorer API
        - localstack: LocalStack DynamoDB-based simulation
    """

    def __init__(
        self,
        use_mock: bool = True,
        provider_type: Optional[str] = None,
        region: Optional[str] = None,
        mock_data: Optional[Dict[str, Any]] = None,
        endpoint_url: Optional[str] = None,
    ):
        # Determine provider type from parameter or environment
        self.provider_type = provider_type or os.getenv("COST_PROVIDER", "mock")

        # Create appropriate provider based on type
        if self.provider_type == "localstack":
            self._provider: BaseCostExplorerProvider = LocalStackCostExplorerProvider(
                region=region,
                endpoint_url=endpoint_url,
            )
            self.use_mock = False
            logger.info("CostExplorerClient using LocalStack provider")

        elif self.provider_type == "real" or (not use_mock and self.provider_type != "mock"):
            self._provider = RealCostExplorerProvider(region)
            self.use_mock = False
            logger.info("CostExplorerClient using real AWS provider")

        else:
            # Default to mock
            self._provider = MockCostExplorerProvider(mock_data)
            self.use_mock = True
            logger.debug("CostExplorerClient using mock provider")

    def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        group_by: Optional[List[Dict[str, str]]] = None,
        filter_expression: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get cost and usage data."""
        return self._provider.get_cost_and_usage(
            start_date, end_date, granularity, group_by, filter_expression
        )

    def get_cost_forecast(
        self,
        start_date: str,
        end_date: str,
        granularity: str = "DAILY",
        metric: str = "UNBLENDED_COST",
    ) -> Dict[str, Any]:
        """Get cost forecast."""
        return self._provider.get_cost_forecast(start_date, end_date, granularity, metric)

    def get_anomalies(
        self,
        start_date: str,
        end_date: str,
        monitor_arn: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get detected cost anomalies."""
        return self._provider.get_anomalies(start_date, end_date, monitor_arn)

    def get_cost_by_service(
        self, days: int = 30, granularity: str = "DAILY"
    ) -> Dict[str, List[float]]:
        """
        Get cost breakdown by service for the specified period.

        Args:
            days: Number of days to look back
            granularity: DAILY, MONTHLY, or HOURLY

        Returns:
            Dict mapping service name to list of costs
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        result = self.get_cost_and_usage(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            granularity=granularity,
            group_by=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        # Aggregate by service
        service_costs: Dict[str, List[float]] = {}
        for period in result.get("results", []):
            for group in period.get("groups", []):
                service = group["keys"][0] if group["keys"] else "Unknown"
                cost = group["metrics"].get("UnblendedCost", {}).get("amount", 0)

                if service not in service_costs:
                    service_costs[service] = []
                service_costs[service].append(cost)

        return service_costs

    def get_historical_costs_for_detector(
        self, days: int = 30
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get historical costs formatted for CostAnomalyDetector.

        Returns data in the format expected by CostAnomalyDetector.analyze_batch()
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        result = self.get_cost_and_usage(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            granularity="DAILY",
            group_by=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        # Build service data
        service_data: Dict[str, Dict[str, Any]] = {}

        for period in result.get("results", []):
            timestamp = period["start"]
            for group in period.get("groups", []):
                service = group["keys"][0] if group["keys"] else "Unknown"
                cost = group["metrics"].get("UnblendedCost", {}).get("amount", 0)

                if service not in service_data:
                    service_data[service] = {
                        "historical_costs": [],
                        "timestamps": [],
                        "current_cost": 0.0,
                    }

                service_data[service]["historical_costs"].append(cost)
                service_data[service]["timestamps"].append(timestamp)

        # Set current_cost as the last value
        for service in service_data:
            if service_data[service]["historical_costs"]:
                service_data[service]["current_cost"] = service_data[service][
                    "historical_costs"
                ][-1]

        return service_data

    @property
    def call_history(self) -> List[Dict[str, Any]]:
        """Get call history (only available for mock provider)."""
        if isinstance(self._provider, MockCostExplorerProvider):
            return self._provider.call_history
        return []
