"""
BDP Agent Test Configuration and Fixtures.

Specialized fixtures for BDP (Business Detection Pattern) agent tests.
"""

import json
import os
import pytest
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import patch, MagicMock

# Ensure mock providers for testing
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("AWS_PROVIDER", "mock")
os.environ.setdefault("RDS_PROVIDER", "mock")


# ============================================================================
# Handler Fixtures
# ============================================================================


@pytest.fixture
def bdp_handler():
    """Create BDP DetectionHandler with mock providers."""
    with patch.dict(
        "os.environ",
        {
            "LLM_PROVIDER": "mock",
            "AWS_PROVIDER": "mock",
            "RDS_PROVIDER": "mock",
        },
    ):
        from src.agents.bdp.handler import DetectionHandler
        return DetectionHandler()


@pytest.fixture
def bdp_handler_with_custom_aws(mock_cloudwatch_logs, mock_cloudwatch_metrics):
    """Create BDP handler with customizable AWS mock data."""
    with patch.dict(
        "os.environ",
        {
            "LLM_PROVIDER": "mock",
            "AWS_PROVIDER": "mock",
            "RDS_PROVIDER": "mock",
        },
    ):
        from src.agents.bdp.handler import DetectionHandler
        from src.common.services.aws_client import AWSClient, AWSProvider

        handler = DetectionHandler()

        # Inject custom mock data
        handler.aws_client._provider.mock_data = {
            "cloudwatch_logs": mock_cloudwatch_logs,
            "cloudwatch_metrics": mock_cloudwatch_metrics,
        }

        return handler


# ============================================================================
# Log Anomaly Fixtures
# ============================================================================


@pytest.fixture
def empty_logs() -> List[Dict[str, Any]]:
    """Return empty log list for no-error scenario."""
    return []


@pytest.fixture
def few_error_logs() -> List[Dict[str, Any]]:
    """Return few error logs (below threshold)."""
    base_time = datetime.utcnow()
    return [
        {
            "@timestamp": (base_time - timedelta(minutes=i)).isoformat(),
            "@message": f"ERROR: Test error message {i}",
            "@logStream": "test-stream-1",
        }
        for i in range(3)
    ]


@pytest.fixture
def many_error_logs() -> List[Dict[str, Any]]:
    """Return many error logs (above threshold for analysis trigger)."""
    base_time = datetime.utcnow()
    return [
        {
            "@timestamp": (base_time - timedelta(minutes=i)).isoformat(),
            "@message": f"ERROR: Connection timeout - attempt {i}",
            "@logStream": f"test-stream-{i % 3}",
        }
        for i in range(10)
    ]


@pytest.fixture
def unicode_error_logs() -> List[Dict[str, Any]]:
    """Return logs with unicode characters for edge case testing."""
    base_time = datetime.utcnow()
    return [
        {
            "@timestamp": base_time.isoformat(),
            "@message": "ERROR: 데이터베이스 연결 실패 - タイムアウト 🔥",
            "@logStream": "unicode-stream",
        },
        {
            "@timestamp": (base_time - timedelta(minutes=1)).isoformat(),
            "@message": "Exception: 사용자 인증 오류 - émoji test 💥",
            "@logStream": "unicode-stream",
        },
    ]


@pytest.fixture
def mock_cloudwatch_logs(few_error_logs) -> List[Dict[str, Any]]:
    """Default mock CloudWatch logs (configurable via parametrize)."""
    return few_error_logs


# ============================================================================
# Metric Anomaly Fixtures
# ============================================================================


@pytest.fixture
def normal_metrics() -> Dict[str, Any]:
    """Return normal metric data (no anomaly) - deterministic values."""
    base_time = datetime.utcnow()
    # Use deterministic values with slight variations (not random)
    values = [5.0, 5.1, 4.9, 5.2, 4.8, 5.0, 5.1, 4.9, 5.0, 5.0]
    return {
        "namespace": "AWS/Lambda",
        "metric": "Errors",
        "datapoints": [
            {"Timestamp": (base_time - timedelta(minutes=i * 5)).isoformat(), "Average": values[i]}
            for i in range(10)
        ],
    }


@pytest.fixture
def spike_metrics() -> Dict[str, Any]:
    """Return metric data with spike (anomaly detected)."""
    base_time = datetime.utcnow()
    values = [5.0, 5.5, 4.8, 5.2, 5.1, 5.0, 4.9, 5.3, 5.0, 50.0]  # Last value is spike
    return {
        "namespace": "AWS/Lambda",
        "metric": "Errors",
        "datapoints": [
            {"Timestamp": (base_time - timedelta(minutes=i * 5)).isoformat(), "Average": val}
            for i, val in enumerate(values)
        ],
    }


@pytest.fixture
def critical_spike_metrics() -> Dict[str, Any]:
    """Return metric data with critical spike (z-score > 3)."""
    base_time = datetime.utcnow()
    # With base values of 5.0 and slight variance, a spike of 1000+ ensures z > 3
    values = [5.0, 5.1, 4.9, 5.2, 4.8, 5.0, 5.1, 4.9, 5.0, 1000.0]
    return {
        "namespace": "AWS/Lambda",
        "metric": "Errors",
        "datapoints": [
            {"Timestamp": (base_time - timedelta(minutes=i * 5)).isoformat(), "Average": val}
            for i, val in enumerate(values)
        ],
    }


