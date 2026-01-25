"""
Tests for HDSP Monitoring data models.
"""

import pytest
from datetime import datetime, timedelta

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertSeverity,
    AlertStatus,
    PrometheusAlert,
    ProcessedAlert,
    AlertGroup,
    DeduplicationEntry,
)


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.HIGH.value == "high"
        assert AlertSeverity.MEDIUM.value == "medium"

    def test_severity_from_string(self):
        """Test creating severity from string."""
        assert AlertSeverity("critical") == AlertSeverity.CRITICAL
        assert AlertSeverity("high") == AlertSeverity.HIGH
        assert AlertSeverity("medium") == AlertSeverity.MEDIUM


class TestPrometheusAlert:
    """Tests for PrometheusAlert model."""

    def test_basic_creation(self, mock_prometheus_alert):
        """Test basic alert creation."""
        alert = mock_prometheus_alert()

        assert alert.alert_name == "KubePodCrashLooping"
        assert alert.status == AlertStatus.FIRING
        assert alert.namespace == "default"

    def test_label_extraction(self, mock_prometheus_alert):
        """Test label property extraction."""
        alert = mock_prometheus_alert(
            namespace="spark",
            pod="spark-executor-1",
        )

        assert alert.namespace == "spark"
        assert alert.pod == "spark-executor-1"
        assert alert.prometheus_severity == "critical"

    def test_annotation_extraction(self):
        """Test annotation extraction."""
        alert = PrometheusAlert(
            alert_name="TestAlert",
            labels={"alertname": "TestAlert"},
            annotations={
                "summary": "Test summary",
                "description": "Test description",
                "runbook_url": "https://example.com/runbook",
            },
        )

        assert alert.summary == "Test summary"
        assert alert.description == "Test description"
        assert alert.runbook_url == "https://example.com/runbook"

    def test_fingerprint_computation(self):
        """Test fingerprint computation."""
        alert1 = PrometheusAlert(
            alert_name="TestAlert",
            labels={
                "alertname": "TestAlert",
                "namespace": "default",
                "pod": "test-pod",
            },
            annotations={},
        )

        alert2 = PrometheusAlert(
            alert_name="TestAlert",
            labels={
                "alertname": "TestAlert",
                "namespace": "default",
                "pod": "test-pod",
            },
            annotations={},
        )

        # Same labels should produce same fingerprint
        assert alert1.compute_fingerprint() == alert2.compute_fingerprint()

        # Different pod should produce different fingerprint
        alert3 = PrometheusAlert(
            alert_name="TestAlert",
            labels={
                "alertname": "TestAlert",
                "namespace": "default",
                "pod": "other-pod",
            },
            annotations={},
        )
        assert alert1.compute_fingerprint() != alert3.compute_fingerprint()


class TestProcessedAlert:
    """Tests for ProcessedAlert model."""

    def test_basic_creation(self, mock_processed_alert):
        """Test basic processed alert creation."""
        alert = mock_processed_alert()

        assert alert.alert_name == "KubePodCrashLooping"
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.cluster_name == "test-cluster"

    def test_duration_calculation(self):
        """Test duration calculation."""
        alert = ProcessedAlert(
            fingerprint="test",
            alert_name="Test",
            severity=AlertSeverity.MEDIUM,
            namespace="default",
            resource_type="Pod",
            resource_name="test",
            cluster_name="test",
            summary="Test",
            description="",
            first_seen=datetime.utcnow() - timedelta(minutes=30),
        )

        assert alert.duration_minutes >= 29  # Allow for test execution time
        assert alert.is_long_running is True

    def test_to_dict(self, mock_processed_alert):
        """Test dictionary conversion."""
        alert = mock_processed_alert()
        data = alert.to_dict()

        assert data["alert_name"] == "KubePodCrashLooping"
        assert data["severity"] == "critical"
        assert "fingerprint" in data
        assert "duration_minutes" in data


class TestAlertGroup:
    """Tests for AlertGroup model."""

    def test_group_creation(self, mock_processed_alert):
        """Test alert group creation."""
        alerts = [
            mock_processed_alert(resource_name="pod-1"),
            mock_processed_alert(resource_name="pod-2"),
        ]

        group = AlertGroup(
            group_key="default:KubePodCrashLooping",
            severity=AlertSeverity.CRITICAL,
            alerts=alerts,
        )

        assert group.total_count == 2
        assert group.namespace == "default"
        assert group.alert_name == "KubePodCrashLooping"

    def test_severity_counts(self, mock_processed_alert):
        """Test severity counting in group."""
        alerts = [
            mock_processed_alert(severity=AlertSeverity.CRITICAL, resource_name="p1"),
            mock_processed_alert(severity=AlertSeverity.CRITICAL, resource_name="p2"),
            mock_processed_alert(severity=AlertSeverity.HIGH, resource_name="p3"),
        ]

        group = AlertGroup(
            group_key="default:Test",
            severity=AlertSeverity.CRITICAL,
            alerts=alerts,
        )

        assert group.critical_count == 2
        assert group.high_count == 1


class TestDeduplicationEntry:
    """Tests for DeduplicationEntry."""

    def test_should_notify_first_time(self):
        """Test first notification check."""
        entry = DeduplicationEntry(
            fingerprint="test",
            alert_name="Test",
            first_seen=datetime.utcnow() - timedelta(seconds=60),
            last_seen=datetime.utcnow(),
        )

        # First notification after 30s wait
        assert entry.should_notify() is True

    def test_should_not_notify_within_window(self):
        """Test deduplication within window."""
        entry = DeduplicationEntry(
            fingerprint="test",
            alert_name="Test",
            first_seen=datetime.utcnow() - timedelta(seconds=60),
            last_seen=datetime.utcnow(),
            notification_count=1,
            last_notified=datetime.utcnow() - timedelta(seconds=30),
        )

        # Recently notified, should not notify again
        assert entry.should_notify(repeat_interval_seconds=3600) is False

    def test_should_notify_after_repeat_interval(self):
        """Test repeat notification after interval."""
        entry = DeduplicationEntry(
            fingerprint="test",
            alert_name="Test",
            first_seen=datetime.utcnow() - timedelta(hours=2),
            last_seen=datetime.utcnow(),
            notification_count=1,
            last_notified=datetime.utcnow() - timedelta(hours=2),
        )

        # Last notification was 2 hours ago, should notify again
        assert entry.should_notify(repeat_interval_seconds=3600) is True
