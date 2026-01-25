"""
HDSP Monitoring Data Models.

Pydantic models for Prometheus alert processing and notification.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    """3-Tier alert severity classification."""

    CRITICAL = "critical"  # Service down, data loss risk - Immediate KakaoTalk
    HIGH = "high"          # Degraded performance - Immediate KakaoTalk
    MEDIUM = "medium"      # Warning, monitor closely - EventBridge only


class AlertStatus(str, Enum):
    """Prometheus alert status."""

    FIRING = "firing"
    RESOLVED = "resolved"


class PrometheusAlert(BaseModel):
    """Raw Prometheus Alertmanager alert."""

    alert_name: str = Field(..., alias="alertname")
    status: AlertStatus = AlertStatus.FIRING
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    starts_at: datetime = Field(default_factory=datetime.utcnow, alias="startsAt")
    ends_at: Optional[datetime] = Field(None, alias="endsAt")
    fingerprint: str = ""
    generator_url: Optional[str] = Field(None, alias="generatorURL")

    class Config:
        populate_by_name = True
        extra = "allow"

    @property
    def namespace(self) -> str:
        """Extract namespace from labels."""
        return self.labels.get("namespace", "default")

    @property
    def pod(self) -> Optional[str]:
        """Extract pod name from labels."""
        return self.labels.get("pod")

    @property
    def node(self) -> Optional[str]:
        """Extract node name from labels."""
        return self.labels.get("node")

    @property
    def container(self) -> Optional[str]:
        """Extract container name from labels."""
        return self.labels.get("container")

    @property
    def service(self) -> Optional[str]:
        """Extract service name from labels."""
        return self.labels.get("service")

    @property
    def prometheus_severity(self) -> str:
        """Get severity label from Prometheus."""
        return self.labels.get("severity", "warning")

    @property
    def summary(self) -> str:
        """Get summary annotation."""
        return self.annotations.get("summary", "")

    @property
    def description(self) -> str:
        """Get description annotation."""
        return self.annotations.get("description", "")

    @property
    def runbook_url(self) -> Optional[str]:
        """Get runbook URL annotation."""
        return self.annotations.get("runbook_url")

    def compute_fingerprint(self) -> str:
        """Compute unique fingerprint for deduplication."""
        key_parts = [
            self.alert_name,
            self.namespace,
            self.labels.get("pod", ""),
            self.labels.get("node", ""),
            self.labels.get("container", ""),
        ]
        key_str = "|".join(key_parts)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]


class ProcessedAlert(BaseModel):
    """Processed and enriched alert ready for notification."""

    fingerprint: str = Field(..., description="SHA256 hash for deduplication")
    alert_name: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.FIRING
    namespace: str
    resource_type: str = "Pod"  # Pod, Node, Service, etc.
    resource_name: str
    cluster_name: str = "on-prem-k8s"

    summary: str
    description: str
    runbook_url: Optional[str] = None

    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    occurrence_count: int = 1

    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)

    @property
    def duration_minutes(self) -> int:
        """Calculate alert duration in minutes."""
        delta = datetime.utcnow() - self.first_seen
        return int(delta.total_seconds() / 60)

    @property
    def is_long_running(self) -> bool:
        """Check if alert has been firing for more than 15 minutes."""
        return self.duration_minutes > 15

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "fingerprint": self.fingerprint,
            "alert_name": self.alert_name,
            "severity": self.severity.value,
            "status": self.status.value,
            "namespace": self.namespace,
            "resource_type": self.resource_type,
            "resource_name": self.resource_name,
            "cluster_name": self.cluster_name,
            "summary": self.summary,
            "description": self.description,
            "runbook_url": self.runbook_url,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "duration_minutes": self.duration_minutes,
            "occurrence_count": self.occurrence_count,
            "labels": self.labels,
        }


class AlertGroup(BaseModel):
    """Group of related alerts for batch notification."""

    group_key: str = Field(..., description="namespace:alertname format")
    severity: AlertSeverity = Field(..., description="Highest severity in group")
    alerts: List[ProcessedAlert] = Field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total number of alerts in group."""
        return len(self.alerts)

    @property
    def namespace(self) -> str:
        """Extract namespace from group key."""
        parts = self.group_key.split(":")
        return parts[0] if parts else "default"

    @property
    def alert_name(self) -> str:
        """Extract alert name from group key."""
        parts = self.group_key.split(":")
        return parts[1] if len(parts) > 1 else self.group_key

    @property
    def critical_count(self) -> int:
        """Count of CRITICAL alerts."""
        return sum(1 for a in self.alerts if a.severity == AlertSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        """Count of HIGH alerts."""
        return sum(1 for a in self.alerts if a.severity == AlertSeverity.HIGH)

    @property
    def earliest_first_seen(self) -> datetime:
        """Earliest first_seen among all alerts."""
        if not self.alerts:
            return datetime.utcnow()
        return min(a.first_seen for a in self.alerts)


@dataclass
class NotificationResult:
    """Result of notification attempt."""

    success: bool
    channel: str  # "kakao", "eventbridge", "mock"
    message: Optional[str] = None
    error: Optional[str] = None
    alert_count: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "channel": self.channel,
            "message": self.message,
            "error": self.error,
            "alert_count": self.alert_count,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class DeduplicationEntry:
    """Entry in deduplication store."""

    fingerprint: str
    alert_name: str
    first_seen: datetime
    last_seen: datetime
    notification_count: int = 0
    last_notified: Optional[datetime] = None

    def should_notify(
        self,
        dedup_window_seconds: int = 300,
        repeat_interval_seconds: int = 3600,
    ) -> bool:
        """Check if this alert should trigger a notification.

        Args:
            dedup_window_seconds: Initial deduplication window (5 min default)
            repeat_interval_seconds: Repeat notification interval (1 hour default)

        Returns:
            True if notification should be sent
        """
        now = datetime.utcnow()

        # First notification - check if within dedup window
        if self.last_notified is None:
            time_since_first = (now - self.first_seen).total_seconds()
            # Allow first notification after brief wait (30s) for grouping
            return time_since_first >= 30

        # Repeat notification - check interval
        time_since_last = (now - self.last_notified).total_seconds()
        return time_since_last >= repeat_interval_seconds

    def update_seen(self) -> None:
        """Update last seen timestamp."""
        self.last_seen = datetime.utcnow()

    def mark_notified(self) -> None:
        """Mark as notified."""
        self.last_notified = datetime.utcnow()
        self.notification_count += 1
