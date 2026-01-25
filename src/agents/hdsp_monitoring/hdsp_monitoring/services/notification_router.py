"""
Notification Router for HDSP Monitoring.

Routes alerts to appropriate notification channels based on severity.
- CRITICAL/HIGH: KakaoTalk (immediate) -> EventBridge fallback
- MEDIUM: EventBridge only
"""

import logging
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertGroup,
    AlertSeverity,
    NotificationResult,
    ProcessedAlert,
)
from src.agents.hdsp_monitoring.hdsp_monitoring.services.summary_generator import (
    AlertSummary,
    AlertSummaryGenerator,
)

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    """Notification channel types."""

    KAKAO = "kakao"
    EVENTBRIDGE = "eventbridge"
    MOCK = "mock"


class BaseNotificationSender(ABC):
    """Abstract base class for notification senders."""

    @abstractmethod
    def send(
        self,
        summary: AlertSummary,
        alerts: List[ProcessedAlert],
    ) -> NotificationResult:
        """Send notification.

        Args:
            summary: Alert summary
            alerts: List of alerts

        Returns:
            NotificationResult
        """
        pass


class KakaoNotificationSender(BaseNotificationSender):
    """KakaoTalk notification sender using bdp_common."""

    def __init__(self):
        """Initialize Kakao sender."""
        self._notifier = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy initialize Kakao notifier."""
        if self._initialized:
            return self._notifier is not None

        self._initialized = True
        try:
            from src.agents.bdp_common.kakao.notifier import KakaoNotifier
            self._notifier = KakaoNotifier()
            if not self._notifier.load_tokens():
                logger.warning(
                    "Kakao tokens not found. "
                    "Run token setup to enable KakaoTalk notifications."
                )
                self._notifier = None
                return False
            return True
        except ImportError as e:
            logger.warning(f"KakaoNotifier not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize KakaoNotifier: {e}")
            return False

    def send(
        self,
        summary: AlertSummary,
        alerts: List[ProcessedAlert],
    ) -> NotificationResult:
        """Send KakaoTalk notification.

        Args:
            summary: Alert summary
            alerts: List of alerts

        Returns:
            NotificationResult
        """
        if not self._ensure_initialized():
            return NotificationResult(
                success=False,
                channel="kakao",
                error="KakaoNotifier not initialized",
                alert_count=len(alerts),
            )

        try:
            # Build message for KakaoTalk
            message = f"{summary.title}\n\n{summary.message}"

            # Truncate if too long (KakaoTalk limit)
            if len(message) > 1000:
                message = message[:997] + "..."

            success = self._notifier.send_text_message(message)

            return NotificationResult(
                success=success,
                channel="kakao",
                message=summary.title if success else None,
                error=None if success else "Failed to send KakaoTalk message",
                alert_count=len(alerts),
            )

        except Exception as e:
            logger.error(f"KakaoTalk send failed: {e}")
            return NotificationResult(
                success=False,
                channel="kakao",
                error=str(e),
                alert_count=len(alerts),
            )


class EventBridgeNotificationSender(BaseNotificationSender):
    """EventBridge notification sender using bdp_common."""

    def __init__(
        self,
        event_bus: Optional[str] = None,
        source: str = "cd1-agent.hdsp-monitoring",
        detail_type: str = "K8s Alert",
    ):
        """Initialize EventBridge sender.

        Args:
            event_bus: EventBridge bus name
            source: Event source
            detail_type: Event detail type
        """
        self._publisher = None
        self._initialized = False
        self.event_bus = event_bus or os.environ.get("EVENT_BUS", "cd1-agent-events")
        self.source = source
        self.detail_type = detail_type

    def _ensure_initialized(self) -> bool:
        """Lazy initialize EventBridge publisher."""
        if self._initialized:
            return self._publisher is not None

        self._initialized = True
        try:
            from src.agents.bdp_common.eventbridge.publisher import EventPublisher
            self._publisher = EventPublisher(
                event_bus=self.event_bus,
                source=self.source,
                detail_type=self.detail_type,
            )
            return True
        except ImportError as e:
            logger.warning(f"EventPublisher not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize EventPublisher: {e}")
            return False

    def send(
        self,
        summary: AlertSummary,
        alerts: List[ProcessedAlert],
    ) -> NotificationResult:
        """Send EventBridge notification.

        Args:
            summary: Alert summary
            alerts: List of alerts

        Returns:
            NotificationResult
        """
        if not self._ensure_initialized():
            return NotificationResult(
                success=False,
                channel="eventbridge",
                error="EventPublisher not initialized",
                alert_count=len(alerts),
            )

        try:
            from src.agents.bdp_common.eventbridge.publisher import AlertEvent

            event = AlertEvent(
                alert_type="k8s_monitoring",
                severity=summary.severity_emoji,
                severity_level=alerts[0].severity.value if alerts else "medium",
                title=summary.title,
                message=summary.message,
                affected_resources=[
                    {
                        "type": a.resource_type,
                        "name": a.resource_name,
                        "namespace": a.namespace,
                        "alert_name": a.alert_name,
                    }
                    for a in alerts
                ],
                action_required=summary.critical_count > 0 or summary.high_count > 0,
                metadata={
                    "cluster_name": summary.cluster_name,
                    "total_count": summary.total_count,
                    "critical_count": summary.critical_count,
                    "high_count": summary.high_count,
                },
            )

            success = self._publisher.publish_event(event)

            return NotificationResult(
                success=success,
                channel="eventbridge",
                message=summary.title if success else None,
                error=None if success else "Failed to publish EventBridge event",
                alert_count=len(alerts),
            )

        except Exception as e:
            logger.error(f"EventBridge send failed: {e}")
            return NotificationResult(
                success=False,
                channel="eventbridge",
                error=str(e),
                alert_count=len(alerts),
            )


class MockNotificationSender(BaseNotificationSender):
    """Mock notification sender for testing."""

    def __init__(self):
        """Initialize mock sender."""
        self.sent_notifications: List[dict] = []

    def send(
        self,
        summary: AlertSummary,
        alerts: List[ProcessedAlert],
    ) -> NotificationResult:
        """Mock send notification.

        Args:
            summary: Alert summary
            alerts: List of alerts

        Returns:
            NotificationResult
        """
        self.sent_notifications.append({
            "summary": summary,
            "alerts": alerts,
        })
        logger.info(f"[MOCK] Notification sent: {summary.title}")

        return NotificationResult(
            success=True,
            channel="mock",
            message=summary.title,
            alert_count=len(alerts),
        )

    def get_sent_notifications(self) -> List[dict]:
        """Get list of sent notifications."""
        return self.sent_notifications.copy()

    def clear(self) -> None:
        """Clear sent notifications."""
        self.sent_notifications.clear()


class NotificationRouter:
    """
    Routes alerts to appropriate notification channels.

    Routing rules:
    - CRITICAL: KakaoTalk (immediate) -> EventBridge fallback
    - HIGH: KakaoTalk (immediate) -> EventBridge fallback
    - MEDIUM: EventBridge only
    """

    def __init__(
        self,
        kakao_enabled: Optional[bool] = None,
        eventbridge_enabled: Optional[bool] = None,
        use_mock: Optional[bool] = None,
    ):
        """Initialize notification router.

        Args:
            kakao_enabled: Enable KakaoTalk notifications
            eventbridge_enabled: Enable EventBridge notifications
            use_mock: Use mock senders
        """
        # Auto-detect settings from environment
        if use_mock is None:
            use_mock = os.environ.get("NOTIFICATION_MOCK", "").lower() == "true"

        if kakao_enabled is None:
            kakao_enabled = os.environ.get("KAKAO_ENABLED", "true").lower() == "true"

        if eventbridge_enabled is None:
            eventbridge_enabled = os.environ.get("EVENTBRIDGE_ENABLED", "true").lower() == "true"

        self.use_mock = use_mock
        self.kakao_enabled = kakao_enabled and not use_mock
        self.eventbridge_enabled = eventbridge_enabled and not use_mock

        # Initialize senders
        if use_mock:
            self._kakao_sender = MockNotificationSender()
            self._eventbridge_sender = MockNotificationSender()
        else:
            self._kakao_sender = KakaoNotificationSender() if kakao_enabled else None
            self._eventbridge_sender = EventBridgeNotificationSender() if eventbridge_enabled else None

        self._summary_generator = AlertSummaryGenerator()

        logger.info(
            f"NotificationRouter initialized: "
            f"kakao={self.kakao_enabled}, eventbridge={self.eventbridge_enabled}, "
            f"mock={use_mock}"
        )

    def route_alerts(
        self,
        alerts: List[ProcessedAlert],
    ) -> List[NotificationResult]:
        """Route alerts to appropriate channels based on severity.

        Args:
            alerts: List of processed alerts

        Returns:
            List of NotificationResult
        """
        if not alerts:
            logger.info("No alerts to route")
            return []

        results = []

        # Separate by severity
        critical_high = [
            a for a in alerts
            if a.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH)
        ]
        medium = [
            a for a in alerts
            if a.severity == AlertSeverity.MEDIUM
        ]

        # Route CRITICAL/HIGH to KakaoTalk first
        if critical_high:
            summary = self._summary_generator.generate_batch_summary(critical_high)

            # Try KakaoTalk
            if self._kakao_sender and self.kakao_enabled:
                kakao_result = self._kakao_sender.send(summary, critical_high)
                results.append(kakao_result)

                # Fallback to EventBridge if Kakao failed
                if not kakao_result.success and self._eventbridge_sender:
                    eb_result = self._eventbridge_sender.send(summary, critical_high)
                    results.append(eb_result)
            elif self._eventbridge_sender:
                # EventBridge only if Kakao not enabled
                eb_result = self._eventbridge_sender.send(summary, critical_high)
                results.append(eb_result)

        # Route MEDIUM to EventBridge only
        if medium and self._eventbridge_sender:
            summary = self._summary_generator.generate_batch_summary(medium)
            eb_result = self._eventbridge_sender.send(summary, medium)
            results.append(eb_result)

        return results

    def route_alert_groups(
        self,
        groups: List[AlertGroup],
    ) -> List[NotificationResult]:
        """Route alert groups to appropriate channels.

        Args:
            groups: List of alert groups

        Returns:
            List of NotificationResult
        """
        if not groups:
            return []

        results = []

        # Separate groups by severity
        critical_high_groups = [
            g for g in groups
            if g.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH)
        ]
        medium_groups = [
            g for g in groups
            if g.severity == AlertSeverity.MEDIUM
        ]

        # Route CRITICAL/HIGH groups
        for group in critical_high_groups:
            summary = self._summary_generator.generate_group_summary(group)

            if self._kakao_sender and self.kakao_enabled:
                kakao_result = self._kakao_sender.send(summary, group.alerts)
                results.append(kakao_result)

                if not kakao_result.success and self._eventbridge_sender:
                    eb_result = self._eventbridge_sender.send(summary, group.alerts)
                    results.append(eb_result)
            elif self._eventbridge_sender:
                eb_result = self._eventbridge_sender.send(summary, group.alerts)
                results.append(eb_result)

        # Route MEDIUM groups to EventBridge
        if medium_groups and self._eventbridge_sender:
            all_medium_alerts = []
            for g in medium_groups:
                all_medium_alerts.extend(g.alerts)

            if all_medium_alerts:
                summary = self._summary_generator.generate_batch_summary(all_medium_alerts)
                eb_result = self._eventbridge_sender.send(summary, all_medium_alerts)
                results.append(eb_result)

        return results

    def send_single_alert(
        self,
        alert: ProcessedAlert,
    ) -> NotificationResult:
        """Send notification for single alert.

        Args:
            alert: Processed alert

        Returns:
            NotificationResult
        """
        summary = self._summary_generator.generate(alert)

        if alert.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH):
            if self._kakao_sender and self.kakao_enabled:
                result = self._kakao_sender.send(summary, [alert])
                if result.success:
                    return result
                # Fallback
                if self._eventbridge_sender:
                    return self._eventbridge_sender.send(summary, [alert])
            elif self._eventbridge_sender:
                return self._eventbridge_sender.send(summary, [alert])
        else:
            if self._eventbridge_sender:
                return self._eventbridge_sender.send(summary, [alert])

        return NotificationResult(
            success=False,
            channel="none",
            error="No notification channel available",
            alert_count=1,
        )

    def get_mock_sender(self, channel: str) -> Optional[MockNotificationSender]:
        """Get mock sender for testing.

        Args:
            channel: "kakao" or "eventbridge"

        Returns:
            MockNotificationSender or None
        """
        if not self.use_mock:
            return None

        if channel == "kakao":
            return self._kakao_sender
        elif channel == "eventbridge":
            return self._eventbridge_sender
        return None
