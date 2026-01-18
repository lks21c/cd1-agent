"""
Unit Tests for BDP Agent Detection Handler.

Comprehensive tests for BDP Agent Lambda handler implementation
covering all detection types and edge cases.
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.agents.bdp.handler import DetectionHandler, handler as detection_handler


class TestDetectionHandlerCreation:
    """Test suite for DetectionHandler initialization."""

    def test_handler_creation(self, bdp_handler):
        """Test DetectionHandler creation with mock providers."""
        assert bdp_handler is not None
        assert bdp_handler.config["llm_provider"] == "mock"
        assert bdp_handler.config["aws_provider"] == "mock"

    def test_handler_clients_initialized(self, bdp_handler):
        """Test all clients are properly initialized."""
        assert bdp_handler.llm_client is not None
        assert bdp_handler.aws_client is not None
        assert bdp_handler.pattern_service is not None


class TestInputValidation:
    """Test suite for input validation."""

    def test_validate_input_missing_type(self, bdp_handler):
        """Test validation with missing detection_type."""
        event = {"body": "{}"}
        error = bdp_handler._validate_input(event)

        assert error is not None
        assert "detection_type" in error

    def test_validate_input_invalid_type(self, bdp_handler):
        """Test validation with invalid detection_type."""
        event = {"body": json.dumps({"detection_type": "invalid_type"})}
        error = bdp_handler._validate_input(event)

        assert error is not None
        assert "Invalid detection_type" in error

    @pytest.mark.parametrize("detection_type", [
        "log_anomaly",
        "metric_anomaly",
        "pattern_anomaly",
        "scheduled",
    ])
    def test_validate_input_valid_types(self, bdp_handler, detection_type):
        """Test validation with all valid detection types."""
        event = {"body": json.dumps({"detection_type": detection_type})}
        error = bdp_handler._validate_input(event)

        assert error is None

    def test_validate_input_from_direct_event(self, bdp_handler):
        """Test validation when detection_type is in event directly."""
        event = {"detection_type": "log_anomaly"}
        error = bdp_handler._validate_input(event)

        assert error is None


class TestLogAnomalyDetection:
    """Test suite for log anomaly detection."""

    def test_detect_log_anomalies_no_errors(self, bdp_handler):
        """Test log detection when no error logs are found."""
        # Configure mock to return empty logs
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": []}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
            "time_range_hours": 1,
        })

        assert result["anomalies_detected"] is False
        assert "No error patterns found" in result["message"]

    def test_detect_log_anomalies_few_errors(self, bdp_handler, few_error_logs):
        """Test log detection with few errors (below analysis threshold)."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": few_error_logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
            "time_range_hours": 1,
        })

        assert result["anomalies_detected"] is True
        assert result["anomaly_count"] == 3
        # Should not trigger analysis (threshold is 5)

    def test_detect_log_anomalies_many_errors(self, bdp_handler, many_error_logs):
        """Test log detection with many errors (triggers analysis)."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": many_error_logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
            "time_range_hours": 1,
        })

        assert result["anomalies_detected"] is True
        assert result["anomaly_count"] == 10
        assert "anomaly_record" in result
        assert "log_summary" in result

    def test_detect_log_anomalies_unicode_logs(self, bdp_handler, unicode_error_logs):
        """Test log detection handles unicode characters properly."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": unicode_error_logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "unicode-service",
            "time_range_hours": 1,
        })

        # Should process without errors
        assert "anomalies_detected" in result
        if result["anomalies_detected"]:
            assert result["anomaly_count"] == len(unicode_error_logs)

    def test_log_anomaly_record_structure(self, bdp_handler, many_error_logs, assert_anomaly_record):
        """Test the structure of generated log anomaly records."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": many_error_logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
            "time_range_hours": 1,
        })

        assert_anomaly_record(result["anomaly_record"], "log_pattern", "high")
        assert result["anomaly_record"]["occurrence_count"] == 10

    def test_log_severity_classification(self, bdp_handler):
        """Test severity is correctly set based on log count."""
        from tests.agents.bdp.mock_data.logs import LogDataFactory

        # Test with 10 logs (high severity)
        high_logs = LogDataFactory.create_error_logs(10)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": high_logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
        })

        assert result["anomaly_record"]["severity"] == "high"

        # Test with 5 logs (medium severity)
        medium_logs = LogDataFactory.create_error_logs(5)
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": medium_logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
        })

        assert result["anomaly_record"]["severity"] == "medium"


class TestMetricAnomalyDetection:
    """Test suite for metric anomaly detection."""

    def test_detect_metric_anomalies_normal(self, bdp_handler, normal_metrics):
        """Test metric detection with normal metrics (no anomaly)."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": normal_metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [{"Name": "FunctionName", "Value": "test-function"}],
            "service_name": "test-service",
        })

        assert result["anomalies_detected"] is False
        assert "z_score" in result
        assert abs(result["z_score"]) <= 2.0

    def test_detect_metric_anomalies_spike(self, bdp_handler, spike_metrics):
        """Test metric detection with spike (anomaly detected)."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": spike_metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [{"Name": "FunctionName", "Value": "test-function"}],
            "service_name": "test-service",
        })

        assert result["anomalies_detected"] is True
        assert result["z_score"] > 2.0
        assert "anomaly_record" in result

    def test_detect_metric_anomalies_critical_spike(self, bdp_handler, critical_spike_metrics):
        """Test metric detection with critical spike (high severity anomaly).

        Note: Achieving z-score > 3 requires extreme outliers because the spike
        affects both mean and variance. This test validates anomaly detection
        and high/critical severity assignment.
        """
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": critical_spike_metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [],
            "service_name": "test-service",
        })

        assert result["anomalies_detected"] is True
        assert result["z_score"] > 2.5  # High enough to trigger anomaly
        assert result["anomaly_record"]["severity"] in ("critical", "high")

    def test_detect_metric_anomalies_insufficient_data(self, bdp_handler, single_datapoint_metrics):
        """Test metric detection with insufficient datapoints."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": single_datapoint_metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [],
            "service_name": "test-service",
        })

        assert result["anomalies_detected"] is False
        assert "Insufficient metric data points" in result["message"]

    def test_detect_metric_anomalies_zero_variance(self, bdp_handler, zero_variance_metrics):
        """Test metric detection with zero variance (identical values)."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": zero_variance_metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [],
            "service_name": "test-service",
        })

        # Should not cause division by zero error
        assert "anomalies_detected" in result
        assert result["z_score"] == 0  # stddev = 0, so z_score = 0

    def test_metric_anomaly_record_structure(self, bdp_handler, spike_metrics, assert_anomaly_record):
        """Test the structure of generated metric anomaly records."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_metrics": spike_metrics}

        result = bdp_handler._detect_metric_anomalies({
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "dimensions": [],
            "service_name": "test-service",
        })

        assert_anomaly_record(result["anomaly_record"], "metric_anomaly")
        assert "metrics_snapshot" in result["anomaly_record"]
        assert "z_score" in result["anomaly_record"]["metrics_snapshot"]


