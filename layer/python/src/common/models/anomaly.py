"""
Anomaly Models for CD1 Agent.

Pydantic models for representing detected anomalies and their metadata.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class AnomalyType(str, Enum):
    """Types of anomalies that can be detected."""
    METRIC_ANOMALY = "metric_anomaly"
    LOG_PATTERN = "log_pattern"
    ERROR_SPIKE = "error_spike"
    LATENCY_INCREASE = "latency_increase"
    COST_ANOMALY = "cost_anomaly"
    SECURITY_EVENT = "security_event"


class Severity(str, Enum):
    """Severity levels for anomalies."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class LogEntry(BaseModel):
    """Individual log entry within an anomaly."""
    timestamp: str
    service_name: str
    log_level: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MetricsSnapshot(BaseModel):
    """Metrics data at the time of anomaly detection."""
    namespace: str
    metric: str
    values: List[float]
    timestamps: Optional[List[str]] = None
    statistics: Optional[Dict[str, float]] = None


class AnomalyRecord(BaseModel):
    """
    Detected anomaly record with full context.

    This model represents a single detected anomaly with all relevant
    context for root cause analysis.
    """
    signature: str = Field(..., description="Unique identifier for deduplication")
    anomaly_type: str = Field(..., description="Type of anomaly detected")
    service_name: str = Field(..., description="Affected service name")
    first_seen: str = Field(..., description="ISO timestamp of first occurrence")
    last_seen: str = Field(..., description="ISO timestamp of last occurrence")
    occurrence_count: int = Field(default=1, ge=1)
    sample_logs: List[Dict[str, Any]] = Field(default_factory=list)
    metrics_snapshot: Dict[str, Any] = Field(default_factory=dict)
    severity: Severity = Field(default=Severity.MEDIUM)

    class Config:
        use_enum_values = True


class DetectionMethodResult(BaseModel):
    """Result from a single detection method."""
    method_name: str
    detected: bool
    score: float = Field(ge=0.0, le=1.0)
    details: Dict[str, Any] = Field(default_factory=dict)


class AnomalyDetectionResult(BaseModel):
    """
    Comprehensive anomaly detection result.

    Contains results from multiple detection methods and combined scoring.
    """
    is_anomaly: bool
    confidence_score: float = Field(ge=0.0, le=1.0)
    severity: Severity
    service_name: str
    current_value: float
    previous_value: float
    change_ratio: float
    detection_results: List[DetectionMethodResult]
    detected_methods: List[str]
    analysis: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    class Config:
        use_enum_values = True
