"""
Alert Processor for HDSP Monitoring.

Processes, deduplicates, and groups Prometheus alerts for notification.
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertGroup,
    AlertSeverity,
    AlertStatus,
    ProcessedAlert,
    PrometheusAlert,
)
from src.agents.hdsp_monitoring.hdsp_monitoring.services.severity_mapper import (
    SeverityMapper,
    get_severity_mapper,
)
from src.agents.hdsp_monitoring.hdsp_monitoring.services.deduplication_store import (
    DeduplicationStore,
    get_deduplication_store,
)

logger = logging.getLogger(__name__)


class AlertProcessor:
    """
    Processes Prometheus alerts for notification.

    Features:
    - Severity mapping to 3-tier system
    - Fingerprint-based deduplication
    - Alert grouping by namespace:alertname
    - Rate limiting for notifications
    - Namespace filtering
    """

    def __init__(
        self,
        severity_mapper: Optional[SeverityMapper] = None,
        dedup_store: Optional[DeduplicationStore] = None,
        cluster_name: Optional[str] = None,
        include_namespaces: Optional[List[str]] = None,
        exclude_namespaces: Optional[List[str]] = None,
        max_notifications_per_minute: int = 10,
    ):
        """Initialize alert processor.

        Args:
            severity_mapper: Severity mapper instance
            dedup_store: Deduplication store instance
            cluster_name: K8s cluster name
            include_namespaces: Namespaces to include (None = all)
            exclude_namespaces: Namespaces to exclude
            max_notifications_per_minute: Rate limit
        """
        self.severity_mapper = severity_mapper or get_severity_mapper()
        self.dedup_store = dedup_store or get_deduplication_store()
        self.cluster_name = cluster_name or os.environ.get(
            "HDSP_CLUSTER_NAME", "on-prem-k8s"
        )
        self.include_namespaces = include_namespaces
        self.exclude_namespaces = exclude_namespaces or ["test-*", "dev-*"]
        self.max_notifications_per_minute = max_notifications_per_minute

        self._notification_count = 0
        self._last_rate_limit_reset = datetime.utcnow()

    def process_alerts(
        self,
        raw_alerts: List[PrometheusAlert],
    ) -> Tuple[List[ProcessedAlert], List[ProcessedAlert]]:
        """Process raw alerts into processed alerts.

        Args:
            raw_alerts: Raw Prometheus alerts

        Returns:
            Tuple of (all processed alerts, alerts to notify)
        """
        processed_alerts = []
        alerts_to_notify = []

        for raw in raw_alerts:
            # Apply namespace filter
            if not self._should_process_namespace(raw.namespace):
                logger.debug(f"Skipping alert from excluded namespace: {raw.namespace}")
                continue

            # Convert to processed alert
            processed = self._convert_alert(raw)
            processed_alerts.append(processed)

            # Check deduplication
            if self.dedup_store.check_and_update(processed):
                if self._check_rate_limit():
                    alerts_to_notify.append(processed)
                else:
                    logger.warning(
                        f"Rate limit exceeded, skipping notification for {processed.alert_name}"
                    )

        logger.info(
            f"Processed {len(processed_alerts)} alerts, "
            f"{len(alerts_to_notify)} to notify"
        )
        return processed_alerts, alerts_to_notify

    def group_alerts(
        self,
        alerts: List[ProcessedAlert],
    ) -> List[AlertGroup]:
        """Group alerts by namespace:alertname.

        Args:
            alerts: Processed alerts to group

        Returns:
            List of AlertGroup objects
        """
        groups: Dict[str, AlertGroup] = {}

        for alert in alerts:
            group_key = f"{alert.namespace}:{alert.alert_name}"

            if group_key not in groups:
                groups[group_key] = AlertGroup(
                    group_key=group_key,
                    severity=alert.severity,
                    alerts=[],
                )

            groups[group_key].alerts.append(alert)

            # Update group severity to highest
            if self._compare_severity(alert.severity, groups[group_key].severity) > 0:
                groups[group_key].severity = alert.severity

        # Sort groups by severity (CRITICAL first) then by count
        sorted_groups = sorted(
            groups.values(),
            key=lambda g: (
                -self._severity_order(g.severity),
                -g.total_count,
            ),
        )

        logger.info(f"Grouped into {len(sorted_groups)} alert groups")
        return sorted_groups

    def filter_by_severity(
        self,
        alerts: List[ProcessedAlert],
        min_severity: AlertSeverity = AlertSeverity.MEDIUM,
    ) -> List[ProcessedAlert]:
        """Filter alerts by minimum severity.

        Args:
            alerts: Alerts to filter
            min_severity: Minimum severity to include

        Returns:
            Filtered alerts
        """
        min_order = self._severity_order(min_severity)
        return [a for a in alerts if self._severity_order(a.severity) >= min_order]

    def get_alerts_for_kakao(
        self,
        alerts: List[ProcessedAlert],
    ) -> List[ProcessedAlert]:
        """Get alerts that should be sent to KakaoTalk.

        CRITICAL and HIGH severity alerts only.

        Args:
            alerts: All processed alerts

        Returns:
            Alerts for KakaoTalk notification
        """
        return [
            a for a in alerts
            if a.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH)
        ]

    def get_alerts_for_eventbridge(
        self,
        alerts: List[ProcessedAlert],
    ) -> List[ProcessedAlert]:
        """Get alerts that should be sent to EventBridge.

        All severity levels.

        Args:
            alerts: All processed alerts

        Returns:
            Alerts for EventBridge
        """
        return alerts  # All alerts go to EventBridge

    def _convert_alert(self, raw: PrometheusAlert) -> ProcessedAlert:
        """Convert raw Prometheus alert to processed alert.

        Args:
            raw: Raw Prometheus alert

        Returns:
            ProcessedAlert object
        """
        severity = self.severity_mapper.map_severity(raw)

        # Determine resource type and name
        resource_type, resource_name = self._extract_resource_info(raw)

        # Compute fingerprint
        fingerprint = raw.fingerprint or raw.compute_fingerprint()

        return ProcessedAlert(
            fingerprint=fingerprint,
            alert_name=raw.alert_name,
            severity=severity,
            status=raw.status,
            namespace=raw.namespace,
            resource_type=resource_type,
            resource_name=resource_name,
            cluster_name=self.cluster_name,
            summary=raw.summary or f"Alert: {raw.alert_name}",
            description=raw.description or "",
            runbook_url=raw.runbook_url,
            first_seen=raw.starts_at or datetime.utcnow(),
            last_seen=datetime.utcnow(),
            occurrence_count=1,
            labels=raw.labels,
            annotations=raw.annotations,
        )

    def _extract_resource_info(
        self,
        raw: PrometheusAlert,
    ) -> Tuple[str, str]:
        """Extract resource type and name from alert.

        Args:
            raw: Raw alert

        Returns:
            Tuple of (resource_type, resource_name)
        """
        # Check for various resource types in order of specificity
        if raw.pod:
            return "Pod", raw.pod
        if raw.node:
            return "Node", raw.node
        if raw.service:
            return "Service", raw.service
        if raw.container:
            return "Container", raw.container

        # Check labels for other resource types
        labels = raw.labels
        if "deployment" in labels:
            return "Deployment", labels["deployment"]
        if "statefulset" in labels:
            return "StatefulSet", labels["statefulset"]
        if "daemonset" in labels:
            return "DaemonSet", labels["daemonset"]
        if "job" in labels:
            return "Job", labels["job"]
        if "cronjob" in labels:
            return "CronJob", labels["cronjob"]
        if "persistentvolumeclaim" in labels:
            return "PVC", labels["persistentvolumeclaim"]

        # Default
        return "Unknown", raw.alert_name

    def _should_process_namespace(self, namespace: str) -> bool:
        """Check if namespace should be processed.

        Args:
            namespace: Namespace name

        Returns:
            True if should process
        """
        import fnmatch

        # Check include list (if specified)
        if self.include_namespaces:
            matched = any(
                fnmatch.fnmatch(namespace, pattern)
                for pattern in self.include_namespaces
            )
            if not matched:
                return False

        # Check exclude list
        if self.exclude_namespaces:
            excluded = any(
                fnmatch.fnmatch(namespace, pattern)
                for pattern in self.exclude_namespaces
            )
            if excluded:
                return False

        return True

    def _check_rate_limit(self) -> bool:
        """Check if rate limit allows notification.

        Returns:
            True if allowed
        """
        now = datetime.utcnow()

        # Reset counter every minute
        elapsed = (now - self._last_rate_limit_reset).total_seconds()
        if elapsed >= 60:
            self._notification_count = 0
            self._last_rate_limit_reset = now

        # Check limit
        if self._notification_count >= self.max_notifications_per_minute:
            return False

        self._notification_count += 1
        return True

    def _severity_order(self, severity: AlertSeverity) -> int:
        """Get numeric order for severity.

        Args:
            severity: Alert severity

        Returns:
            Numeric order (higher = more severe)
        """
        order_map = {
            AlertSeverity.CRITICAL: 3,
            AlertSeverity.HIGH: 2,
            AlertSeverity.MEDIUM: 1,
        }
        return order_map.get(severity, 0)

    def _compare_severity(
        self,
        a: AlertSeverity,
        b: AlertSeverity,
    ) -> int:
        """Compare two severities.

        Returns:
            positive if a > b, negative if a < b, 0 if equal
        """
        return self._severity_order(a) - self._severity_order(b)

    def get_stats(self) -> Dict:
        """Get processor statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "cluster_name": self.cluster_name,
            "include_namespaces": self.include_namespaces,
            "exclude_namespaces": self.exclude_namespaces,
            "max_notifications_per_minute": self.max_notifications_per_minute,
            "current_notification_count": self._notification_count,
            "dedup_stats": self.dedup_store.get_stats(),
        }
