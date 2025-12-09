"""
Unit Tests for BDP Agent Models.

Tests for Pydantic models and data validation.
"""

import pytest
from pydantic import ValidationError

from src.models.anomaly import (
    AnomalyRecord,
    AnomalyType,
    Severity,
    AnomalyDetectionResult,
    LogEntry,
    MetricsSnapshot,
    DetectionMethodResult,
)
from src.models.analysis_result import (
    AnalysisResult,
    RemediationAction,
    ActionType,
    AnalysisDetails,
    ReflectionOutput,
    ReflectionEvaluation,
)
from src.models.agent_state import (
    AgentState,
    AgentExecutionResult,
    ToolResult,
    ReflectionResult,
)


class TestAnomalyModels:
    """Test suite for anomaly models."""

    def test_anomaly_record_creation(self, sample_anomaly_data):
        """Test AnomalyRecord creation with valid data."""
        record = AnomalyRecord(**sample_anomaly_data)

        assert record.signature == "test_anomaly_001"
        assert record.anomaly_type == "error_spike"
        assert record.service_name == "test-lambda-function"
        assert record.occurrence_count == 15
        assert record.severity == Severity.HIGH

    def test_anomaly_record_defaults(self):
        """Test AnomalyRecord default values."""
        record = AnomalyRecord(
            signature="test_001",
            anomaly_type="error_spike",
            service_name="test-service",
            first_seen="2024-01-15T10:00:00Z",
            last_seen="2024-01-15T10:30:00Z",
        )

        assert record.occurrence_count == 1
        assert record.sample_logs == []
        assert record.metrics_snapshot == {}
        assert record.severity == Severity.MEDIUM

    def test_anomaly_record_validation_error(self):
        """Test AnomalyRecord validation with missing required fields."""
        with pytest.raises(ValidationError):
            AnomalyRecord(signature="test")

    def test_anomaly_type_enum(self):
        """Test AnomalyType enum values."""
        assert AnomalyType.METRIC_ANOMALY == "metric_anomaly"
        assert AnomalyType.LOG_PATTERN == "log_pattern"
        assert AnomalyType.ERROR_SPIKE == "error_spike"
        assert AnomalyType.COST_ANOMALY == "cost_anomaly"

    def test_severity_enum(self):
        """Test Severity enum values."""
        assert Severity.CRITICAL == "critical"
        assert Severity.HIGH == "high"
        assert Severity.MEDIUM == "medium"
        assert Severity.LOW == "low"
        assert Severity.INFO == "info"

    def test_log_entry_creation(self):
        """Test LogEntry creation."""
        entry = LogEntry(
            timestamp="2024-01-15T10:00:00Z",
            service_name="test-service",
            log_level="ERROR",
            message="Test error message",
        )

        assert entry.timestamp == "2024-01-15T10:00:00Z"
        assert entry.log_level == "ERROR"
        assert entry.metadata == {}

    def test_metrics_snapshot_creation(self):
        """Test MetricsSnapshot creation."""
        snapshot = MetricsSnapshot(
            namespace="AWS/Lambda",
            metric="Errors",
            values=[1.0, 2.0, 3.0],
        )

        assert snapshot.namespace == "AWS/Lambda"
        assert len(snapshot.values) == 3
        assert snapshot.timestamps is None

    def test_detection_method_result(self):
        """Test DetectionMethodResult creation."""
        result = DetectionMethodResult(
            method_name="stddev",
            detected=True,
            score=0.85,
            details={"z_score": 2.5},
        )

        assert result.method_name == "stddev"
        assert result.detected is True
        assert result.score == 0.85

    def test_anomaly_detection_result(self):
        """Test AnomalyDetectionResult creation."""
        result = AnomalyDetectionResult(
            is_anomaly=True,
            confidence_score=0.9,
            severity=Severity.HIGH,
            service_name="test-service",
            current_value=150.0,
            previous_value=100.0,
            change_ratio=0.5,
            detection_results=[],
            detected_methods=["ratio", "stddev"],
            analysis="Cost anomaly detected",
        )

        assert result.is_anomaly is True
        assert result.confidence_score == 0.9
        assert result.severity == Severity.HIGH


