"""
Analysis Result Models for BDP Agent.

Pydantic models for LLM analysis results and remediation actions.
"""

from enum import Enum
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of remediation actions."""
    LAMBDA_RESTART = "lambda_restart"
    RDS_PARAMETER = "rds_parameter"
    AUTO_SCALING = "auto_scaling"
    EVENTBRIDGE_EVENT = "eventbridge_event"
    NOTIFY = "notify"
    ESCALATE = "escalate"
    INVESTIGATE = "investigate"


class RemediationAction(BaseModel):
    """
    Individual remediation action to be executed.

    Includes all parameters needed for execution and rollback.
    """
    action_type: ActionType
    priority: int = Field(default=1, ge=1, le=10)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    expected_outcome: str = ""
    rollback_plan: str = ""
    estimated_impact: str = "medium"
    requires_approval: bool = False

    class Config:
        use_enum_values = True


class AnalysisDetails(BaseModel):
    """Detailed analysis breakdown."""
    root_cause: str
    impact_severity: str = "medium"
    affected_services: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """
    Complete LLM analysis result.

    Contains root cause analysis, confidence scoring, and remediation plan.
    """
    analysis: AnalysisDetails
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    remediations: List[RemediationAction] = Field(default_factory=list)
    requires_human_review: bool = True
    review_reason: Optional[str] = None

    @property
    def auto_execute(self) -> bool:
        """Determine if remediation can be auto-executed."""
        return self.confidence_score >= 0.85 and not self.requires_human_review

    @property
    def requires_approval(self) -> bool:
        """Determine if human approval is required."""
        return 0.5 <= self.confidence_score < 0.85

    @property
    def requires_escalation(self) -> bool:
        """Determine if escalation is needed."""
        return self.confidence_score < 0.5


class ReflectionEvaluation(BaseModel):
    """Reflection engine evaluation scores."""
    evidence_sufficiency: float = Field(ge=0.0, le=1.0)
    logical_consistency: float = Field(ge=0.0, le=1.0)
    actionability: float = Field(ge=0.0, le=1.0)
    risk_assessment: float = Field(ge=0.0, le=1.0)


class ReflectionOutput(BaseModel):
    """
    Reflection engine output for quality assessment.

    Used to evaluate analysis quality and determine execution path.
    """
    evaluation: ReflectionEvaluation
    overall_confidence: float = Field(ge=0.0, le=1.0)
    concerns: List[str] = Field(default_factory=list)
    recommendations: Dict[str, Any] = Field(default_factory=dict)
    auto_execute: bool = False
    reason: str = ""
