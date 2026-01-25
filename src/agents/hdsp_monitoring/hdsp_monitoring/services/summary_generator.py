"""
Korean Alert Summary Generator.

Generates Korean-language alert messages for KakaoTalk notifications.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertGroup,
    AlertSeverity,
    ProcessedAlert,
)

logger = logging.getLogger(__name__)


@dataclass
class AlertSummary:
    """Alert summary for notification."""

    title: str
    message: str
    severity_emoji: str
    alert_name: str
    namespace: str
    resource_type: str
    resource_name: str
    cluster_name: str
    timestamp: str
    total_count: int
    critical_count: int
    high_count: int


class AlertSummaryGenerator:
    """
    Korean alert summary generator.

    Generates formatted messages for KakaoTalk and EventBridge notifications.
    """

    SEVERITY_EMOJI: Dict[AlertSeverity, str] = {
        AlertSeverity.CRITICAL: "🚨",
        AlertSeverity.HIGH: "⚠️",
        AlertSeverity.MEDIUM: "📊",
    }

    SEVERITY_KOREAN: Dict[AlertSeverity, str] = {
        AlertSeverity.CRITICAL: "심각",
        AlertSeverity.HIGH: "높음",
        AlertSeverity.MEDIUM: "보통",
    }

    RESOURCE_TYPE_KOREAN: Dict[str, str] = {
        "Pod": "파드",
        "Node": "노드",
        "Service": "서비스",
        "Deployment": "디플로이먼트",
        "StatefulSet": "스테이트풀셋",
        "DaemonSet": "데몬셋",
        "Job": "잡",
        "CronJob": "크론잡",
        "Container": "컨테이너",
        "PVC": "영구 볼륨",
        "Unknown": "리소스",
    }

    ALERT_NAME_KOREAN: Dict[str, str] = {
        "KubePodCrashLooping": "CrashLoopBackOff",
        "KubePodNotReady": "Pod 준비 안됨",
        "KubeNodeNotReady": "노드 준비 안됨",
        "KubeContainerOOMKilled": "OOM Killed",
        "KubeContainerTerminated": "컨테이너 종료됨",
        "TargetDown": "타겟 다운",
        "KubeNodeMemoryPressure": "메모리 부족",
        "KubeNodeDiskPressure": "디스크 부족",
        "KubeDeploymentReplicasMismatch": "레플리카 불일치",
        "KubeQuotaAlmostFull": "쿼터 임계치 도달",
    }

    ADVICE_TEMPLATE: Dict[AlertSeverity, str] = {
        AlertSeverity.CRITICAL: (
            "⚠️ 즉시 확인이 필요합니다.\n"
            "서비스에 영향을 줄 수 있는 상황입니다."
        ),
        AlertSeverity.HIGH: (
            "📢 빠른 확인을 권장합니다.\n"
            "성능 저하 또는 안정성 문제가 발생할 수 있습니다."
        ),
        AlertSeverity.MEDIUM: (
            "📌 모니터링이 필요합니다.\n"
            "현재 상황을 주시해 주세요."
        ),
    }

    def __init__(self):
        """Initialize summary generator."""
        pass

    def generate(self, alert: ProcessedAlert) -> AlertSummary:
        """Generate summary for single alert.

        Args:
            alert: Processed alert

        Returns:
            AlertSummary object
        """
        emoji = self.SEVERITY_EMOJI.get(alert.severity, "📊")
        severity_kr = self.SEVERITY_KOREAN.get(alert.severity, "보통")
        resource_kr = self.RESOURCE_TYPE_KOREAN.get(alert.resource_type, alert.resource_type)
        alert_name_kr = self.ALERT_NAME_KOREAN.get(alert.alert_name, alert.alert_name)

        # Build title
        title = f"{emoji} K8s 알림: {alert_name_kr}"

        # Build message
        message = self._build_single_message(alert, resource_kr, severity_kr)

        return AlertSummary(
            title=title,
            message=message,
            severity_emoji=emoji,
            alert_name=alert.alert_name,
            namespace=alert.namespace,
            resource_type=alert.resource_type,
            resource_name=alert.resource_name,
            cluster_name=alert.cluster_name,
            timestamp=datetime.utcnow().isoformat(),
            total_count=1,
            critical_count=1 if alert.severity == AlertSeverity.CRITICAL else 0,
            high_count=1 if alert.severity == AlertSeverity.HIGH else 0,
        )

    def generate_group_summary(
        self,
        group: AlertGroup,
        max_items: int = 5,
    ) -> AlertSummary:
        """Generate summary for alert group.

        Args:
            group: Alert group
            max_items: Max alerts to show in detail

        Returns:
            AlertSummary object
        """
        if not group.alerts:
            return self._empty_summary()

        emoji = self.SEVERITY_EMOJI.get(group.severity, "📊")
        alert_name_kr = self.ALERT_NAME_KOREAN.get(group.alert_name, group.alert_name)

        # Build title
        if group.total_count == 1:
            title = f"{emoji} K8s 알림: {alert_name_kr}"
        else:
            title = f"{emoji} K8s 알림: {alert_name_kr} ({group.total_count}건)"

        # Build message
        message = self._build_group_message(group, alert_name_kr, max_items)

        return AlertSummary(
            title=title,
            message=message,
            severity_emoji=emoji,
            alert_name=group.alert_name,
            namespace=group.namespace,
            resource_type=group.alerts[0].resource_type if group.alerts else "Unknown",
            resource_name="multiple" if group.total_count > 1 else group.alerts[0].resource_name,
            cluster_name=group.alerts[0].cluster_name if group.alerts else "on-prem-k8s",
            timestamp=datetime.utcnow().isoformat(),
            total_count=group.total_count,
            critical_count=group.critical_count,
            high_count=group.high_count,
        )

    def generate_batch_summary(
        self,
        alerts: List[ProcessedAlert],
        max_items: int = 5,
    ) -> AlertSummary:
        """Generate summary for batch of alerts.

        Args:
            alerts: List of processed alerts
            max_items: Max alerts to show

        Returns:
            AlertSummary object
        """
        if not alerts:
            return self._empty_summary()

        # Count by severity
        severity_counts = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.HIGH: 0,
            AlertSeverity.MEDIUM: 0,
        }
        for alert in alerts:
            severity_counts[alert.severity] += 1

        # Find highest severity
        highest = AlertSeverity.MEDIUM
        for sev in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]:
            if severity_counts[sev] > 0:
                highest = sev
                break

        emoji = self.SEVERITY_EMOJI.get(highest, "📊")

        # Build title
        title = f"{emoji} K8s 알림: {len(alerts)}건 탐지"

        # Build message
        message = self._build_batch_message(alerts, severity_counts, max_items)

        return AlertSummary(
            title=title,
            message=message,
            severity_emoji=emoji,
            alert_name="multiple",
            namespace="multiple",
            resource_type="multiple",
            resource_name="multiple",
            cluster_name=alerts[0].cluster_name if alerts else "on-prem-k8s",
            timestamp=datetime.utcnow().isoformat(),
            total_count=len(alerts),
            critical_count=severity_counts[AlertSeverity.CRITICAL],
            high_count=severity_counts[AlertSeverity.HIGH],
        )

    def _build_single_message(
        self,
        alert: ProcessedAlert,
        resource_kr: str,
        severity_kr: str,
    ) -> str:
        """Build message for single alert."""
        lines = [
            f"━━━━━━━━━━━━━━━━━━━━",
            f"🏷️ 클러스터: {alert.cluster_name}",
            f"📍 네임스페이스: {alert.namespace}",
            f"🔧 리소스: {resource_kr}/{alert.resource_name}",
            f"━━━━━━━━━━━━━━━━━━━━",
            "",
            "📋 알림 내용:",
            alert.summary or alert.description or f"Alert: {alert.alert_name}",
            "",
        ]

        # Add advice
        advice = self.ADVICE_TEMPLATE.get(alert.severity, "")
        if advice:
            lines.append("⚠️ 조치 권고:")
            lines.append(advice)
            lines.append("")

        # Add runbook if available
        if alert.runbook_url:
            lines.append(f"📖 Runbook: {alert.runbook_url}")
            lines.append("")

        # Footer
        lines.append(f"[심각도: {severity_kr.upper()} | 지속시간: {alert.duration_minutes}분]")

        return "\n".join(lines)

    def _build_group_message(
        self,
        group: AlertGroup,
        alert_name_kr: str,
        max_items: int,
    ) -> str:
        """Build message for alert group."""
        severity_kr = self.SEVERITY_KOREAN.get(group.severity, "보통")
        first_alert = group.alerts[0] if group.alerts else None
        cluster = first_alert.cluster_name if first_alert else "on-prem-k8s"

        lines = [
            f"━━━━━━━━━━━━━━━━━━━━",
            f"🏷️ 클러스터: {cluster}",
            f"📍 네임스페이스: {group.namespace}",
            f"📊 알림 유형: {alert_name_kr}",
            f"━━━━━━━━━━━━━━━━━━━━",
            "",
            f"총 {group.total_count}건의 알림이 발생했습니다.",
            "",
        ]

        if group.critical_count > 0 or group.high_count > 0:
            lines.append("📊 심각도별 현황:")
            if group.critical_count > 0:
                lines.append(f"  • 심각: {group.critical_count}건")
            if group.high_count > 0:
                lines.append(f"  • 높음: {group.high_count}건")
            medium_count = group.total_count - group.critical_count - group.high_count
            if medium_count > 0:
                lines.append(f"  • 보통: {medium_count}건")
            lines.append("")

        lines.append("📋 주요 항목:")
        for alert in group.alerts[:max_items]:
            emoji = self.SEVERITY_EMOJI.get(alert.severity, "📊")
            resource_kr = self.RESOURCE_TYPE_KOREAN.get(alert.resource_type, alert.resource_type)
            lines.append(f"  {emoji} {resource_kr}/{alert.resource_name}")

        if group.total_count > max_items:
            lines.append(f"  ... 외 {group.total_count - max_items}건")

        lines.append("")

        # Add advice for highest severity
        advice = self.ADVICE_TEMPLATE.get(group.severity, "")
        if advice:
            lines.append(advice)
            lines.append("")

        # Calculate duration from earliest
        duration = (datetime.utcnow() - group.earliest_first_seen).total_seconds() / 60
        lines.append(f"[심각도: {severity_kr.upper()} | 지속시간: {int(duration)}분]")

        return "\n".join(lines)

    def _build_batch_message(
        self,
        alerts: List[ProcessedAlert],
        severity_counts: Dict[AlertSeverity, int],
        max_items: int,
    ) -> str:
        """Build message for batch of alerts."""
        cluster = alerts[0].cluster_name if alerts else "on-prem-k8s"

        # Group by namespace
        by_namespace: Dict[str, List[ProcessedAlert]] = {}
        for alert in alerts:
            if alert.namespace not in by_namespace:
                by_namespace[alert.namespace] = []
            by_namespace[alert.namespace].append(alert)

        lines = [
            f"━━━━━━━━━━━━━━━━━━━━",
            f"🏷️ 클러스터: {cluster}",
            f"📊 총 {len(alerts)}건의 알림",
            f"━━━━━━━━━━━━━━━━━━━━",
            "",
            "📊 심각도별 현황:",
            f"  • 심각: {severity_counts[AlertSeverity.CRITICAL]}건",
            f"  • 높음: {severity_counts[AlertSeverity.HIGH]}건",
            f"  • 보통: {severity_counts[AlertSeverity.MEDIUM]}건",
            "",
            "📍 네임스페이스별:",
        ]

        for ns, ns_alerts in sorted(by_namespace.items(), key=lambda x: -len(x[1])):
            lines.append(f"  • {ns}: {len(ns_alerts)}건")

        lines.append("")
        lines.append("📋 주요 항목:")

        # Sort by severity and show top items
        sorted_alerts = sorted(
            alerts,
            key=lambda a: (
                -self._severity_order(a.severity),
                a.first_seen,
            ),
        )

        for alert in sorted_alerts[:max_items]:
            emoji = self.SEVERITY_EMOJI.get(alert.severity, "📊")
            alert_kr = self.ALERT_NAME_KOREAN.get(alert.alert_name, alert.alert_name)
            lines.append(f"  {emoji} {alert.namespace}/{alert.resource_name}")
            lines.append(f"     └ {alert_kr}")

        if len(alerts) > max_items:
            lines.append(f"  ... 외 {len(alerts) - max_items}건")

        lines.append("")

        # Determine highest severity for advice
        highest = AlertSeverity.MEDIUM
        if severity_counts[AlertSeverity.CRITICAL] > 0:
            highest = AlertSeverity.CRITICAL
        elif severity_counts[AlertSeverity.HIGH] > 0:
            highest = AlertSeverity.HIGH

        advice = self.ADVICE_TEMPLATE.get(highest, "")
        if advice:
            lines.append(advice)

        return "\n".join(lines)

    def _empty_summary(self) -> AlertSummary:
        """Return empty summary when no alerts."""
        return AlertSummary(
            title="✅ K8s 정상",
            message="현재 탐지된 알림이 없습니다.",
            severity_emoji="✅",
            alert_name="none",
            namespace="all",
            resource_type="none",
            resource_name="none",
            cluster_name="on-prem-k8s",
            timestamp=datetime.utcnow().isoformat(),
            total_count=0,
            critical_count=0,
            high_count=0,
        )

    def _severity_order(self, severity: AlertSeverity) -> int:
        """Get numeric order for severity."""
        return {
            AlertSeverity.CRITICAL: 3,
            AlertSeverity.HIGH: 2,
            AlertSeverity.MEDIUM: 1,
        }.get(severity, 0)
