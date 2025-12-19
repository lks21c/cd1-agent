"""
Drift Analysis Result Models.

Pydantic models for LLM-based drift root cause analysis results.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DriftCauseCategory(str, Enum):
    """Root cause categories for configuration drifts."""

    MANUAL_CHANGE = "manual_change"  # Console/CLI/SDK direct modification
    AUTO_SCALING = "auto_scaling"  # ASG, HPA, or similar scaling mechanism
    MAINTENANCE_WINDOW = "maintenance_window"  # AWS automatic maintenance
    DEPLOYMENT_DRIFT = "deployment_drift"  # IaC (Terraform/CDK) state mismatch
    SECURITY_PATCH = "security_patch"  # Automatic security updates
    OPERATOR_ERROR = "operator_error"  # Misconfiguration by operator
    UNKNOWN = "unknown"  # Insufficient evidence


class DriftCauseAnalysis(BaseModel):
    """Detailed drift cause analysis."""

    category: DriftCauseCategory = DriftCauseCategory.UNKNOWN
    root_cause: str = ""
    likely_actor: str = "unknown"  # user/system/automation/aws
    time_estimate: Optional[str] = None  # When drift likely occurred
    evidence: List[str] = Field(default_factory=list)
    related_changes: List[str] = Field(default_factory=list)

    class Config:
        use_enum_values = True


class DriftRemediationAction(BaseModel):
    """Drift-specific remediation action."""

    action_type: str  # revert_to_baseline, update_baseline, escalate, investigate, notify
    priority: int = Field(default=1, ge=1, le=10)
    description: str = ""
    command_hint: Optional[str] = None  # e.g., "terraform apply", "kubectl apply"
    requires_approval: bool = True
    rollback_steps: List[str] = Field(default_factory=list)
    expected_outcome: str = ""


class DriftAnalysisResult(BaseModel):
    """
    Complete drift analysis result from LLM.

    Contains root cause analysis, confidence scoring, and remediation plan.
    """

    # Identifiers
    drift_id: str = ""
    resource_type: str = ""
    resource_id: str = ""

    # Analysis
    cause_analysis: DriftCauseAnalysis = Field(default_factory=DriftCauseAnalysis)
    impact_assessment: str = ""
    blast_radius: List[str] = Field(default_factory=list)  # Affected systems

    # Scores
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    urgency_score: float = Field(default=0.5, ge=0.0, le=1.0)  # How urgent is remediation

    # Actions
    remediations: List[DriftRemediationAction] = Field(default_factory=list)

    # Control
    requires_human_review: bool = True
    review_reason: Optional[str] = None
    reasoning: str = ""

    @property
    def requires_approval(self) -> bool:
        """Determine if human approval is required."""
        return self.confidence_score >= 0.5

    @property
    def requires_escalation(self) -> bool:
        """Determine if escalation is needed."""
        return self.confidence_score < 0.5

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "drift_id": self.drift_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "cause_analysis": self.cause_analysis.model_dump(),
            "impact_assessment": self.impact_assessment,
            "blast_radius": self.blast_radius,
            "confidence_score": self.confidence_score,
            "urgency_score": self.urgency_score,
            "remediations": [r.model_dump() for r in self.remediations],
            "requires_human_review": self.requires_human_review,
            "review_reason": self.review_reason,
            "reasoning": self.reasoning,
        }


class DriftReflectionResult(BaseModel):
    """
    Reflection engine output for drift analysis quality assessment.

    Used to evaluate analysis quality and determine if replanning is needed.
    """

    # Evaluation scores
    cause_plausibility: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    remediation_practicality: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_assessment: float = Field(default=0.5, ge=0.0, le=1.0)

    # Decision
    overall_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    needs_replan: bool = False
    needs_human_review: bool = True
    concerns: List[str] = Field(default_factory=list)
    reasoning: str = ""

    @property
    def should_complete(self) -> bool:
        """Determine if analysis is sufficient to complete."""
        return (
            not self.needs_replan
            and self.overall_confidence >= 0.7
            and all(
                score >= 0.6
                for score in [
                    self.cause_plausibility,
                    self.evidence_quality,
                    self.remediation_practicality,
                ]
            )
        )
