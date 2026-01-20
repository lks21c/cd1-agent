"""
Detection Request/Response Schemas.

Pydantic models for detection API endpoints across all agents.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Base Schemas
# ============================================================================


class BaseDetectionRequest(BaseModel):
    """Base detection request model."""

    detection_type: str = Field(
        default="all",
        description="Type of detection to run",
    )


class BaseDetectionResponse(BaseModel):
    """Base detection response model."""

    success: bool = Field(description="Whether the detection completed successfully")
    request_id: str = Field(description="Unique request identifier")
    timestamp: datetime = Field(description="Response timestamp")
    data: Dict[str, Any] = Field(description="Detection result data")


class SeverityBreakdown(BaseModel):
    """Severity breakdown for anomaly counts."""

    critical: int = Field(default=0, description="Critical severity count")
    high: int = Field(default=0, description="High severity count")
    medium: int = Field(default=0, description="Medium severity count")
    low: int = Field(default=0, description="Low severity count")


# ============================================================================
# Cost Agent Schemas
# ============================================================================


class CostDetectionRequest(BaseDetectionRequest):
    """Cost detection request model."""

    detection_type: Literal["all", "forecast", "aws_anomalies"] = Field(
        default="all",
        description="Type of cost detection",
    )
    days: int = Field(
        default=14,
        ge=1,
        le=90,
        description="Number of days to analyze",
    )
    min_cost_threshold: float = Field(
        default=1.0,
        ge=0.0,
        description="Minimum cost threshold to include service",
    )


class CostAnomalyDetail(BaseModel):
    """Cost anomaly detail model."""

    service_name: str
    severity: str
    confidence_score: float
    current_cost: float
    previous_cost: float
    change_ratio: float
    detected_methods: List[str]
    analysis: str
    timestamp: str


class CostDetectionResponse(BaseModel):
    """Cost detection response model."""

    detection_type: str
    period_days: int
    services_analyzed: int
    anomalies_detected: bool
    total_anomalies: int
    severity_breakdown: SeverityBreakdown
    summary: str
    anomalies: List[CostAnomalyDetail]
    detection_timestamp: str


# ============================================================================
# HDSP Agent Schemas
# ============================================================================


class HDSPDetectionRequest(BaseDetectionRequest):
    """HDSP detection request model."""

    detection_type: Literal["all", "pod_failure", "node_pressure", "resource"] = Field(
        default="all",
        description="Type of HDSP detection",
    )
    cluster_name: Optional[str] = Field(
        default=None,
        description="Specific cluster to analyze",
    )


class HDSPAnomalyDetail(BaseModel):
    """HDSP anomaly detail model."""

    cluster: str
    namespace: Optional[str] = None
    resource_type: str
    resource_name: str
    severity: str
    message: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class HDSPDetectionResponse(BaseModel):
    """HDSP detection response model."""

    detection_type: str
    clusters_analyzed: int
    anomalies_detected: bool
    total_anomalies: int
    severity_breakdown: SeverityBreakdown
    summary: str
    anomalies: List[HDSPAnomalyDetail]
    detection_timestamp: str


# ============================================================================
# BDP Agent Schemas
# ============================================================================


class BDPDetectionRequest(BaseDetectionRequest):
    """BDP detection request model."""

    detection_type: Literal["log_anomaly", "metric_anomaly", "pattern_anomaly", "scheduled"] = Field(
        default="scheduled",
        description="Type of BDP detection",
    )
    log_group: Optional[str] = Field(
        default=None,
        description="Specific log group to analyze",
    )
    time_range_hours: int = Field(
        default=1,
        ge=1,
        le=24,
        description="Time range in hours for analysis",
    )
    service_name: Optional[str] = Field(
        default=None,
        description="Specific service to analyze",
    )


class BDPAnomalyDetail(BaseModel):
    """BDP anomaly detail model."""

    anomaly_type: str
    service_name: Optional[str] = None
    log_group: Optional[str] = None
    pattern_id: Optional[str] = None
    severity: str
    message: str
    occurrence_count: int = Field(default=1)
    sample_logs: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class BDPDetectionResponse(BaseModel):
    """BDP detection response model."""

    detection_type: str
    time_range_hours: int
    anomalies_detected: bool
    total_anomalies: int
    severity_breakdown: SeverityBreakdown
    summary: str
    anomalies: List[BDPAnomalyDetail]
    detection_timestamp: str


# ============================================================================
# Drift Agent Schemas
# ============================================================================


class DriftDetectionRequest(BaseDetectionRequest):
    """Drift detection request model."""

    resource_types: List[Literal["eks", "msk", "s3", "emr", "mwaa"]] = Field(
        default=["eks", "msk", "s3"],
        description="Resource types to check for drift",
    )
    severity_threshold: Literal["critical", "high", "medium", "low"] = Field(
        default="medium",
        description="Minimum severity threshold to report",
    )
    enable_analysis: bool = Field(
        default=False,
        description="Enable LLM-based drift analysis",
    )


class DriftDetail(BaseModel):
    """Drift detail model."""

    resource_type: str
    resource_name: str
    severity: str
    drift_type: str
    field_path: str
    expected_value: Any
    actual_value: Any
    message: str
    timestamp: str
    analysis: Optional[Dict[str, Any]] = None


class DriftDetectionResponse(BaseModel):
    """Drift detection response model."""

    resource_types_checked: List[str]
    total_resources_checked: int
    drifts_detected: bool
    total_drifts: int
    severity_breakdown: SeverityBreakdown
    summary: str
    drifts: List[DriftDetail]
    detection_timestamp: str


# ============================================================================
# Status Schemas
# ============================================================================


class AgentStatusResponse(BaseModel):
    """Agent status response model."""

    agent: str
    status: Literal["healthy", "degraded", "unhealthy"]
    environment: str
    version: str = Field(default="1.0.0")
    uptime_seconds: float
    last_detection: Optional[str] = None
    detection_count: int = Field(default=0)
    error_count: int = Field(default=0)
    config: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str
