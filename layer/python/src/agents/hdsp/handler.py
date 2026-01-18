"""
HDSP Detection Handler for On-Prem K8s Anomaly Detection Lambda.

Entry point for HDSP Agent - detects Kubernetes cluster anomalies
using Prometheus metrics.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from src.common.handlers.base_handler import BaseHandler
from src.agents.hdsp.services.prometheus_client import PrometheusClient
from src.agents.hdsp.services.anomaly_detector import (
    HDSPAnomalyDetector,
    HDSPDetectionResult,
    HDSPSeverity,
)
from src.common.services.aws_client import AWSClient, AWSProvider


class HDSPDetectionHandler(BaseHandler):
    """
    Lambda handler for HDSP (On-Prem K8s) anomaly detection.

    Processes Prometheus metrics to detect K8s cluster anomalies:
    - Pod failures (CrashLoopBackOff, OOMKilled, restarts)
    - Node pressure (MemoryPressure, DiskPressure, NotReady)
    - Resource anomalies (high CPU/Memory usage)

    Triggers analysis workflow when anomalies are detected.
    """

    def __init__(self):
        super().__init__("HDSPDetectionHandler")
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize service clients based on configuration."""
        aws_provider = AWSProvider(self.config["aws_provider"])
        self.aws_client = AWSClient(provider=aws_provider)

        # Prometheus client auto-detects mock mode from environment
        self.prometheus_client = PrometheusClient()
        self.detector = HDSPAnomalyDetector(
            prometheus_client=self.prometheus_client
        )

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """Validate HDSP detection event."""
        # Support both direct invocation and scheduled (MWAA) invocation
        # No strict validation required - defaults are sufficient
        return None

    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """Process HDSP detection request."""
        body = self._parse_body(event)

        # Support detection_type for selective detection
        detection_type = body.get("detection_type", event.get("detection_type", "all"))

        self.logger.info(f"Processing HDSP detection type: {detection_type}")

        if detection_type == "all":
            return self._run_full_detection(body)
        elif detection_type == "pod_failure":
            return self._detect_pod_failures_only(body)
        elif detection_type == "node_pressure":
            return self._detect_node_pressure_only(body)
        elif detection_type == "resource":
            return self._detect_resource_anomalies_only(body)
        else:
            raise ValueError(
                f"Invalid detection_type: {detection_type}. "
                f"Must be one of: all, pod_failure, node_pressure, resource"
            )

    def _run_full_detection(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Run all detection methods."""
        self.logger.info("Running full HDSP detection")

        # Run detection
        result = self.detector.detect_all()

        self.logger.info(
            f"Detection complete: {result.total_anomalies} anomalies found "
            f"(critical: {result.critical_count}, high: {result.high_count})"
        )

        # Store results
        self._store_detection_result(result)

        # Trigger analysis for critical/high anomalies
        if result.has_critical or result.high_count > 0:
            self._trigger_analysis(result)

        return {
            "detection_type": "all",
            "cluster_name": result.cluster_name,
            "namespaces_checked": result.namespaces_checked,
            "anomalies_detected": result.has_anomalies,
            "total_anomalies": result.total_anomalies,
            "severity_breakdown": {
                "critical": result.critical_count,
                "high": result.high_count,
                "medium": result.medium_count,
                "low": result.low_count,
            },
            "summary": result.summary,
            "anomalies": [a.to_dict() for a in result.anomalies[:20]],  # Limit response size
            "detection_timestamp": result.detection_timestamp,
        }

    def _detect_pod_failures_only(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Run pod failure detection only."""
        self.logger.info("Running pod failure detection")

        anomalies = self.detector.detect_pod_failures()

        result = self._create_partial_result(anomalies, "pod_failure")

        if result.has_critical or result.high_count > 0:
            self._store_detection_result(result)
            self._trigger_analysis(result)

        return {
            "detection_type": "pod_failure",
            "anomalies_detected": result.has_anomalies,
            "total_anomalies": result.total_anomalies,
            "anomalies": [a.to_dict() for a in result.anomalies],
            "summary": result.summary,
        }

    def _detect_node_pressure_only(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Run node pressure detection only."""
        self.logger.info("Running node pressure detection")

        anomalies = self.detector.detect_node_pressure()

        result = self._create_partial_result(anomalies, "node_pressure")

        if result.has_critical or result.high_count > 0:
            self._store_detection_result(result)
            self._trigger_analysis(result)

        return {
            "detection_type": "node_pressure",
            "anomalies_detected": result.has_anomalies,
            "total_anomalies": result.total_anomalies,
            "anomalies": [a.to_dict() for a in result.anomalies],
            "summary": result.summary,
        }

    def _detect_resource_anomalies_only(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Run resource anomaly detection only."""
        self.logger.info("Running resource anomaly detection")

        anomalies = self.detector.detect_resource_anomalies()

        result = self._create_partial_result(anomalies, "resource")

        if result.has_critical or result.high_count > 0:
            self._store_detection_result(result)
            self._trigger_analysis(result)

        return {
            "detection_type": "resource",
            "anomalies_detected": result.has_anomalies,
            "total_anomalies": result.total_anomalies,
            "anomalies": [a.to_dict() for a in result.anomalies],
            "summary": result.summary,
        }

    def _create_partial_result(
        self, anomalies: list, detection_type: str
    ) -> HDSPDetectionResult:
        """Create HDSPDetectionResult from partial detection."""
        critical = sum(1 for a in anomalies if a.severity == HDSPSeverity.CRITICAL)
        high = sum(1 for a in anomalies if a.severity == HDSPSeverity.HIGH)
        medium = sum(1 for a in anomalies if a.severity == HDSPSeverity.MEDIUM)
        low = sum(1 for a in anomalies if a.severity == HDSPSeverity.LOW)

        summary = (
            f"{detection_type} detection: found {len(anomalies)} anomalies "
            f"[{critical} critical, {high} high, {medium} medium, {low} low]"
        )

        return HDSPDetectionResult(
            anomalies=anomalies,
            total_anomalies=len(anomalies),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            detection_timestamp=datetime.utcnow().isoformat(),
            cluster_name=self.detector.cluster_name,
            namespaces_checked=self.detector.namespaces,
            summary=summary,
        )

    def _store_detection_result(self, result: HDSPDetectionResult) -> None:
        """Store detection result in DynamoDB."""
        try:
            # Store summary record
            self.aws_client.put_dynamodb_item(
                table_name=self.config["dynamodb_table"],
                item={
                    "pk": f"HDSP#{result.cluster_name}#{result.detection_timestamp[:10]}",
                    "sk": f"DETECTION#{result.detection_timestamp}",
                    "type": "hdsp_detection",
                    "cluster_name": result.cluster_name,
                    "total_anomalies": result.total_anomalies,
                    "critical_count": result.critical_count,
                    "high_count": result.high_count,
                    "medium_count": result.medium_count,
                    "low_count": result.low_count,
                    "namespaces_checked": result.namespaces_checked,
                    "summary": result.summary,
                    "timestamp": result.detection_timestamp,
                },
            )

            # Store individual critical/high anomalies for tracking
            for anomaly in result.anomalies:
                if anomaly.severity in (HDSPSeverity.CRITICAL, HDSPSeverity.HIGH):
                    signature = (
                        f"hdsp_{anomaly.anomaly_type.value}_"
                        f"{anomaly.namespace}_{anomaly.resource_name}"
                    )
                    self.aws_client.put_dynamodb_item(
                        table_name=self.config["dynamodb_table"],
                        item={
                            "pk": f"ANOMALY#{signature}",
                            "sk": f"HDSP#{anomaly.timestamp}",
                            "type": "hdsp_anomaly",
                            **anomaly.to_dict(),
                        },
                    )

            self.logger.info(
                f"Stored HDSP detection result: {result.total_anomalies} anomalies"
            )

        except Exception as e:
            self.logger.error(f"Failed to store HDSP detection result: {e}")

    def _trigger_analysis(self, result: HDSPDetectionResult) -> None:
        """Publish HDSP anomaly event to EventBridge for downstream analysis."""
        try:
            # Create aggregated anomaly data for analysis
            anomaly_data = {
                "signature": f"hdsp_{result.cluster_name}_{result.detection_timestamp[:10]}",
                "anomaly_type": "k8s_anomaly",
                "service_name": f"hdsp-{result.cluster_name}",
                "agent": "hdsp",
                "cluster_name": result.cluster_name,
                "first_seen": result.detection_timestamp,
                "last_seen": result.detection_timestamp,
                "occurrence_count": result.total_anomalies,
                "severity": self._get_highest_severity(result),
                "summary": result.summary,
                "anomaly_details": [a.to_dict() for a in result.anomalies[:10]],
                "metrics_snapshot": {
                    "total_anomalies": result.total_anomalies,
                    "critical_count": result.critical_count,
                    "high_count": result.high_count,
                    "namespaces": result.namespaces_checked,
                },
            }

            self.aws_client.put_eventbridge_event(
                event_bus=self.config["event_bus"],
                source="cd1-agent.hdsp",
                detail_type="K8s Anomaly Detected",
                detail=anomaly_data,
            )

            self.logger.info(
                f"Analysis triggered for HDSP detection: {anomaly_data['signature']}"
            )

        except Exception as e:
            self.logger.error(f"Failed to trigger HDSP analysis: {e}")

    def _get_highest_severity(self, result: HDSPDetectionResult) -> str:
        """Get the highest severity level from detection result."""
        if result.critical_count > 0:
            return "critical"
        elif result.high_count > 0:
            return "high"
        elif result.medium_count > 0:
            return "medium"
        return "low"


# Lambda entry point
handler_instance = HDSPDetectionHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)
