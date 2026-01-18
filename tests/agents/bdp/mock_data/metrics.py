"""
Metrics Mock Data for BDP Agent Tests.

Provides CloudWatch Metrics data generators for various test scenarios.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import random


class MetricDataFactory:
    """Factory for generating mock CloudWatch Metrics data."""

    @staticmethod
    def create_datapoint(
        value: float,
        timestamp: Optional[datetime] = None,
        statistic: str = "Average",
        unit: str = "Count",
    ) -> Dict[str, Any]:
        """Create a single metric datapoint."""
        ts = timestamp or datetime.utcnow()
        return {
            "Timestamp": ts.isoformat(),
            statistic: value,
            "Unit": unit,
        }

    @staticmethod
    def create_metric_response(
        datapoints: List[Dict[str, Any]],
        namespace: str = "AWS/Lambda",
        metric_name: str = "Errors",
    ) -> Dict[str, Any]:
        """Create a full metric response structure."""
        return {
            "namespace": namespace,
            "metric": metric_name,
            "datapoints": datapoints,
        }

    @staticmethod
    def create_stable_metrics(
        count: int = 10,
        base_value: float = 5.0,
        variance: float = 0.5,
        period_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Create stable metrics with low variance (no anomaly)."""
        base = datetime.utcnow()
        datapoints = [
            MetricDataFactory.create_datapoint(
                value=base_value + random.uniform(-variance, variance),
                timestamp=base - timedelta(seconds=i * period_seconds),
            )
            for i in range(count)
        ]
        return MetricDataFactory.create_metric_response(datapoints)

    @staticmethod
    def create_spike_metrics(
        count: int = 10,
        base_value: float = 5.0,
        spike_value: float = 50.0,
        spike_position: int = -1,
    ) -> Dict[str, Any]:
        """Create metrics with a spike at specified position."""
        base = datetime.utcnow()
        values = [base_value + random.uniform(-0.5, 0.5) for _ in range(count)]

        # Place spike at specified position (default: last)
        actual_position = spike_position if spike_position >= 0 else count + spike_position
        values[actual_position] = spike_value

        datapoints = [
            MetricDataFactory.create_datapoint(
                value=val,
                timestamp=base - timedelta(minutes=i * 5),
            )
            for i, val in enumerate(values)
        ]
        return MetricDataFactory.create_metric_response(datapoints)

    @staticmethod
    def create_trending_metrics(
        count: int = 10,
        start_value: float = 5.0,
        end_value: float = 50.0,
    ) -> Dict[str, Any]:
        """Create metrics with a gradual trend."""
        base = datetime.utcnow()
        step = (end_value - start_value) / (count - 1)
        datapoints = [
            MetricDataFactory.create_datapoint(
                value=start_value + (i * step),
                timestamp=base - timedelta(minutes=i * 5),
            )
            for i in range(count)
        ]
        return MetricDataFactory.create_metric_response(datapoints)

    @staticmethod
    def create_zero_variance_metrics(count: int = 10, value: float = 5.0) -> Dict[str, Any]:
        """Create metrics with identical values (zero variance)."""
        base = datetime.utcnow()
        datapoints = [
            MetricDataFactory.create_datapoint(
                value=value,
                timestamp=base - timedelta(minutes=i * 5),
            )
            for i in range(count)
        ]
        return MetricDataFactory.create_metric_response(datapoints)

    @staticmethod
    def create_insufficient_data(count: int = 1) -> Dict[str, Any]:
        """Create metrics with insufficient datapoints."""
        base = datetime.utcnow()
        datapoints = [
            MetricDataFactory.create_datapoint(value=10.0, timestamp=base)
            for _ in range(count)
        ]
        return MetricDataFactory.create_metric_response(datapoints)


def generate_normal_metrics(
    count: int = 10,
    base_value: float = 5.0,
    namespace: str = "AWS/Lambda",
    metric_name: str = "Errors",
) -> Dict[str, Any]:
    """Generate normal metrics without anomalies.

    Args:
        count: Number of datapoints
        base_value: Base metric value
        namespace: CloudWatch namespace
        metric_name: Metric name

    Returns:
        Mock CloudWatch metrics response
    """
    metrics = MetricDataFactory.create_stable_metrics(count, base_value)
    metrics["namespace"] = namespace
    metrics["metric"] = metric_name
    return metrics


def generate_spike_metrics(
    spike_multiplier: float = 10.0,
    base_value: float = 5.0,
    count: int = 10,
) -> Dict[str, Any]:
    """Generate metrics with a spike anomaly.

    Args:
        spike_multiplier: How much higher the spike is vs base value
        base_value: Base metric value
        count: Number of datapoints

    Returns:
        Mock CloudWatch metrics response with spike
    """
    return MetricDataFactory.create_spike_metrics(
        count=count,
        base_value=base_value,
        spike_value=base_value * spike_multiplier,
    )


def generate_critical_spike_metrics(
    base_value: float = 5.0,
    count: int = 10,
) -> Dict[str, Any]:
    """Generate metrics with a critical spike (z-score > 3).

    Args:
        base_value: Base metric value
        count: Number of datapoints

    Returns:
        Mock CloudWatch metrics response with critical spike
    """
    return MetricDataFactory.create_spike_metrics(
        count=count,
        base_value=base_value,
        spike_value=base_value * 40,  # Extreme spike for z-score > 3
    )


def calculate_z_score(values: List[float]) -> float:
    """Calculate z-score for the last value in the list.

    Utility function for test assertions.
    """
    if len(values) < 2:
        return 0.0

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    stddev = variance ** 0.5

    if stddev == 0:
        return 0.0

    return (values[-1] - mean) / stddev