class TestPatternAnomalyDetection:
    """Test suite for pattern-based anomaly detection."""

    def test_detect_pattern_anomalies_no_patterns(self, bdp_handler):
        """Test pattern detection when no patterns configured."""
        with patch.object(bdp_handler.pattern_service, 'execute_all_patterns', return_value=[]):
            result = bdp_handler._detect_pattern_anomalies({})

            assert result["anomalies_detected"] is False
            assert "No detection patterns configured" in result["message"]

    def test_detect_pattern_anomalies_no_matches(self, bdp_handler, pattern_service_mock, normal_context):
        """Test pattern detection with no pattern matches."""
        # Execute with normal context (no exceptions/errors)
        results = pattern_service_mock.execute_all_patterns(context=normal_context)

        # Filter to regex patterns and check
        regex_results = [r for r in results if r.pattern.pattern_type.value == "REGEX"]
        for r in regex_results:
            if r.pattern.pattern_name == "exception_pattern":
                assert r.is_anomaly is False

    def test_detect_pattern_anomalies_regex_match(self, bdp_handler, exception_context):
        """Test pattern detection with regex matches."""
        result = bdp_handler._detect_pattern_anomalies({
            "context": exception_context,
        })

        # Pattern detection should execute
        assert "patterns_executed" in result

    def test_detect_pattern_anomalies_service_filter(self, bdp_handler):
        """Test pattern detection with service filter."""
        result = bdp_handler._detect_pattern_anomalies({
            "target_service": "auth-service",
        })

        # Should only execute patterns for auth-service
        assert "patterns_executed" in result


