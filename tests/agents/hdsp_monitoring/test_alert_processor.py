"""
Tests for alert processor.
"""

import pytest
from datetime import datetime, timedelta

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertSeverity,
    ProcessedAlert,
)


class TestAlertProcessor:
    """Tests for AlertProcessor."""

    def test_process_alerts_basic(self, alert_processor, mock_prometheus_alert):
        """Test basic alert processing."""
        alerts = [
            mock_prometheus_alert(
                alert_name="KubePodCrashLooping",
                namespace="spark",
                pod="pod-1",
            ),
            mock_prometheus_alert(
                alert_name="KubeNodeMemoryPressure",
                namespace="kube-system",
                pod="",
            ),
        ]

        all_processed, to_notify = alert_processor.process_alerts(alerts)

        assert len(all_processed) == 2
        assert all(isinstance(a, ProcessedAlert) for a in all_processed)

    def test_namespace_filtering_exclude(self, alert_processor, mock_prometheus_alert):
        """Test namespace exclusion filtering."""
        alerts = [
            mock_prometheus_alert(namespace="production"),
            mock_prometheus_alert(namespace="test-env"),  # Should be excluded
            mock_prometheus_alert(namespace="dev-sandbox"),  # Should be excluded
        ]

        all_processed, _ = alert_processor.process_alerts(alerts)

        # Only production should pass
        assert len(all_processed) == 1
        assert all_processed[0].namespace == "production"

    def test_severity_mapping(self, alert_processor, mock_prometheus_alert):
        """Test that severity is correctly mapped."""
        alerts = [
            mock_prometheus_alert(
                alert_name="KubePodCrashLooping",
                severity_label="warning",
            ),
        ]

        all_processed, _ = alert_processor.process_alerts(alerts)

        # KubePodCrashLooping should be mapped to CRITICAL via override
        assert all_processed[0].severity == AlertSeverity.CRITICAL

    def test_grouping(self, alert_processor, mock_processed_alert):
        """Test alert grouping by namespace:alertname."""
        alerts = [
            mock_processed_alert(
                alert_name="KubePodCrashLooping",
                namespace="spark",
                resource_name="pod-1",
            ),
            mock_processed_alert(
                alert_name="KubePodCrashLooping",
                namespace="spark",
                resource_name="pod-2",
            ),
            mock_processed_alert(
                alert_name="KubeNodeMemoryPressure",
                namespace="kube-system",
                resource_name="node-1",
            ),
        ]

        groups = alert_processor.group_alerts(alerts)

        assert len(groups) == 2

        # Check group keys
        group_keys = {g.group_key for g in groups}
        assert "spark:KubePodCrashLooping" in group_keys
        assert "kube-system:KubeNodeMemoryPressure" in group_keys

        # Check group counts
        spark_group = next(g for g in groups if "spark" in g.group_key)
        assert spark_group.total_count == 2

    def test_filter_by_severity(self, alert_processor, mock_processed_alert):
        """Test severity filtering."""
        alerts = [
            mock_processed_alert(severity=AlertSeverity.CRITICAL, resource_name="c1"),
            mock_processed_alert(severity=AlertSeverity.HIGH, resource_name="h1"),
            mock_processed_alert(severity=AlertSeverity.MEDIUM, resource_name="m1"),
        ]

        # Filter HIGH and above
        filtered = alert_processor.filter_by_severity(alerts, AlertSeverity.HIGH)
        assert len(filtered) == 2

        # Filter CRITICAL only
        filtered = alert_processor.filter_by_severity(alerts, AlertSeverity.CRITICAL)
        assert len(filtered) == 1
        assert filtered[0].severity == AlertSeverity.CRITICAL

    def test_get_alerts_for_kakao(self, alert_processor, mock_processed_alert):
        """Test filtering for KakaoTalk (CRITICAL/HIGH only)."""
        alerts = [
            mock_processed_alert(severity=AlertSeverity.CRITICAL, resource_name="c1"),
            mock_processed_alert(severity=AlertSeverity.HIGH, resource_name="h1"),
            mock_processed_alert(severity=AlertSeverity.MEDIUM, resource_name="m1"),
        ]

        kakao_alerts = alert_processor.get_alerts_for_kakao(alerts)

        assert len(kakao_alerts) == 2
        assert all(a.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH) for a in kakao_alerts)

    def test_resource_extraction_pod(self, alert_processor, mock_prometheus_alert):
        """Test resource info extraction for pods."""
        alert = mock_prometheus_alert(pod="my-pod-123")
        all_processed, _ = alert_processor.process_alerts([alert])

        assert all_processed[0].resource_type == "Pod"
        assert all_processed[0].resource_name == "my-pod-123"

    def test_rate_limiting(self, alert_processor, mock_prometheus_alert):
        """Test rate limiting."""
        # Create many alerts
        alerts = [
            mock_prometheus_alert(pod=f"pod-{i}", minutes_ago=i + 1)
            for i in range(20)
        ]

        # Clear dedup store to ensure fresh state
        alert_processor.dedup_store.clear()

        # Process all alerts
        _, to_notify = alert_processor.process_alerts(alerts)

        # Should be rate limited to max_notifications_per_minute
        assert len(to_notify) <= alert_processor.max_notifications_per_minute
