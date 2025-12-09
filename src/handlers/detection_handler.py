"""
Detection Handler for Anomaly Detection Lambda.

Entry point for anomaly detection and log summarization.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.handlers.base_handler import BaseHandler
from src.services.llm_client import LLMClient, LLMProvider
from src.services.aws_client import AWSClient, AWSProvider
from src.services.cost_anomaly_detector import CostAnomalyDetector
from src.services.cost_explorer_client import CostExplorerClient
from src.prompts.detection_prompts import build_log_summarization_prompt


class DetectionHandler(BaseHandler):
    """
    Lambda handler for anomaly detection.

    Processes incoming logs and metrics to detect anomalies.
    Triggers analysis workflow when anomalies are detected.
    """

    def __init__(self):
        super().__init__("DetectionHandler")
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize service clients based on configuration."""
        llm_provider = LLMProvider(self.config["llm_provider"])
        aws_provider = AWSProvider(self.config["aws_provider"])

        self.llm_client = LLMClient(provider=llm_provider)
        self.aws_client = AWSClient(provider=aws_provider)
        self.cost_detector = CostAnomalyDetector(sensitivity=0.7)
        self.cost_client = CostExplorerClient(
            use_mock=(aws_provider == AWSProvider.MOCK)
        )

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """Validate detection event."""
        body = self._parse_body(event)

        detection_type = body.get("detection_type", event.get("detection_type"))
        if not detection_type:
            return "Missing required field: detection_type"

        valid_types = ["log_anomaly", "metric_anomaly", "cost_anomaly", "scheduled"]
        if detection_type not in valid_types:
            return f"Invalid detection_type. Must be one of: {valid_types}"

        return None

    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """Process detection request."""
        body = self._parse_body(event)
        detection_type = body.get("detection_type", event.get("detection_type", "log_anomaly"))

        self.logger.info(f"Processing detection type: {detection_type}")

        if detection_type == "log_anomaly":
            return self._detect_log_anomalies(body)
        elif detection_type == "metric_anomaly":
            return self._detect_metric_anomalies(body)
        elif detection_type == "cost_anomaly":
            return self._detect_cost_anomalies(body)
        elif detection_type == "scheduled":
            return self._run_scheduled_detection(body)
        else:
            raise ValueError(f"Unsupported detection type: {detection_type}")

    def _detect_log_anomalies(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Detect anomalies in log data."""
        log_group = body.get("log_group", "/aws/lambda/default")
        time_range_hours = body.get("time_range_hours", 1)
        service_name = body.get("service_name", "unknown")

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=time_range_hours)

        # Query logs
        query = """
        fields @timestamp, @message, @logStream
        | filter @message like /(?i)(error|exception|failed|timeout)/
        | sort @timestamp desc
        | limit 100
        """

        logs = self.aws_client.query_cloudwatch_logs(
            log_group=log_group,
            query=query,
            start_time=start_time,
            end_time=end_time,
        )

        if not logs:
            return {
                "anomalies_detected": False,
                "message": "No error patterns found in logs",
                "service_name": service_name,
                "time_range": f"{start_time.isoformat()} to {end_time.isoformat()}",
            }

        # Summarize logs
        log_summary = self._summarize_logs(logs)

        # Create anomaly record
        anomaly_record = self._create_log_anomaly_record(
            service_name=service_name,
            logs=logs,
            summary=log_summary,
        )

        # Store result
        self._store_detection_result(anomaly_record)

        # Trigger analysis if significant
        if len(logs) >= 5:
            self._trigger_analysis(anomaly_record)

        return {
            "anomalies_detected": True,
            "anomaly_count": len(logs),
            "anomaly_record": anomaly_record,
            "log_summary": log_summary,
        }

    def _detect_metric_anomalies(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Detect anomalies in CloudWatch metrics."""
        namespace = body.get("namespace", "AWS/Lambda")
        metric_name = body.get("metric_name", "Errors")
        dimensions = body.get("dimensions", [])
        service_name = body.get("service_name", "unknown")
        time_range_hours = body.get("time_range_hours", 24)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=time_range_hours)

        # Get metrics
        metrics = self.aws_client.get_cloudwatch_metrics(
            namespace=namespace,
            metric_name=metric_name,
            dimensions=dimensions,
            start_time=start_time,
            end_time=end_time,
            period=300,
        )

        datapoints = metrics.get("datapoints", [])
        if len(datapoints) < 2:
            return {
                "anomalies_detected": False,
                "message": "Insufficient metric data points",
                "service_name": service_name,
            }

        # Simple anomaly detection using standard deviation
        values = [dp.get("Average", 0) for dp in datapoints]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        stddev = variance ** 0.5

        latest_value = values[-1]
        z_score = (latest_value - mean) / stddev if stddev > 0 else 0

        is_anomaly = abs(z_score) > 2.0

        result = {
            "anomalies_detected": is_anomaly,
            "service_name": service_name,
            "metric_name": metric_name,
            "current_value": latest_value,
            "mean": mean,
            "stddev": stddev,
            "z_score": z_score,
        }

        if is_anomaly:
            anomaly_record = self._create_metric_anomaly_record(
                service_name=service_name,
                metric_name=metric_name,
                current_value=latest_value,
                mean=mean,
                z_score=z_score,
            )
            self._store_detection_result(anomaly_record)
            self._trigger_analysis(anomaly_record)
            result["anomaly_record"] = anomaly_record

        return result

    def _detect_cost_anomalies(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Detect cost anomalies using Luminol detector."""
        days = body.get("days", 30)

        # Get historical cost data
        cost_data = self.cost_client.get_historical_costs_for_detector(days=days)

        if not cost_data:
            return {
                "anomalies_detected": False,
                "message": "No cost data available",
            }

        # Run anomaly detection
        results = self.cost_detector.analyze_batch(cost_data)

        # Filter to actual anomalies
        anomalies = [r for r in results if r.is_anomaly]

        if not anomalies:
            return {
                "anomalies_detected": False,
                "message": "No cost anomalies detected",
                "services_analyzed": len(results),
            }

        # Create anomaly records for each
        anomaly_records = []
        for anomaly in anomalies[:5]:  # Limit to top 5
            record = self._create_cost_anomaly_record(anomaly)
            self._store_detection_result(record)
            anomaly_records.append(record)

        # Trigger analysis for critical anomalies
        critical = [a for a in anomalies if a.severity in ("critical", "high")]
        if critical:
            self._trigger_analysis(anomaly_records[0])

        return {
            "anomalies_detected": True,
            "anomaly_count": len(anomalies),
            "anomaly_records": anomaly_records,
            "services_analyzed": len(results),
        }

    def _run_scheduled_detection(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Run all detection types on schedule."""
        results = {
            "log_detection": {},
            "metric_detection": {},
            "cost_detection": {},
            "total_anomalies": 0,
        }

        # Get services to check from config or body
        services = body.get("services", [
            {"name": "lambda", "log_group": "/aws/lambda/bdp-agent"},
        ])

        # Log detection for each service
        for service in services:
            try:
                log_result = self._detect_log_anomalies({
                    "service_name": service["name"],
                    "log_group": service.get("log_group", f"/aws/lambda/{service['name']}"),
                    "time_range_hours": 1,
                })
                results["log_detection"][service["name"]] = log_result
                if log_result.get("anomalies_detected"):
                    results["total_anomalies"] += log_result.get("anomaly_count", 0)
            except Exception as e:
                self.logger.error(f"Log detection failed for {service['name']}: {e}")
                results["log_detection"][service["name"]] = {"error": str(e)}

        # Cost detection
        try:
            cost_result = self._detect_cost_anomalies({"days": 30})
            results["cost_detection"] = cost_result
            if cost_result.get("anomalies_detected"):
                results["total_anomalies"] += cost_result.get("anomaly_count", 0)
        except Exception as e:
            self.logger.error(f"Cost detection failed: {e}")
            results["cost_detection"] = {"error": str(e)}

        return results

    def _summarize_logs(self, logs: List[Dict[str, Any]]) -> str:
        """Summarize logs using LLM."""
        prompt = build_log_summarization_prompt(
            logs=logs,
            max_summary_tokens=500,
            focus_areas=["errors", "patterns", "timing"],
        )

        summary = self.llm_client.generate(
            prompt=prompt,
            temperature=0.3,
            max_tokens=600,
        )

        return summary

    def _create_log_anomaly_record(
        self,
        service_name: str,
        logs: List[Dict[str, Any]],
        summary: str,
    ) -> Dict[str, Any]:
        """Create standardized log anomaly record."""
        now = datetime.utcnow().isoformat()
        signature = f"log_{service_name}_{now[:10]}"

        return {
            "signature": signature,
            "anomaly_type": "log_pattern",
            "service_name": service_name,
            "first_seen": logs[-1].get("@timestamp", now) if logs else now,
            "last_seen": logs[0].get("@timestamp", now) if logs else now,
            "occurrence_count": len(logs),
            "sample_logs": logs[:10],
            "metrics_snapshot": {},
            "severity": "high" if len(logs) >= 10 else "medium",
            "summary": summary,
        }

    def _create_metric_anomaly_record(
        self,
        service_name: str,
        metric_name: str,
        current_value: float,
        mean: float,
        z_score: float,
    ) -> Dict[str, Any]:
        """Create standardized metric anomaly record."""
        now = datetime.utcnow().isoformat()
        signature = f"metric_{service_name}_{metric_name}_{now[:10]}"

        severity = "critical" if abs(z_score) > 3 else "high" if abs(z_score) > 2.5 else "medium"

        return {
            "signature": signature,
            "anomaly_type": "metric_anomaly",
            "service_name": service_name,
            "first_seen": now,
            "last_seen": now,
            "occurrence_count": 1,
            "sample_logs": [],
            "metrics_snapshot": {
                "metric_name": metric_name,
                "current_value": current_value,
                "mean": mean,
                "z_score": z_score,
            },
            "severity": severity,
        }

    def _create_cost_anomaly_record(self, anomaly) -> Dict[str, Any]:
        """Create standardized cost anomaly record from detector result."""
        return {
            "signature": f"cost_{anomaly.service_name}_{anomaly.timestamp[:10]}",
            "anomaly_type": "cost_anomaly",
            "service_name": anomaly.service_name,
            "first_seen": anomaly.timestamp,
            "last_seen": anomaly.timestamp,
            "occurrence_count": 1,
            "sample_logs": [],
            "metrics_snapshot": {
                "current_cost": anomaly.current_value,
                "previous_cost": anomaly.previous_value,
                "change_ratio": anomaly.change_ratio,
                "confidence_score": anomaly.confidence_score,
                "detected_methods": anomaly.detected_methods,
            },
            "severity": anomaly.severity,
            "analysis": anomaly.analysis,
        }

    def _store_detection_result(self, record: Dict[str, Any]) -> None:
        """Store detection result in DynamoDB."""
        try:
            self.aws_client.put_dynamodb_item(
                table_name=self.config["dynamodb_table"],
                item={
                    "pk": f"ANOMALY#{record['signature']}",
                    "sk": f"DETECTION#{record['last_seen']}",
                    "type": "detection",
                    **record,
                },
            )
        except Exception as e:
            self.logger.error(f"Failed to store detection result: {e}")

    def _trigger_analysis(self, anomaly_record: Dict[str, Any]) -> None:
        """Publish anomaly event to EventBridge for downstream processing.

        Note: This uses EventBridge for event publishing (not scheduling).
        The Lambda itself is triggered by MWAA (Airflow DAG).
        """
        try:
            self.aws_client.put_eventbridge_event(
                event_bus=self.config["event_bus"],
                source="bdp.detection",
                detail_type="AnomalyDetected",
                detail=anomaly_record,
            )
            self.logger.info(f"Analysis triggered for {anomaly_record['signature']}")
        except Exception as e:
            self.logger.error(f"Failed to trigger analysis: {e}")


# Lambda entry point
handler_instance = DetectionHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)
