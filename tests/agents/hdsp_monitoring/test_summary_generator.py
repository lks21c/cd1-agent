"""
Tests for Korean summary generator.
"""

import pytest
from datetime import datetime, timedelta

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertSeverity,
    AlertGroup,
    ProcessedAlert,
)


class TestAlertSummaryGenerator:
    """Tests for AlertSummaryGenerator."""

    def test_generate_single_alert(self, summary_generator, mock_processed_alert):
        """Test single alert summary generation."""
        alert = mock_processed_alert(
            alert_name="KubePodCrashLooping",
            severity=AlertSeverity.CRITICAL,
        )

        summary = summary_generator.generate(alert)

        assert "K8s 알림" in summary.title
        assert "CrashLoopBackOff" in summary.title  # Korean translation
        assert "🚨" in summary.severity_emoji
        assert summary.critical_count == 1
        assert summary.total_count == 1

    def test_generate_high_severity(self, summary_generator, mock_processed_alert):
        """Test HIGH severity summary."""
        alert = mock_processed_alert(
            alert_name="KubeNodeMemoryPressure",
            severity=AlertSeverity.HIGH,
        )

        summary = summary_generator.generate(alert)

        assert "⚠️" in summary.severity_emoji
        assert "빠른 확인" in summary.message or "높음" in summary.message

    def test_generate_group_summary(self, summary_generator, mock_processed_alert):
        """Test group summary generation."""
        alerts = [
            mock_processed_alert(severity=AlertSeverity.CRITICAL, resource_name="p1"),
            mock_processed_alert(severity=AlertSeverity.CRITICAL, resource_name="p2"),
            mock_processed_alert(severity=AlertSeverity.HIGH, resource_name="p3"),
        ]

        group = AlertGroup(
            group_key="spark:KubePodCrashLooping",
            severity=AlertSeverity.CRITICAL,
            alerts=alerts,
        )

        summary = summary_generator.generate_group_summary(group)

        assert "3건" in summary.title or summary.total_count == 3
        assert summary.critical_count == 2
        assert summary.high_count == 1

    def test_generate_batch_summary(self, summary_generator, mock_processed_alert):
        """Test batch summary generation."""
        alerts = [
            mock_processed_alert(
                alert_name="KubePodCrashLooping",
                severity=AlertSeverity.CRITICAL,
                namespace="spark",
                resource_name="p1",
            ),
            mock_processed_alert(
                alert_name="KubeNodeMemoryPressure",
                severity=AlertSeverity.HIGH,
                namespace="kube-system",
                resource_name="node-1",
            ),
            mock_processed_alert(
                alert_name="KubeQuotaAlmostFull",
                severity=AlertSeverity.MEDIUM,
                namespace="default",
                resource_name="quota",
            ),
        ]

        summary = summary_generator.generate_batch_summary(alerts)

        assert "3건" in summary.title or summary.total_count == 3
        assert "심각도별" in summary.message or "심각" in summary.message
        assert "네임스페이스별" in summary.message or "spark" in summary.message

    def test_empty_batch(self, summary_generator):
        """Test empty batch returns proper message."""
        summary = summary_generator.generate_batch_summary([])

        assert "✅" in summary.severity_emoji or "정상" in summary.title
        assert summary.total_count == 0

    def test_message_includes_cluster(self, summary_generator, mock_processed_alert):
        """Test that message includes cluster name."""
        alert = mock_processed_alert(
            alert_name="KubePodCrashLooping",
            severity=AlertSeverity.CRITICAL,
        )
        alert.cluster_name = "production-cluster"

        summary = summary_generator.generate(alert)

        assert "production-cluster" in summary.message or summary.cluster_name == "production-cluster"

    def test_message_includes_namespace(self, summary_generator, mock_processed_alert):
        """Test that message includes namespace."""
        alert = mock_processed_alert(
            namespace="spark-jobs",
        )

        summary = summary_generator.generate(alert)

        assert "spark-jobs" in summary.message

    def test_advice_by_severity(self, summary_generator, mock_processed_alert):
        """Test that advice varies by severity."""
        critical_alert = mock_processed_alert(severity=AlertSeverity.CRITICAL)
        medium_alert = mock_processed_alert(
            severity=AlertSeverity.MEDIUM,
            alert_name="KubeQuotaAlmostFull",
        )

        critical_summary = summary_generator.generate(critical_alert)
        medium_summary = summary_generator.generate(medium_alert)

        # Critical should have urgent language
        assert "즉시" in critical_summary.message or "⚠️" in critical_summary.message
        # Medium should have monitoring language
        assert "모니터링" in medium_summary.message or "📌" in medium_summary.message

    def test_duration_in_message(self, summary_generator):
        """Test that duration is included in message."""
        alert = ProcessedAlert(
            fingerprint="test",
            alert_name="KubePodCrashLooping",
            severity=AlertSeverity.CRITICAL,
            namespace="default",
            resource_type="Pod",
            resource_name="test-pod",
            cluster_name="test",
            summary="Test",
            description="",
            first_seen=datetime.utcnow() - timedelta(minutes=25),
        )

        summary = summary_generator.generate(alert)

        # Should include duration
        assert "분" in summary.message or "지속시간" in summary.message
