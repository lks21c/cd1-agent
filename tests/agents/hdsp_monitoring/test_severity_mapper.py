"""
Tests for severity mapper.
"""

import pytest

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertSeverity,
    AlertStatus,
    PrometheusAlert,
)


class TestSeverityMapper:
    """Tests for SeverityMapper."""

    def test_alert_name_override_critical(self, severity_mapper, mock_prometheus_alert):
        """Test critical alert name overrides."""
        critical_alerts = [
            "KubePodCrashLooping",
            "KubeContainerOOMKilled",
            "KubeNodeNotReady",
            "TargetDown",
        ]

        for alert_name in critical_alerts:
            alert = mock_prometheus_alert(alert_name=alert_name, severity_label="warning")
            result = severity_mapper.map_severity(alert)
            assert result == AlertSeverity.CRITICAL, f"{alert_name} should be CRITICAL"

    def test_alert_name_override_high(self, severity_mapper, mock_prometheus_alert):
        """Test high alert name overrides."""
        high_alerts = [
            "KubeNodeMemoryPressure",
            "KubeNodeDiskPressure",
            "KubeDeploymentReplicasMismatch",
        ]

        for alert_name in high_alerts:
            alert = mock_prometheus_alert(alert_name=alert_name, severity_label="info")
            result = severity_mapper.map_severity(alert)
            assert result == AlertSeverity.HIGH, f"{alert_name} should be HIGH"

    def test_label_mapping_critical(self, severity_mapper, mock_prometheus_alert):
        """Test label-based mapping to critical."""
        for label in ["critical", "error", "page"]:
            alert = mock_prometheus_alert(
                alert_name="CustomAlert",
                severity_label=label,
            )
            result = severity_mapper.map_severity(alert)
            assert result == AlertSeverity.CRITICAL, f"Label '{label}' should map to CRITICAL"

    def test_label_mapping_high(self, severity_mapper, mock_prometheus_alert):
        """Test label-based mapping to high."""
        for label in ["warning", "high", "warn"]:
            alert = mock_prometheus_alert(
                alert_name="CustomAlert",
                severity_label=label,
            )
            result = severity_mapper.map_severity(alert)
            assert result == AlertSeverity.HIGH, f"Label '{label}' should map to HIGH"

    def test_label_mapping_medium(self, severity_mapper, mock_prometheus_alert):
        """Test label-based mapping to medium."""
        for label in ["info", "medium", "low"]:
            alert = mock_prometheus_alert(
                alert_name="CustomAlert",
                severity_label=label,
            )
            result = severity_mapper.map_severity(alert)
            assert result == AlertSeverity.MEDIUM, f"Label '{label}' should map to MEDIUM"

    def test_keyword_pattern_critical(self, severity_mapper):
        """Test keyword pattern matching for critical."""
        alert = PrometheusAlert(
            alert_name="SomethingDown",
            labels={"alertname": "SomethingDown", "severity": "warning"},
            annotations={},
        )
        result = severity_mapper.map_severity(alert)
        assert result == AlertSeverity.CRITICAL

    def test_keyword_pattern_high(self, severity_mapper):
        """Test keyword pattern matching for high."""
        alert = PrometheusAlert(
            alert_name="MemoryPressureDetected",
            labels={"alertname": "MemoryPressureDetected", "severity": "unknown"},
            annotations={},
        )
        result = severity_mapper.map_severity(alert)
        assert result == AlertSeverity.HIGH

    def test_default_medium(self, severity_mapper):
        """Test default to medium for unknown alerts."""
        alert = PrometheusAlert(
            alert_name="SomeRandomAlert",
            labels={"alertname": "SomeRandomAlert", "severity": "unknown"},
            annotations={},
        )
        result = severity_mapper.map_severity(alert)
        assert result == AlertSeverity.MEDIUM

    def test_add_override(self, severity_mapper, mock_prometheus_alert):
        """Test adding custom override."""
        severity_mapper.add_override("CustomCritical", AlertSeverity.CRITICAL)

        alert = mock_prometheus_alert(
            alert_name="CustomCritical",
            severity_label="info",
        )
        result = severity_mapper.map_severity(alert)
        assert result == AlertSeverity.CRITICAL

    def test_remove_override(self, severity_mapper, mock_prometheus_alert):
        """Test removing override."""
        # Remove existing override
        result = severity_mapper.remove_override("KubePodCrashLooping")
        assert result is True

        # Now it should use label-based mapping
        alert = mock_prometheus_alert(
            alert_name="KubePodCrashLooping",
            severity_label="info",
        )
        result = severity_mapper.map_severity(alert)
        assert result == AlertSeverity.MEDIUM  # Falls back to label mapping