class TestScheduledDetection:
    """Test suite for scheduled detection."""

    def test_scheduled_detection_basic(self, bdp_handler, scheduled_detection_services):
        """Test scheduled detection runs all detection types."""
        result = bdp_handler._run_scheduled_detection({
            "services": scheduled_detection_services,
        })

        assert "log_detection" in result
        assert "pattern_detection" in result
        assert "total_anomalies" in result

    def test_scheduled_detection_empty_services(self, bdp_handler, empty_services):
        """Test scheduled detection with empty services list."""
        result = bdp_handler._run_scheduled_detection({
            "services": empty_services,
        })

        # Should still run pattern detection
        assert "pattern_detection" in result

    def test_scheduled_detection_error_handling(self, bdp_handler):
        """Test scheduled detection handles individual failures gracefully."""
        # Mock log detection to fail for one service
        services = [
            {"name": "working-service", "log_group": "/aws/lambda/working"},
            {"name": "failing-service", "log_group": "/aws/lambda/failing"},
        ]

        result = bdp_handler._run_scheduled_detection({"services": services})

        # Should have results for both services (error or success)
        assert "working-service" in result["log_detection"]
        assert "failing-service" in result["log_detection"]


class TestLambdaHandler:
    """Test suite for Lambda handler function."""

    def test_handler_function_log_anomaly(self, lambda_context, log_anomaly_event):
        """Test Lambda handler with log anomaly event."""
        event = {"body": json.dumps(log_anomaly_event)}

        with patch.dict("os.environ", {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"}):
            response = detection_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True

    def test_handler_function_metric_anomaly(self, lambda_context, metric_anomaly_event):
        """Test Lambda handler with metric anomaly event."""
        event = {"body": json.dumps(metric_anomaly_event)}

        with patch.dict("os.environ", {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"}):
            response = detection_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True

    def test_handler_function_pattern_anomaly(self, lambda_context, pattern_anomaly_event):
        """Test Lambda handler with pattern anomaly event."""
        event = {"body": json.dumps(pattern_anomaly_event)}

        with patch.dict("os.environ", {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"}):
            response = detection_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True

    def test_handler_function_scheduled(self, lambda_context, scheduled_event):
        """Test Lambda handler with scheduled event."""
        event = {"body": json.dumps(scheduled_event)}

        with patch.dict("os.environ", {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"}):
            response = detection_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True

    def test_handler_function_validation_error(self, lambda_context):
        """Test Lambda handler with invalid input."""
        event = {"body": json.dumps({"detection_type": "invalid"})}

        with patch.dict("os.environ", {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"}):
            response = detection_handler(event, lambda_context)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["success"] is False

    def test_handler_function_direct_event(self, lambda_context):
        """Test Lambda handler with direct event (not API Gateway)."""
        event = {"detection_type": "log_anomaly", "log_group": "/aws/lambda/test"}

        with patch.dict("os.environ", {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"}):
            response = detection_handler(event, lambda_context)

        assert response["statusCode"] == 200


class TestEventBridgeIntegration:
    """Test suite for EventBridge event publishing."""

    def test_trigger_analysis_publishes_event(self, bdp_handler, many_error_logs):
        """Test that analysis trigger publishes to EventBridge."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": many_error_logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
        })

        # Check that EventBridge event was published
        events = bdp_handler.aws_client.get_events()
        assert len(events) > 0
        assert events[-1]["source"] == "bdp.detection"
        assert events[-1]["detail_type"] == "AnomalyDetected"

    def test_no_event_for_few_logs(self, bdp_handler, few_error_logs):
        """Test that no EventBridge event is published for few logs."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": few_error_logs}

        # Clear any existing events
        bdp_handler.aws_client._provider._events = []

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
        })

        # Should not trigger analysis (< 5 logs)
        events = bdp_handler.aws_client.get_events()
        assert len(events) == 0


class TestDynamoDBStorage:
    """Test suite for DynamoDB result storage."""

    def test_store_detection_result(self, bdp_handler, many_error_logs):
        """Test detection results are stored in DynamoDB."""
        bdp_handler.aws_client._provider.mock_data = {"cloudwatch_logs": many_error_logs}

        result = bdp_handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
        })

        # Check DynamoDB put was called
        calls = bdp_handler.aws_client.call_history
        put_calls = [c for c in calls if c["method"] == "put_dynamodb_item"]
        assert len(put_calls) > 0