class TestAnalysisModels:
    """Test suite for analysis models."""

    def test_remediation_action_creation(self):
        """Test RemediationAction creation."""
        action = RemediationAction(
            action_type=ActionType.LAMBDA_RESTART,
            priority=1,
            parameters={"function_name": "test-function"},
            expected_outcome="Function restarted",
        )

        assert action.action_type == ActionType.LAMBDA_RESTART
        assert action.priority == 1
        assert action.requires_approval is False

    def test_remediation_action_with_approval(self):
        """Test RemediationAction requiring approval."""
        action = RemediationAction(
            action_type=ActionType.RDS_PARAMETER,
            priority=1,
            parameters={"parameter": "max_connections"},
            requires_approval=True,
        )

        assert action.requires_approval is True

    def test_action_type_enum(self):
        """Test ActionType enum values."""
        assert ActionType.LAMBDA_RESTART == "lambda_restart"
        assert ActionType.RDS_PARAMETER == "rds_parameter"
        assert ActionType.NOTIFY == "notify"
        assert ActionType.ESCALATE == "escalate"

    def test_analysis_details_creation(self):
        """Test AnalysisDetails creation."""
        details = AnalysisDetails(
            root_cause="Database connection pool exhausted",
            impact_severity="high",
            affected_services=["lambda", "rds"],
            evidence=["Timeout errors", "Connection refused"],
        )

        assert details.root_cause == "Database connection pool exhausted"
        assert len(details.affected_services) == 2

    def test_analysis_result_creation(self, sample_analysis_result):
        """Test AnalysisResult creation."""
        result = AnalysisResult(**sample_analysis_result)

        assert result.confidence_score == 0.87
        assert result.requires_human_review is False
        assert len(result.remediations) == 1

    def test_analysis_result_auto_execute_property(self):
        """Test AnalysisResult auto_execute property - always False (disabled)."""
        result = AnalysisResult(
            analysis=AnalysisDetails(root_cause="Test"),
            confidence_score=0.90,
            requires_human_review=False,
        )

        # Auto-execute is disabled - all actions require approval
        assert result.auto_execute is False

        result2 = AnalysisResult(
            analysis=AnalysisDetails(root_cause="Test"),
            confidence_score=0.70,
            requires_human_review=False,
        )

        assert result2.auto_execute is False

    def test_analysis_result_requires_approval_property(self):
        """Test AnalysisResult requires_approval property."""
        result = AnalysisResult(
            analysis=AnalysisDetails(root_cause="Test"),
            confidence_score=0.70,
        )

        assert result.requires_approval is True

    def test_analysis_result_requires_escalation_property(self):
        """Test AnalysisResult requires_escalation property."""
        result = AnalysisResult(
            analysis=AnalysisDetails(root_cause="Test"),
            confidence_score=0.40,
        )

        assert result.requires_escalation is True

    def test_reflection_evaluation_creation(self):
        """Test ReflectionEvaluation creation."""
        evaluation = ReflectionEvaluation(
            evidence_sufficiency=0.85,
            logical_consistency=0.90,
            actionability=0.80,
            risk_assessment=0.75,
        )

        assert evaluation.evidence_sufficiency == 0.85
        assert evaluation.logical_consistency == 0.90

    def test_reflection_output_creation(self, sample_reflection_result):
        """Test ReflectionOutput creation."""
        output = ReflectionOutput(**sample_reflection_result)

        assert output.overall_confidence == 0.82
        assert output.auto_execute is False
        assert len(output.concerns) == 1

    def test_confidence_score_validation(self):
        """Test confidence score bounds validation."""
        with pytest.raises(ValidationError):
            AnalysisResult(
                analysis=AnalysisDetails(root_cause="Test"),
                confidence_score=1.5,  # Invalid: > 1.0
            )

        with pytest.raises(ValidationError):
            AnalysisResult(
                analysis=AnalysisDetails(root_cause="Test"),
                confidence_score=-0.5,  # Invalid: < 0.0
            )


class TestAgentStateModels:
    """Test suite for agent state models."""

    def test_tool_result_creation(self):
        """Test ToolResult creation."""
        result: ToolResult = {
            "tool_name": "get_cloudwatch_metrics",
            "input_params": {"service_name": "test"},
            "output": {"values": [1, 2, 3]},
            "success": True,
            "error_message": None,
        }

        assert result["tool_name"] == "get_cloudwatch_metrics"
        assert result["success"] is True

    def test_reflection_result_creation(self):
        """Test ReflectionResult creation."""
        result: ReflectionResult = {
            "evidence_sufficiency": 0.8,
            "logical_consistency": 0.9,
            "actionability": 0.7,
            "risk_assessment": 0.75,
            "overall_confidence": 0.8,
            "concerns": ["Need more data"],
            "should_continue": True,
            "reason": "More investigation needed",
        }

        assert result["overall_confidence"] == 0.8
        assert result["should_continue"] is True

    def test_agent_execution_result_creation(self):
        """Test AgentExecutionResult creation."""
        result: AgentExecutionResult = {
            "root_cause": "Database connection issue",
            "confidence_score": 0.85,
            "remediation_plan": {"actions": []},
            "evidence": ["Timeout errors"],
            "reasoning": "Multiple signals indicate DB issues",
            "requires_human_review": False,
            "review_reason": None,
        }

        assert result["root_cause"] == "Database connection issue"
        assert result["confidence_score"] == 0.85
        assert result["requires_human_review"] is False
