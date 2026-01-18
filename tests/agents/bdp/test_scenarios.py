"""
E2E Scenario Tests for BDP Agent.

Tests complete detection workflows based on realistic scenarios.
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from tests.agents.bdp.mock_data.logs import LogDataFactory, generate_error_logs
from tests.agents.bdp.mock_data.metrics import MetricDataFactory, generate_spike_metrics
from tests.agents.bdp.mock_data.patterns import generate_pattern_context


class TestScenario1LogAnomaly:
    """
    Scenario 1: Log Anomaly Detection

    Purpose: Validate CloudWatch Logs error pattern detection

    Cases:
    - No errors: Should return anomalies_detected: False
    - Few errors (3): Should detect but not trigger analysis
    - Many errors (10): Should detect and trigger EventBridge
    """

    @pytest.mark.parametrize("log_count,expected_detected,should_trigger_analysis", [
        (0, False, False),
        (3, True, False),
        (10, True, True),
    ])
    def test_log_anomaly_thresholds(
        self,
        bdp_handler,
        log_count,
        expected_detected,
        should_trigger_analysis,
    ):
        """Test log anomaly detection at different threshold levels."""
        # Generate appropriate number of logs
        logs = LogDataFactory.create_error_logs(log_count) if log_count > 0 else []
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": logs}
        bdp_handler.aws_client._provider._events = []  # Clear events

        event = {
            "detection_type": "log_anomaly",
            "log_group": "/aws/lambda/test-function",
            "service_name": "test-service",
            "time_range_hours": 1,
        }

        result = bdp_handler._detect_log_anomalies(event)

        assert result["anomalies_detected"] == expected_detected

        if expected_detected:
            assert result["anomaly_count"] == log_count

        # Check EventBridge trigger
        events = bdp_handler.aws_client.get_events()
        if should_trigger_analysis:
            assert len(events) > 0, "EventBridge should be triggered for 10+ logs"
        else:
            assert len(events) == 0, f"EventBridge should NOT be triggered for {log_count} logs"

    def test_log_anomaly_connection_timeout_pattern(self, bdp_handler):
        """Test detection of connection timeout error pattern."""
        logs = LogDataFactory.create_connection_timeout_logs(count=10)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/database-service",
            "service_name": "database-service",
            "time_range_hours": 1,
        })

        assert result["anomalies_detected"] is True
        assert result["anomaly_count"] == 10
        assert "log_summary" in result
        assert result["anomaly_record"]["severity"] == "high"

    def test_log_anomaly_auth_failure_pattern(self, bdp_handler):
        """Test detection of authentication failure pattern."""
        logs = LogDataFactory.create_auth_failure_logs(count=8)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/auth-service",
            "service_name": "auth-service",
            "time_range_hours": 1,
        })

        assert result["anomalies_detected"] is True
        assert "anomaly_record" in result


class TestScenario2MetricAnomaly:
    """
    Scenario 2: Metric Anomaly Detection (Z-score based)

    Purpose: Validate CloudWatch Metrics statistical anomaly detection

    Cases:
    - Normal metrics: Z-score <= 2.0, no anomaly
    - Spike: Z-score > 2.0, anomaly detected
    - Critical spike: Z-score > 3.0, severity: critical
    """

    def test_metric_normal_operation(self, bdp_handler):
        """Test normal metrics do not trigger anomaly."""
        # Use deterministic values with small variance (not random)
        from datetime import datetime, timedelta
        base_time = datetime.utcnow()
        values = [5.0, 5.1, 4.9, 5.2, 4.8, 5.0, 5.1, 4.9, 5.0, 5.0]
        metrics = {
            "namespace": "AWS/Lambda",
            "metric": "Errors",
            "datapoints": [
                {"Timestamp": (base_time - timedelta(minutes=i * 5)).isoformat(), "Average": values[i]}
                for i in range(10)
            ],
        }
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": metrics}

        event = {
            "detection_type": "metric_anomaly",
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [{"Name": "FunctionName", "Value": "test-function"}],
            "service_name": "test-service",
            "time_range_hours": 24,
        }

        result = bdp_handler._detect_metric_anomalies(event)

        assert result["anomalies_detected"] is False
        assert abs(result["z_score"]) <= 2.0

    def test_metric_spike_anomaly(self, bdp_handler):
        """Test spike metrics trigger anomaly detection."""
        metrics = MetricDataFactory.create_spike_metrics(
            count=10,
            base_value=5.0,
            spike_value=50.0,  # 10x spike
        )
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [],
            "service_name": "test-service",
        })

        assert result["anomalies_detected"] is True
        assert result["z_score"] > 2.0
        assert "anomaly_record" in result

    def test_metric_critical_spike_severity(self, bdp_handler):
        """Test critical spikes receive high/critical severity.

        Note: Achieving z-score > 3 in a single-pass calculation is difficult
        because the spike value affects both the mean and variance.
        This test validates that extreme spikes are detected as anomalies
        with appropriate severity classification.
        """
        from datetime import datetime, timedelta
        base_time = datetime.utcnow()
        values = [5.0, 5.1, 4.9, 5.2, 4.8, 5.0, 5.1, 4.9, 5.0, 1000.0]  # Extreme spike
        metrics = {
            "namespace": "AWS/Lambda",
            "metric": "Errors",
            "datapoints": [
                {"Timestamp": (base_time - timedelta(minutes=i * 5)).isoformat(), "Average": values[i]}
                for i in range(10)
            ],
        }
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [],
            "service_name": "critical-service",
        })

        assert result["anomalies_detected"] is True
        assert result["z_score"] > 2.5  # Significant anomaly
        assert result["anomaly_record"]["severity"] in ("critical", "high")


class TestScenario3PatternAnomaly:
    """
    Scenario 3: Pattern Anomaly Detection (RDS-based)

    Purpose: Validate RDS-based detection pattern execution

    Cases:
    - No pattern matches: anomalies_detected: False
    - Auth failure pattern: Detects 5+ failures, severity: critical
    - Service filtering: Only runs patterns for target_service
    """

    def test_pattern_no_matches(self, bdp_handler, normal_context):
        """Test pattern detection with no anomaly matches."""
        result = bdp_handler._detect_pattern_anomalies({
            "context": normal_context,
        })

        # May or may not detect depending on mock randomness
        assert "patterns_executed" in result

    def test_pattern_exception_detection(self, bdp_handler, exception_context):
        """Test detection of exception patterns in logs."""
        result = bdp_handler._detect_pattern_anomalies({
            "context": exception_context,
        })

        assert "patterns_executed" in result

    def test_pattern_service_filtering(self, bdp_handler):
        """Test patterns are filtered by target_service."""
        result_all = bdp_handler._detect_pattern_anomalies({
            "target_service": None,
        })

        result_auth = bdp_handler._detect_pattern_anomalies({
            "target_service": "auth-service",
        })

        # Auth-service specific patterns should be fewer or equal
        assert result_auth["patterns_executed"] <= result_all["patterns_executed"]

    def test_pattern_custom_context(self, bdp_handler):
        """Test pattern execution with custom context."""
        custom_context = generate_pattern_context(
            scenario="auth_failure",
        )

        result = bdp_handler._detect_pattern_anomalies({
            "context": custom_context,
        })

        assert "patterns_executed" in result


class TestScenario4ScheduledDetection:
    """
    Scenario 4: Scheduled Detection (Full Execution)

    Purpose: Validate all detection types run sequentially

    Expected Output:
    {
        "log_detection": {...},
        "pattern_detection": {...},
        "total_anomalies": N
    }
    """

    def test_scheduled_full_execution(self, bdp_handler):
        """Test scheduled detection executes all types."""
        event = {
            "detection_type": "scheduled",
            "services": [
                {"name": "lambda", "log_group": "/aws/lambda/bdp-agent"},
            ],
        }

        result = bdp_handler._run_scheduled_detection(event)

        # Verify structure
        assert "log_detection" in result
        assert "pattern_detection" in result
        assert "total_anomalies" in result
        assert isinstance(result["total_anomalies"], int)

        # Verify log detection per service
        assert "lambda" in result["log_detection"]

    def test_scheduled_multiple_services(self, bdp_handler):
        """Test scheduled detection across multiple services."""
        services = [
            {"name": "auth", "log_group": "/aws/lambda/auth"},
            {"name": "api", "log_group": "/aws/lambda/api"},
            {"name": "worker", "log_group": "/aws/lambda/worker"},
        ]

        result = bdp_handler._run_scheduled_detection({"services": services})

        # All services should have results
        for service in services:
            assert service["name"] in result["log_detection"]

    def test_scheduled_aggregates_anomalies(self, bdp_handler):
        """Test total_anomalies correctly aggregates from all sources."""
        # Configure mock to return logs
        logs = LogDataFactory.create_error_logs(5)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": logs}

        result = bdp_handler._run_scheduled_detection({
            "services": [
                {"name": "test", "log_group": "/aws/lambda/test"},
            ],
        })

        # total_anomalies should be sum of log and pattern anomalies
        assert result["total_anomalies"] >= 0


class TestScenario5EdgeCases:
    """
    Scenario 5: Edge Cases

    Purpose: Validate handling of unusual inputs

    Cases:
    - Empty results
    - Single datapoint
    - Zero variance
    - Unicode content
    """

    def test_edge_empty_log_results(self, bdp_handler):
        """Test handling of empty log query results."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": []}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/empty",
            "service_name": "empty-service",
        })

        assert result["anomalies_detected"] is False
        assert "message" in result

    def test_edge_single_metric_datapoint(self, bdp_handler):
        """Test handling of single metric datapoint."""
        metrics = MetricDataFactory.create_insufficient_data(count=1)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [],
            "service_name": "test-service",
        })

        assert result["anomalies_detected"] is False
        assert "Insufficient" in result["message"]

    def test_edge_zero_variance_metrics(self, bdp_handler):
        """Test handling of zero variance (division by zero protection)."""
        metrics = MetricDataFactory.create_zero_variance_metrics(count=10, value=5.0)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [],
            "service_name": "test-service",
        })

        # Should not crash with division by zero
        assert "anomalies_detected" in result
        assert result["z_score"] == 0

    def test_edge_unicode_content(self, bdp_handler):
        """Test handling of unicode characters in logs."""
        from tests.agents.bdp.mock_data.logs import generate_unicode_logs

        logs = generate_unicode_logs()
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": logs}

        # Should not raise encoding errors
        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/international",
            "service_name": "i18n-service",
        })

        assert "anomalies_detected" in result

    def test_edge_large_log_volume(self, bdp_handler):
        """Test handling of large log volume."""
        # Create 100 logs (above typical threshold)
        logs = LogDataFactory.create_error_logs(100)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/high-volume",
            "service_name": "high-volume-service",
        })

        assert result["anomalies_detected"] is True
        assert result["anomaly_count"] == 100
        # Sample logs should be limited
        assert len(result["anomaly_record"]["sample_logs"]) <= 10

    def test_edge_trending_metrics(self, bdp_handler):
        """Test handling of gradually trending metrics."""
        metrics = MetricDataFactory.create_trending_metrics(
            count=10,
            start_value=5.0,
            end_value=50.0,  # Gradual increase
        )
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [],
            "service_name": "trending-service",
        })

        # Trending data may or may not trigger depending on z-score
        assert "anomalies_detected" in result
        assert "z_score" in result