@pytest.fixture
def single_datapoint_metrics() -> Dict[str, Any]:
    """Return metrics with single datapoint (insufficient data)."""
    base_time = datetime.utcnow()
    return {
        "namespace": "AWS/Lambda",
        "metric": "Errors",
        "datapoints": [
            {"Timestamp": base_time.isoformat(), "Average": 10.0}
        ],
    }


@pytest.fixture
def zero_variance_metrics() -> Dict[str, Any]:
    """Return metrics with identical values (zero variance edge case)."""
    base_time = datetime.utcnow()
    return {
        "namespace": "AWS/Lambda",
        "metric": "Errors",
        "datapoints": [
            {"Timestamp": (base_time - timedelta(minutes=i * 5)).isoformat(), "Average": 5.0}
            for i in range(10)
        ],
    }


@pytest.fixture
def mock_cloudwatch_metrics(normal_metrics) -> Dict[str, Any]:
    """Default mock CloudWatch metrics (configurable via parametrize)."""
    return normal_metrics


# ============================================================================
# Pattern Anomaly Fixtures
# ============================================================================


@pytest.fixture
def pattern_service_mock():
    """Create mock DetectionPatternService."""
    with patch.dict("os.environ", {"RDS_PROVIDER": "mock"}):
        from src.agents.bdp.services import DetectionPatternService
        return DetectionPatternService(use_mock=True)


@pytest.fixture
def auth_failure_context() -> Dict[str, Any]:
    """Context for testing authentication failure pattern."""
    return {
        "text": """
        2024-01-15 10:00:00 ERROR AuthService: Failed login attempt for user@example.com
        2024-01-15 10:01:00 ERROR AuthService: Failed login attempt for user@example.com
        2024-01-15 10:02:00 ERROR AuthService: Failed login attempt for user@example.com
        2024-01-15 10:03:00 ERROR AuthService: Failed login attempt for user@example.com
        2024-01-15 10:04:00 ERROR AuthService: Failed login attempt for user@example.com
        """,
    }


@pytest.fixture
def exception_context() -> Dict[str, Any]:
    """Context with multiple exception patterns."""
    return {
        "text": """
        Exception: NullPointerException at com.app.Service.process
        Error: Connection refused to database
        FATAL: Out of memory - heap space exhausted
        CRITICAL: Service degradation detected
        Exception: TimeoutException waiting for response
        """,
    }


@pytest.fixture
def normal_context() -> Dict[str, Any]:
    """Context with no anomaly patterns."""
    return {
        "text": """
        INFO: Application started successfully
        INFO: Processing 100 requests
        INFO: Completed batch job
        DEBUG: Cache hit ratio: 95%
        """,
    }


# ============================================================================
# Scheduled Detection Fixtures
# ============================================================================


@pytest.fixture
def scheduled_detection_services() -> List[Dict[str, str]]:
    """Services configuration for scheduled detection."""
    return [
        {"name": "auth-service", "log_group": "/aws/lambda/auth-service"},
        {"name": "api-gateway", "log_group": "/aws/lambda/api-gateway"},
        {"name": "data-processor", "log_group": "/aws/lambda/data-processor"},
    ]


@pytest.fixture
def empty_services() -> List[Dict[str, str]]:
    """Empty services list for edge case testing."""
    return []


# ============================================================================
# Event Fixtures
# ============================================================================


@pytest.fixture
def log_anomaly_event() -> Dict[str, Any]:
    """Standard log anomaly detection event."""
    return {
        "detection_type": "log_anomaly",
        "log_group": "/aws/lambda/test-function",
        "service_name": "test-service",
        "time_range_hours": 1,
    }


@pytest.fixture
def metric_anomaly_event() -> Dict[str, Any]:
    """Standard metric anomaly detection event."""
    return {
        "detection_type": "metric_anomaly",
        "namespace": "AWS/Lambda",
        "metric_name": "Errors",
        "dimensions": [{"Name": "FunctionName", "Value": "test-function"}],
        "service_name": "test-service",
        "time_range_hours": 24,
    }


@pytest.fixture
def pattern_anomaly_event() -> Dict[str, Any]:
    """Standard pattern anomaly detection event."""
    return {
        "detection_type": "pattern_anomaly",
        "target_service": None,
        "context": {},
    }


@pytest.fixture
def scheduled_event(scheduled_detection_services) -> Dict[str, Any]:
    """Standard scheduled detection event."""
    return {
        "detection_type": "scheduled",
        "services": scheduled_detection_services,
    }


@pytest.fixture
def lambda_event_with_body(log_anomaly_event) -> Dict[str, Any]:
    """Lambda event with JSON body (API Gateway style)."""
    return {
        "body": json.dumps(log_anomaly_event),
    }


# ============================================================================
# Assertion Helpers
# ============================================================================


@pytest.fixture
def assert_anomaly_record():
    """Factory fixture for anomaly record validation."""
    def _assert(record: Dict[str, Any], expected_type: str, expected_severity: str = None):
        assert "signature" in record
        assert "anomaly_type" in record
        assert record["anomaly_type"] == expected_type
        assert "service_name" in record
        assert "first_seen" in record
        assert "last_seen" in record
        assert "severity" in record

        if expected_severity:
            assert record["severity"] == expected_severity

    return _assert


@pytest.fixture
def assert_detection_result():
    """Factory fixture for detection result validation."""
    def _assert(result: Dict[str, Any], expected_detected: bool):
        assert "anomalies_detected" in result
        assert result["anomalies_detected"] == expected_detected

        if expected_detected:
            assert "anomaly_count" in result or "anomaly_record" in result or "anomaly_records" in result

    return _assert
