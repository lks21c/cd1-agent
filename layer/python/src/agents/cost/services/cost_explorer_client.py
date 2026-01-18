"""
Cost Explorer Client with Provider Abstraction.

Client for AWS Cost Explorer API with mock support for testing.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


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

        # Get cost data
        costs = client.get_cost_and_usage(
            start_date="2024-01-01",
            end_date="2024-01-31"
        )

        # Get cost by service
        costs = client.get_cost_by_service(days=30)
    """

    def __init__(
        self,
        use_mock: bool = True,
        region: Optional[str] = None,
        mock_data: Optional[Dict[str, Any]] = None,
    ):
        self.use_mock = use_mock
        if use_mock:
            self._provider: BaseCostExplorerProvider = MockCostExplorerProvider(mock_data)
        else:
            self._provider = RealCostExplorerProvider(region)

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