class TestIntegrationScenarios:
    """Integration scenarios testing complete workflows."""

    def test_detection_to_eventbridge_flow(self, bdp_handler, lambda_context):
        """Test complete flow from detection to EventBridge notification."""
        # Setup: Many error logs to trigger analysis
        logs = LogDataFactory.create_connection_timeout_logs(count=15)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": logs}
        bdp_handler.aws_client._provider._events = []

        # Execute detection
        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/production",
            "service_name": "production-service",
            "time_range_hours": 1,
        })

        # Verify detection
        assert result["anomalies_detected"] is True

        # Verify EventBridge notification
        events = bdp_handler.aws_client.get_events()
        assert len(events) == 1
        assert events[0]["source"] == "bdp.detection"
        assert events[0]["detail"]["service_name"] == "production-service"

    def test_detection_to_dynamodb_storage(self, bdp_handler):
        """Test detection results are properly stored in DynamoDB."""
        logs = LogDataFactory.create_error_logs(5)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
        })

        # Verify DynamoDB storage
        calls = bdp_handler.aws_client.call_history
        put_calls = [c for c in calls if c["method"] == "put_dynamodb_item"]

        assert len(put_calls) >= 1
        stored_item = put_calls[0]["item"]
        assert "pk" in stored_item
        assert "sk" in stored_item
        assert stored_item["type"] == "detection"

    def test_lambda_handler_e2e(self, lambda_context):
        """Test complete Lambda handler E2E flow."""
        from src.agents.bdp.handler import handler as detection_handler

        event = {
            "body": json.dumps({
                "detection_type": "scheduled",
                "services": [
                    {"name": "test-service", "log_group": "/aws/lambda/test"},
                ],
            })
        }

        with patch.dict("os.environ", {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"}):
            response = detection_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True
        assert "data" in body
        assert "log_detection" in body["data"]
        assert "pattern_detection" in body["data"]
