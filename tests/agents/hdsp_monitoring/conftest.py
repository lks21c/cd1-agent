"""
Test fixtures for HDSP Monitoring tests.
"""

import os
import pytest
from datetime import datetime, timedelta

# Set test environment
os.environ["PROMETHEUS_MOCK"] = "true"
os.environ["NOTIFICATION_MOCK"] = "true"
os.environ["KAKAO_ENABLED"] = "false"
os.environ["HDSP_CLUSTER_NAME"] = "test-cluster"


@pytest.fixture
def mock_prometheus_alert():
    """Create a mock Prometheus alert."""
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
        PrometheusAlert,
        AlertStatus,
    )

    def _create_alert(
        alert_name: str = "KubePodCrashLooping",
        namespace: str = "default",
        pod: str = "test-pod",
        severity_label: str = "critical",
        minutes_ago: int = 10,
    ) -> PrometheusAlert:
        return PrometheusAlert(
            alert_name=alert_name,
            status=AlertStatus.FIRING,
            labels={
                "alertname": alert_name,
                "namespace": namespace,
                "pod": pod,
                "severity": severity_label,
            },
            annotations={
                "summary": f"Test alert: {alert_name}",
                "description": f"Test description for {alert_name}",
            },
            starts_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
            fingerprint=f"{alert_name}-{namespace}-{pod}",
        )

    return _create_alert


@pytest.fixture
def mock_processed_alert():
    """Create a mock processed alert."""
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
        ProcessedAlert,
        AlertSeverity,
    )

    def _create_alert(
        alert_name: str = "KubePodCrashLooping",
        severity: AlertSeverity = AlertSeverity.CRITICAL,
        namespace: str = "default",
        resource_name: str = "test-pod",
    ) -> ProcessedAlert:
        return ProcessedAlert(
            fingerprint=f"{alert_name}-{namespace}-{resource_name}",
            alert_name=alert_name,
            severity=severity,
            namespace=namespace,
            resource_type="Pod",
            resource_name=resource_name,
            cluster_name="test-cluster",
            summary=f"Test alert: {alert_name}",
            description="Test description",
            first_seen=datetime.utcnow() - timedelta(minutes=10),
        )

    return _create_alert


@pytest.fixture
def severity_mapper():
    """Create a severity mapper instance."""
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.severity_mapper import (
        SeverityMapper,
    )
    return SeverityMapper()


@pytest.fixture
def dedup_store():
    """Create a fresh deduplication store."""
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.deduplication_store import (
        DeduplicationStore,
    )
    return DeduplicationStore()


@pytest.fixture
def alert_processor():
    """Create an alert processor instance."""
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.alert_processor import (
        AlertProcessor,
    )
    return AlertProcessor(cluster_name="test-cluster")


@pytest.fixture
def summary_generator():
    """Create a summary generator instance."""
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.summary_generator import (
        AlertSummaryGenerator,
    )
    return AlertSummaryGenerator()


@pytest.fixture
def notification_router():
    """Create a mock notification router."""
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.notification_router import (
        NotificationRouter,
    )
    return NotificationRouter(use_mock=True)


@pytest.fixture
def alert_fetcher():
    """Create a mock alert fetcher."""
    from src.agents.hdsp_monitoring.hdsp_monitoring.services.prometheus_alert_fetcher import (
        PrometheusAlertFetcher,
    )
    return PrometheusAlertFetcher(use_mock=True)
