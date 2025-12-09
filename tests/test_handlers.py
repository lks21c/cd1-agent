"""
Unit Tests for BDP Agent Handlers.

Tests for Lambda handler implementations.
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from src.handlers.base_handler import BaseHandler, LambdaResponse
from src.handlers.detection_handler import DetectionHandler, handler as detection_handler
from src.handlers.analysis_handler import AnalysisHandler, handler as analysis_handler
from src.handlers.remediation_handler import RemediationHandler, handler as remediation_handler


class TestLambdaResponse:
    """Test suite for LambdaResponse."""

    def test_response_creation(self):
        """Test LambdaResponse creation."""
        response = LambdaResponse(
            status_code=200,
            body={"message": "success"},
        )

        assert response.status_code == 200
        assert response.body["message"] == "success"
        assert "Content-Type" in response.headers

    def test_response_to_dict(self):
        """Test LambdaResponse to_dict conversion."""
        response = LambdaResponse(
            status_code=200,
            body={"key": "value"},
        )

        result = response.to_dict()

        assert result["statusCode"] == 200
        assert isinstance(result["body"], str)
        assert json.loads(result["body"])["key"] == "value"

    def test_response_custom_headers(self):
        """Test LambdaResponse with custom headers."""
        response = LambdaResponse(
            status_code=200,
            body={},
            headers={"X-Custom": "Header"},
        )

        assert response.headers["X-Custom"] == "Header"


class TestBaseHandler:
    """Test suite for BaseHandler."""

    def test_concrete_handler_required(self):
        """Test that BaseHandler requires concrete implementation."""
        with pytest.raises(TypeError):
            BaseHandler()

    def test_config_loading(self):
        """Test configuration loading."""

        class TestHandler(BaseHandler):
            def process(self, event, context):
                return {}

        with patch.dict(
            "os.environ",
            {"ENVIRONMENT": "test", "AWS_REGION": "us-west-2"},
        ):
            handler = TestHandler()

            assert handler.config["environment"] == "test"
            assert handler.config["region"] == "us-west-2"


class TestDetectionHandler:
    """Test suite for DetectionHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "mock",
                "AWS_PROVIDER": "mock",
            },
        ):
            return DetectionHandler()

    def test_handler_creation(self, handler):
        """Test DetectionHandler creation."""
        assert handler is not None
        assert handler.config["llm_provider"] == "mock"

    def test_validate_input_missing_type(self, handler):
        """Test validation with missing detection_type."""
        event = {"body": "{}"}
        error = handler._validate_input(event)

        assert error is not None
        assert "detection_type" in error

    def test_validate_input_invalid_type(self, handler):
        """Test validation with invalid detection_type."""
        event = {"body": json.dumps({"detection_type": "invalid_type"})}
        error = handler._validate_input(event)

        assert error is not None

    def test_validate_input_valid(self, handler):
        """Test validation with valid input."""
        event = {"body": json.dumps({"detection_type": "log_anomaly"})}
        error = handler._validate_input(event)

        assert error is None

    def test_detect_log_anomalies(self, handler):
        """Test log anomaly detection."""
        result = handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
            "time_range_hours": 1,
        })

        # Result should have expected structure
        assert "anomalies_detected" in result

    def test_detect_cost_anomalies(self, handler):
        """Test cost anomaly detection."""
        result = handler._detect_cost_anomalies({"days": 7})

        assert "anomalies_detected" in result
        assert "services_analyzed" in result

    def test_handler_function(self, lambda_context):
        """Test Lambda handler function."""
        event = {
            "body": json.dumps({
                "detection_type": "scheduled",
                "services": [],
            })
        }

        with patch.dict(
            "os.environ",
            {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"},
        ):
            response = detection_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True


class TestAnalysisHandler:
    """Test suite for AnalysisHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "mock",
                "AWS_PROVIDER": "mock",
            },
        ):
            return AnalysisHandler()

    def test_handler_creation(self, handler):
        """Test AnalysisHandler creation."""
        assert handler is not None

    def test_validate_input_missing_data(self, handler):
        """Test validation with missing anomaly data."""
        event = {"body": "{}"}
        error = handler._validate_input(event)

        assert error is not None

    def test_validate_input_valid(self, handler, sample_anomaly_data):
        """Test validation with valid input."""
        event = {"detail": sample_anomaly_data}
        error = handler._validate_input(event)

        assert error is None

    def test_perform_analysis(self, handler, sample_anomaly_data, sample_log_summary):
        """Test analysis execution."""
        result = handler._perform_analysis(
            anomaly_data=sample_anomaly_data,
            log_summary=sample_log_summary,
        )

        assert result is not None
        assert 0.0 <= result.confidence_score <= 1.0

    def test_determine_action_auto_execute(self, handler):
        """Test action determination for auto-execute."""
        from src.models.analysis_result import AnalysisResult, AnalysisDetails

        result = AnalysisResult(
            analysis=AnalysisDetails(root_cause="Test"),
            confidence_score=0.90,
            requires_human_review=False,
        )

        action = handler._determine_action(result)

        assert action == "auto_execute"

    def test_determine_action_approval(self, handler):
        """Test action determination for approval."""
        from src.models.analysis_result import AnalysisResult, AnalysisDetails

        result = AnalysisResult(
            analysis=AnalysisDetails(root_cause="Test"),
            confidence_score=0.70,
        )

        action = handler._determine_action(result)

        assert action == "request_approval"

    def test_handler_function(self, lambda_context, sample_anomaly_data):
        """Test Lambda handler function."""
        event = {
            "detail": sample_anomaly_data,
        }

        with patch.dict(
            "os.environ",
            {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"},
        ):
            response = analysis_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True
        assert "analysis" in body["data"]


class TestRemediationHandler:
    """Test suite for RemediationHandler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        with patch.dict(
            "os.environ",
            {"AWS_PROVIDER": "mock"},
        ):
            return RemediationHandler()

    def test_handler_creation(self, handler):
        """Test RemediationHandler creation."""
        assert handler is not None

    def test_validate_input_missing_result(self, handler):
        """Test validation with missing analysis_result."""
        event = {"body": "{}"}
        error = handler._validate_input(event)

        assert error is not None
        assert "analysis_result" in error

    def test_validate_input_valid(self, handler, sample_analysis_result):
        """Test validation with valid input."""
        event = {"detail": {"analysis_result": sample_analysis_result}}
        error = handler._validate_input(event)

        assert error is None

    def test_execute_action_notify(self, handler, sample_anomaly_data):
        """Test notification action execution."""
        from src.models.analysis_result import RemediationAction, ActionType

        action = RemediationAction(
            action_type=ActionType.NOTIFY,
            parameters={"channel": "slack", "message": "Test"},
        )

        result = handler._execute_action(action, sample_anomaly_data)

        assert result["status"] == "success"
        assert result["action_type"] == ActionType.NOTIFY

    def test_execute_action_escalate(self, handler, sample_anomaly_data):
        """Test escalation action execution."""
        from src.models.analysis_result import RemediationAction, ActionType

        action = RemediationAction(
            action_type=ActionType.ESCALATE,
            parameters={"severity": "high", "team": "platform"},
        )

        result = handler._execute_action(action, sample_anomaly_data)

        assert result["status"] == "success"

    def test_handler_function(
        self, lambda_context, sample_anomaly_data, sample_analysis_result
    ):
        """Test Lambda handler function."""
        event = {
            "detail": {
                "anomaly_data": sample_anomaly_data,
                "analysis_result": sample_analysis_result,
                "auto_approved": True,
            }
        }

        with patch.dict("os.environ", {"AWS_PROVIDER": "mock"}):
            response = remediation_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True

    def test_process_no_remediations(self, handler, lambda_context, sample_anomaly_data):
        """Test processing with no remediation actions."""
        event = {
            "detail": {
                "anomaly_data": sample_anomaly_data,
                "analysis_result": {
                    "analysis": {"root_cause": "Test"},
                    "confidence_score": 0.8,
                    "remediations": [],
                },
            }
        }

        result = handler.process(event, lambda_context)

        assert result["status"] == "no_action"
