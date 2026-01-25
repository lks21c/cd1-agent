"""
Severity Mapper for Prometheus Alerts.

Maps Prometheus severity labels to 3-tier severity system
(CRITICAL, HIGH, MEDIUM).
"""

import logging
import re
from typing import Dict, Optional

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertSeverity,
    PrometheusAlert,
)

logger = logging.getLogger(__name__)


class SeverityMapper:
    """
    Maps Prometheus alert severity to 3-tier system.

    Priority:
    1. Alert name overrides (always apply)
    2. Label-based mapping
    3. Keyword-based inference
    4. Default to MEDIUM
    """

    # Label-based mapping (Prometheus severity label values)
    LABEL_MAPPING: Dict[str, AlertSeverity] = {
        # CRITICAL
        "critical": AlertSeverity.CRITICAL,
        "error": AlertSeverity.CRITICAL,
        "page": AlertSeverity.CRITICAL,
        "emergency": AlertSeverity.CRITICAL,
        "fatal": AlertSeverity.CRITICAL,
        # HIGH
        "warning": AlertSeverity.HIGH,
        "high": AlertSeverity.HIGH,
        "warn": AlertSeverity.HIGH,
        "major": AlertSeverity.HIGH,
        # MEDIUM
        "info": AlertSeverity.MEDIUM,
        "medium": AlertSeverity.MEDIUM,
        "low": AlertSeverity.MEDIUM,
        "minor": AlertSeverity.MEDIUM,
        "notice": AlertSeverity.MEDIUM,
    }

    # Alert name overrides (always apply, takes precedence)
    ALERT_OVERRIDES: Dict[str, AlertSeverity] = {
        # CRITICAL - Service-affecting issues
        "KubePodCrashLooping": AlertSeverity.CRITICAL,
        "KubePodNotReady": AlertSeverity.CRITICAL,
        "KubeNodeNotReady": AlertSeverity.CRITICAL,
        "KubeContainerOOMKilled": AlertSeverity.CRITICAL,
        "KubeContainerTerminated": AlertSeverity.CRITICAL,
        "TargetDown": AlertSeverity.CRITICAL,
        "PrometheusTargetMissing": AlertSeverity.CRITICAL,
        "KubeJobFailed": AlertSeverity.CRITICAL,
        "KubeStatefulSetReplicasMismatch": AlertSeverity.CRITICAL,
        "KubeDaemonSetMisScheduled": AlertSeverity.CRITICAL,
        "KubeAPIDown": AlertSeverity.CRITICAL,
        "KubeSchedulerDown": AlertSeverity.CRITICAL,
        "KubeControllerManagerDown": AlertSeverity.CRITICAL,
        "EtcdClusterUnavailable": AlertSeverity.CRITICAL,
        "NodeFilesystemAlmostOutOfSpace": AlertSeverity.CRITICAL,
        "KubeNodeUnreachable": AlertSeverity.CRITICAL,
        "AlertmanagerDown": AlertSeverity.CRITICAL,
        "PrometheusDown": AlertSeverity.CRITICAL,
        "Watchdog": AlertSeverity.CRITICAL,  # Dead man's switch

        # HIGH - Performance degradation
        "KubeNodeMemoryPressure": AlertSeverity.HIGH,
        "KubeNodeDiskPressure": AlertSeverity.HIGH,
        "KubeNodePIDPressure": AlertSeverity.HIGH,
        "KubeDeploymentReplicasMismatch": AlertSeverity.HIGH,
        "KubeStatefulSetUpdateNotRolledOut": AlertSeverity.HIGH,
        "KubePodNotScheduled": AlertSeverity.HIGH,
        "KubeHpaReplicasMismatch": AlertSeverity.HIGH,
        "KubeHpaMaxedOut": AlertSeverity.HIGH,
        "KubePersistentVolumeFillingUp": AlertSeverity.HIGH,
        "NodeFilesystemSpaceFillingUp": AlertSeverity.HIGH,
        "NodeMemoryHighUtilization": AlertSeverity.HIGH,
        "NodeCPUHighUtilization": AlertSeverity.HIGH,
        "ContainerCPUUsageHigh": AlertSeverity.HIGH,
        "ContainerMemoryUsageHigh": AlertSeverity.HIGH,
        "KubeContainerWaiting": AlertSeverity.HIGH,
        "KubeJobNotCompleted": AlertSeverity.HIGH,
        "KubeCronJobRunning": AlertSeverity.HIGH,
        "PrometheusRuleFailures": AlertSeverity.HIGH,
        "PrometheusRemoteWriteFailures": AlertSeverity.HIGH,

        # MEDIUM - Informational
        "KubeQuotaAlmostFull": AlertSeverity.MEDIUM,
        "KubeResourceQuotaExceeded": AlertSeverity.MEDIUM,
        "KubeVersionMismatch": AlertSeverity.MEDIUM,
        "KubeClientErrors": AlertSeverity.MEDIUM,
        "NodeClockSkewDetected": AlertSeverity.MEDIUM,
        "PrometheusNotificationQueueRunningFull": AlertSeverity.MEDIUM,
    }

    # Keyword patterns for inference
    CRITICAL_KEYWORDS = [
        r"down$", r"failed$", r"crash", r"oom", r"killed", r"unreachable",
        r"unavailable", r"notready", r"missing$", r"lost$", r"dead$",
    ]
    HIGH_KEYWORDS = [
        r"pressure", r"mismatch", r"notrolledout", r"filling", r"high$",
        r"degraded", r"slow", r"latency", r"error", r"warning",
    ]

    def __init__(self):
        """Initialize severity mapper."""
        # Compile keyword patterns
        self._critical_patterns = [
            re.compile(kw, re.IGNORECASE) for kw in self.CRITICAL_KEYWORDS
        ]
        self._high_patterns = [
            re.compile(kw, re.IGNORECASE) for kw in self.HIGH_KEYWORDS
        ]

    def map_severity(self, alert: PrometheusAlert) -> AlertSeverity:
        """Map Prometheus alert to 3-tier severity.

        Args:
            alert: Raw Prometheus alert

        Returns:
            Mapped AlertSeverity
        """
        # 1. Check alert name overrides (highest priority)
        if alert.alert_name in self.ALERT_OVERRIDES:
            severity = self.ALERT_OVERRIDES[alert.alert_name]
            logger.debug(
                f"Alert '{alert.alert_name}' mapped to {severity.value} via override"
            )
            return severity

        # 2. Check label-based mapping
        prometheus_severity = alert.prometheus_severity.lower()
        if prometheus_severity in self.LABEL_MAPPING:
            severity = self.LABEL_MAPPING[prometheus_severity]
            logger.debug(
                f"Alert '{alert.alert_name}' mapped to {severity.value} "
                f"via label '{prometheus_severity}'"
            )
            return severity

        # 3. Check keyword patterns in alert name
        alert_name_lower = alert.alert_name.lower()

        for pattern in self._critical_patterns:
            if pattern.search(alert_name_lower):
                logger.debug(
                    f"Alert '{alert.alert_name}' mapped to CRITICAL via keyword"
                )
                return AlertSeverity.CRITICAL

        for pattern in self._high_patterns:
            if pattern.search(alert_name_lower):
                logger.debug(
                    f"Alert '{alert.alert_name}' mapped to HIGH via keyword"
                )
                return AlertSeverity.HIGH

        # 4. Default to MEDIUM
        logger.debug(f"Alert '{alert.alert_name}' defaulted to MEDIUM")
        return AlertSeverity.MEDIUM

    def get_override_reason(self, alert_name: str) -> Optional[str]:
        """Get reason for override if exists.

        Args:
            alert_name: Alert name

        Returns:
            Reason string or None
        """
        if alert_name in self.ALERT_OVERRIDES:
            severity = self.ALERT_OVERRIDES[alert_name]
            return f"Alert '{alert_name}' is mapped to {severity.value} by default override"
        return None

    def add_override(self, alert_name: str, severity: AlertSeverity) -> None:
        """Add custom severity override.

        Args:
            alert_name: Alert name to override
            severity: Severity to assign
        """
        self.ALERT_OVERRIDES[alert_name] = severity
        logger.info(f"Added severity override: {alert_name} -> {severity.value}")

    def remove_override(self, alert_name: str) -> bool:
        """Remove custom severity override.

        Args:
            alert_name: Alert name to remove

        Returns:
            True if removed, False if not found
        """
        if alert_name in self.ALERT_OVERRIDES:
            del self.ALERT_OVERRIDES[alert_name]
            logger.info(f"Removed severity override: {alert_name}")
            return True
        return False


# Singleton instance
_mapper_instance: Optional[SeverityMapper] = None


def get_severity_mapper() -> SeverityMapper:
    """Get singleton SeverityMapper instance."""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = SeverityMapper()
    return _mapper_instance
