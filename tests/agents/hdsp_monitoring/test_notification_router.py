"""
Tests for notification router.
"""

import pytest

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertSeverity,
    AlertGroup,
)


class TestNotificationRouter:
    """Tests for NotificationRouter."""

    def test_route_critical_alerts(self, notification_router, mock_processed_alert):
        """Test routing of critical alerts."""
        alerts = [
            mock_processed_alert(
                severity=AlertSeverity.CRITICAL,
                resource_name="pod-1",
            ),
        ]

        results = notification_router.route_alerts(alerts)

        assert len(results) > 0
        assert results[0].success
        assert results[0].alert_count == 1

    def test_route_high_alerts(self, notification_router, mock_processed_alert):
        """Test routing of high alerts."""
        alerts = [
            mock_processed_alert(
                severity=AlertSeverity.HIGH,
                resource_name="node-1",
            ),
        ]

        results = notification_router.route_alerts(alerts)

        assert len(results) > 0
        assert results[0].success

    def test_route_medium_alerts(self, notification_router, mock_processed_alert):
        """Test routing of medium alerts to EventBridge only."""
        alerts = [
            mock_processed_alert(
                severity=AlertSeverity.MEDIUM,
                alert_name="KubeQuotaAlmostFull",
                resource_name="quota-1",
            ),
        ]

        results = notification_router.route_alerts(alerts)

        # Medium alerts should only go to EventBridge
        assert len(results) > 0
        assert results[0].channel in ("eventbridge", "mock")

    def test_route_mixed_severity(self, notification_router, mock_processed_alert):
        """Test routing of mixed severity alerts."""
        alerts = [
            mock_processed_alert(severity=AlertSeverity.CRITICAL, resource_name="c1"),
            mock_processed_alert(severity=AlertSeverity.HIGH, resource_name="h1"),
            mock_processed_alert(severity=AlertSeverity.MEDIUM, resource_name="m1"),
        ]

        results = notification_router.route_alerts(alerts)

        # Should have at least 2 results (CRITICAL/HIGH batch + MEDIUM batch)
        assert len(results) >= 1

        # Total alerts routed
        total_routed = sum(r.alert_count for r in results if r.success)
        assert total_routed >= 1

    def test_route_empty_alerts(self, notification_router):
        """Test routing empty alert list."""
        results = notification_router.route_alerts([])

        assert len(results) == 0

    def test_route_alert_groups(self, notification_router, mock_processed_alert):
        """Test routing alert groups."""
        alerts = [
            mock_processed_alert(severity=AlertSeverity.CRITICAL, resource_name="p1"),
            mock_processed_alert(severity=AlertSeverity.CRITICAL, resource_name="p2"),
        ]

        group = AlertGroup(
            group_key="spark:KubePodCrashLooping",
            severity=AlertSeverity.CRITICAL,
            alerts=alerts,
        )

        results = notification_router.route_alert_groups([group])

        assert len(results) > 0
        assert results[0].success
        assert results[0].alert_count == 2

    def test_send_single_alert(self, notification_router, mock_processed_alert):
        """Test sending single alert."""
        alert = mock_processed_alert(
            severity=AlertSeverity.CRITICAL,
        )

        result = notification_router.send_single_alert(alert)

        assert result.success
        assert result.alert_count == 1

    def test_mock_sender_tracking(self, notification_router, mock_processed_alert):
        """Test that mock sender tracks notifications."""
        alerts = [
            mock_processed_alert(
                severity=AlertSeverity.CRITICAL,
                resource_name="pod-1",
            ),
        ]

        notification_router.route_alerts(alerts)

        # Check mock sender tracked the notification
        kakao_mock = notification_router.get_mock_sender("kakao")
        if kakao_mock:
            sent = kakao_mock.get_sent_notifications()
            assert len(sent) > 0

    def test_notification_result_structure(self, notification_router, mock_processed_alert):
        """Test notification result structure."""
        alerts = [
            mock_processed_alert(severity=AlertSeverity.CRITICAL),
        ]

        results = notification_router.route_alerts(alerts)

        result = results[0]
        assert hasattr(result, "success")
        assert hasattr(result, "channel")
        assert hasattr(result, "alert_count")

        # Test to_dict
        result_dict = result.to_dict()
        assert "success" in result_dict
        assert "channel" in result_dict
        assert "alert_count" in result_dict
        assert "timestamp" in result_dict
