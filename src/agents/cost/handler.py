"""
Cost Detection Handler for Cost Anomaly Detection Lambda.

Entry point for Cost Agent - detects cost anomalies using AWS Cost Explorer
and Luminol-based anomaly detection.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import os
import uuid

from src.common.handlers.base_handler import BaseHandler
from src.agents.cost.services.cost_explorer_client import CostExplorerClient
from src.agents.cost.services.anomaly_detector import (
    CostAnomalyDetector,
    CostAnomalyResult,
)
from src.common.services.aws_client import AWSClient, AWSProvider


class CostDetectionHandler(BaseHandler):
    """
    Lambda handler for Cost anomaly detection.

    Processes AWS Cost Explorer data to detect cost anomalies:
    - Ratio-based detection (sudden spikes)
    - Standard deviation detection (statistical outliers)
    - Trend detection (unexpected deviations from trend)
    - Luminol-based detection (advanced time-series analysis)

    Triggers analysis workflow when anomalies are detected.
    """

    def __init__(self):
        super().__init__("CostDetectionHandler")
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize service clients based on configuration."""
        aws_provider = AWSProvider(self.config["aws_provider"])
        self.aws_client = AWSClient(provider=aws_provider)

        # Cost Explorer client - provider type from environment
        # COST_PROVIDER: mock (default), real, localstack
        cost_provider = os.getenv("COST_PROVIDER", "mock")
        use_mock = cost_provider == "mock"

        # Support legacy COST_EXPLORER_MOCK for backward compatibility
        if os.getenv("COST_EXPLORER_MOCK", "").lower() == "false":
            use_mock = False
            cost_provider = "real"

        self.cost_client = CostExplorerClient(
            use_mock=use_mock,
            provider_type=cost_provider,
        )

        # Anomaly detector with configurable sensitivity
        sensitivity = float(os.getenv("COST_SENSITIVITY", "0.7"))
        self.detector = CostAnomalyDetector(sensitivity=sensitivity)

        # DynamoDB tables
        self.history_table = os.getenv("COST_HISTORY_TABLE", "bdp-cost-history")
        self.anomaly_table = os.getenv("COST_ANOMALY_TABLE", "bdp-cost-anomaly-tracking")

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """Validate cost detection event."""
        # Support both direct invocation and scheduled (MWAA) invocation
        # No strict validation required - defaults are sufficient
        return None

    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """Process cost detection request."""
        body = self._parse_body(event)

        # Support detection_type for selective detection
        detection_type = body.get("detection_type", event.get("detection_type", "all"))
        days = int(body.get("days", event.get("days", 14)))
        min_cost_threshold = float(body.get("min_cost_threshold", event.get("min_cost_threshold", 1.0)))

        self.logger.info(f"Processing cost detection: type={detection_type}, days={days}")

        if detection_type == "all":
            return self._run_full_detection(days, min_cost_threshold)
        elif detection_type == "forecast":
            return self._run_forecast_detection(days)
        elif detection_type == "aws_anomalies":
            return self._get_aws_anomalies(days)
        else:
            raise ValueError(
                f"Invalid detection_type: {detection_type}. "
                f"Must be one of: all, forecast, aws_anomalies"
            )

    def _run_full_detection(
        self, days: int, min_cost_threshold: float
    ) -> Dict[str, Any]:
        """Run full cost anomaly detection."""
        self.logger.info(f"Running full cost detection for {days} days")

        # Get historical costs formatted for detector
        cost_data = self.cost_client.get_historical_costs_for_detector(days=days)

        # Filter by minimum cost threshold
        filtered_data = {
            service: data
            for service, data in cost_data.items()
            if data["current_cost"] >= min_cost_threshold
        }

        # Run batch detection
        results = self.detector.analyze_batch(filtered_data)

        # Filter to only anomalies
        anomalies = [r for r in results if r.is_anomaly]

        # Count by severity
        severity_breakdown = self._count_by_severity(anomalies)

        self.logger.info(
            f"Detection complete: {len(anomalies)} anomalies found "
            f"(critical: {severity_breakdown['critical']}, "
            f"high: {severity_breakdown['high']})"
        )

        # Store results if there are anomalies
        if anomalies:
            self._store_detection_results(anomalies)

            # Trigger analysis for critical/high anomalies
            critical_high = [
                a for a in anomalies
                if a.severity in ("critical", "high")
            ]
            if critical_high:
                self._trigger_analysis(critical_high, severity_breakdown)

        return {
            "detection_type": "all",
            "period_days": days,
            "services_analyzed": len(filtered_data),
            "anomalies_detected": len(anomalies) > 0,
            "total_anomalies": len(anomalies),
            "severity_breakdown": severity_breakdown,
            "summary": self._generate_summary(anomalies),
            "anomalies": [self._result_to_dict(a) for a in anomalies[:20]],  # Limit response
            "detection_timestamp": datetime.utcnow().isoformat(),
        }

    def _run_forecast_detection(self, days: int) -> Dict[str, Any]:
        """Run cost forecast and detect unexpected deviations."""
        self.logger.info(f"Running forecast detection for next {days} days")

        end_date = datetime.utcnow() + timedelta(days=days)
        start_date = datetime.utcnow()

        forecast = self.cost_client.get_cost_forecast(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )

        return {
            "detection_type": "forecast",
            "forecast_period_days": days,
            "total_forecast": forecast["total_forecast"],
            "unit": forecast["unit"],
            "daily_forecasts": forecast["forecast_by_time"],
            "detection_timestamp": datetime.utcnow().isoformat(),
        }

    def _get_aws_anomalies(self, days: int) -> Dict[str, Any]:
        """Get anomalies from AWS Cost Anomaly Detection service."""
        self.logger.info(f"Fetching AWS-detected anomalies for {days} days")

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        anomalies = self.cost_client.get_anomalies(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )

        return {
            "detection_type": "aws_anomalies",
            "period_days": days,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "detection_timestamp": datetime.utcnow().isoformat(),
        }

    def _count_by_severity(self, anomalies: List[CostAnomalyResult]) -> Dict[str, int]:
        """Count anomalies by severity level."""
        return {
            "critical": sum(1 for a in anomalies if a.severity == "critical"),
            "high": sum(1 for a in anomalies if a.severity == "high"),
            "medium": sum(1 for a in anomalies if a.severity == "medium"),
            "low": sum(1 for a in anomalies if a.severity == "low"),
        }

    def _generate_summary(self, anomalies: List[CostAnomalyResult]) -> str:
        """Generate human-readable summary of detection results."""
        if not anomalies:
            return "No cost anomalies detected."

        severity_counts = self._count_by_severity(anomalies)
        services = [a.service_name for a in anomalies[:5]]

        return (
            f"Detected {len(anomalies)} cost anomalies "
            f"[{severity_counts['critical']} critical, "
            f"{severity_counts['high']} high, "
            f"{severity_counts['medium']} medium, "
            f"{severity_counts['low']} low]. "
            f"Top affected services: {', '.join(services)}"
        )

    def _result_to_dict(self, result: CostAnomalyResult) -> Dict[str, Any]:
        """Convert CostAnomalyResult to dictionary."""
        return {
            "service_name": result.service_name,
            "severity": result.severity,
            "confidence_score": result.confidence_score,
            "current_cost": result.current_value,
            "previous_cost": result.previous_value,
            "change_ratio": result.change_ratio,
            "detected_methods": result.detected_methods,
            "analysis": result.analysis,
            "timestamp": result.timestamp,
        }

    def _store_detection_results(self, anomalies: List[CostAnomalyResult]) -> None:
        """Store detection results in DynamoDB."""
        try:
            detection_timestamp = datetime.utcnow().isoformat()
            date_key = detection_timestamp[:10]

            # Store summary record
            self.aws_client.put_dynamodb_item(
                table_name=self.config["dynamodb_table"],
                item={
                    "pk": f"COST#{date_key}",
                    "sk": f"DETECTION#{detection_timestamp}",
                    "type": "cost_detection",
                    "total_anomalies": len(anomalies),
                    "severity_breakdown": self._count_by_severity(anomalies),
                    "summary": self._generate_summary(anomalies),
                    "timestamp": detection_timestamp,
                },
            )

            # Store individual critical/high anomalies
            for anomaly in anomalies:
                if anomaly.severity in ("critical", "high"):
                    anomaly_id = f"cost_{anomaly.service_name}_{uuid.uuid4().hex[:8]}"
                    self.aws_client.put_dynamodb_item(
                        table_name=self.anomaly_table,
                        item={
                            "pk": f"ANOMALY#{anomaly_id}",
                            "sk": f"COST#{anomaly.timestamp}",
                            "type": "cost_anomaly",
                            **self._result_to_dict(anomaly),
                        },
                    )

            self.logger.info(f"Stored cost detection results: {len(anomalies)} anomalies")

        except Exception as e:
            self.logger.error(f"Failed to store cost detection results: {e}")

    def _trigger_analysis(
        self,
        anomalies: List[CostAnomalyResult],
        severity_breakdown: Dict[str, int],
    ) -> None:
        """Publish cost anomaly event to EventBridge for downstream analysis."""
        try:
            detection_timestamp = datetime.utcnow().isoformat()

            # Create aggregated anomaly data for analysis
            anomaly_data = {
                "signature": f"cost_{detection_timestamp[:10]}",
                "anomaly_type": "cost_anomaly",
                "service_name": "cost-agent",
                "agent": "cost",
                "first_seen": detection_timestamp,
                "last_seen": detection_timestamp,
                "occurrence_count": len(anomalies),
                "severity": self._get_highest_severity(anomalies),
                "summary": self._generate_summary(anomalies),
                "anomaly_details": [self._result_to_dict(a) for a in anomalies[:10]],
                "metrics_snapshot": {
                    "total_anomalies": len(anomalies),
                    **severity_breakdown,
                },
            }

            self.aws_client.put_eventbridge_event(
                event_bus=self.config["event_bus"],
                source="cd1-agent.cost",
                detail_type="Cost Anomaly Detected",
                detail=anomaly_data,
            )

            self.logger.info(
                f"Analysis triggered for cost detection: {anomaly_data['signature']}"
            )

        except Exception as e:
            self.logger.error(f"Failed to trigger cost analysis: {e}")

    def _get_highest_severity(self, anomalies: List[CostAnomalyResult]) -> str:
        """Get the highest severity level from anomaly results."""
        severity_order = ["critical", "high", "medium", "low"]
        for severity in severity_order:
            if any(a.severity == severity for a in anomalies):
                return severity
        return "low"


# Lambda entry point
handler_instance = CostDetectionHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)
