"""
Prometheus Alertmanager Alert Fetcher.

Fetches firing alerts from Prometheus Alertmanager API.
"""

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    AlertStatus,
    PrometheusAlert,
)

logger = logging.getLogger(__name__)


class BaseAlertFetcher(ABC):
    """Abstract base class for alert fetchers."""

    @abstractmethod
    def fetch_firing_alerts(self) -> List[PrometheusAlert]:
        """Fetch all currently firing alerts.

        Returns:
            List of PrometheusAlert objects
        """
        pass

    @abstractmethod
    def fetch_alert_groups(self) -> List[Dict[str, Any]]:
        """Fetch alert groups from Alertmanager.

        Returns:
            List of alert group dictionaries
        """
        pass


class RealAlertFetcher(BaseAlertFetcher):
    """Real Alertmanager API fetcher."""

    def __init__(
        self,
        alertmanager_url: Optional[str] = None,
        timeout: int = 30,
        auth_token: Optional[str] = None,
    ):
        """Initialize real alert fetcher.

        Args:
            alertmanager_url: Alertmanager base URL
            timeout: Request timeout in seconds
            auth_token: Optional authentication token
        """
        self.alertmanager_url = (
            alertmanager_url
            or os.environ.get("ALERTMANAGER_URL", "http://localhost:9093")
        ).rstrip("/")
        self.timeout = timeout
        self.auth_token = auth_token or os.environ.get("ALERTMANAGER_AUTH_TOKEN")
        self._session = None

    def _get_session(self):
        """Get or create requests session."""
        if self._session is None:
            import requests
            self._session = requests.Session()
            if self.auth_token:
                self._session.headers["Authorization"] = f"Bearer {self.auth_token}"
        return self._session

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Make HTTP request to Alertmanager API.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            JSON response data
        """
        session = self._get_session()
        url = f"{self.alertmanager_url}{endpoint}"

        try:
            response = session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Alertmanager API error: {e}")
            raise

    def fetch_firing_alerts(self) -> List[PrometheusAlert]:
        """Fetch all currently firing alerts from Alertmanager.

        Returns:
            List of PrometheusAlert objects
        """
        try:
            # Alertmanager v2 API
            data = self._make_request("/api/v2/alerts", {"active": "true"})
            alerts = []

            for item in data:
                try:
                    # Parse Alertmanager v2 format
                    labels = item.get("labels", {})
                    annotations = item.get("annotations", {})

                    alert = PrometheusAlert(
                        alert_name=labels.get("alertname", "Unknown"),
                        status=AlertStatus(item.get("status", {}).get("state", "firing")),
                        labels=labels,
                        annotations=annotations,
                        starts_at=self._parse_datetime(item.get("startsAt")),
                        ends_at=self._parse_datetime(item.get("endsAt")),
                        fingerprint=item.get("fingerprint", ""),
                        generator_url=item.get("generatorURL"),
                    )
                    alerts.append(alert)
                except Exception as e:
                    logger.warning(f"Failed to parse alert: {e}")
                    continue

            logger.info(f"Fetched {len(alerts)} firing alerts from Alertmanager")
            return alerts

        except Exception as e:
            logger.error(f"Failed to fetch alerts: {e}")
            return []

    def fetch_alert_groups(self) -> List[Dict[str, Any]]:
        """Fetch alert groups from Alertmanager.

        Returns:
            List of alert group dictionaries
        """
        try:
            data = self._make_request("/api/v2/alerts/groups")
            logger.info(f"Fetched {len(data)} alert groups from Alertmanager")
            return data
        except Exception as e:
            logger.error(f"Failed to fetch alert groups: {e}")
            return []

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string from Alertmanager.

        Args:
            dt_str: ISO format datetime string

        Returns:
            datetime object or None
        """
        if not dt_str:
            return None

        try:
            # Handle various ISO formats
            if dt_str.endswith("Z"):
                dt_str = dt_str[:-1] + "+00:00"
            return datetime.fromisoformat(dt_str.replace("+00:00", ""))
        except ValueError:
            return None


class MockAlertFetcher(BaseAlertFetcher):
    """Mock alert fetcher for testing."""

    def __init__(self):
        """Initialize mock alert fetcher."""
        self._mock_alerts: List[PrometheusAlert] = []
        self._setup_default_alerts()

    def _setup_default_alerts(self) -> None:
        """Setup default mock alerts."""
        now = datetime.utcnow()

        self._mock_alerts = [
            # CRITICAL: CrashLoopBackOff
            PrometheusAlert(
                alert_name="KubePodCrashLooping",
                status=AlertStatus.FIRING,
                labels={
                    "alertname": "KubePodCrashLooping",
                    "namespace": "spark",
                    "pod": "spark-executor-abc123",
                    "container": "executor",
                    "severity": "critical",
                },
                annotations={
                    "summary": "Pod spark/spark-executor-abc123 is crash looping",
                    "description": "Pod has restarted 5 times in the last 10 minutes",
                    "runbook_url": "https://runbooks.example.com/KubePodCrashLooping",
                },
                starts_at=now - timedelta(minutes=25),
                fingerprint="abc123def456",
            ),
            # CRITICAL: OOMKilled
            PrometheusAlert(
                alert_name="KubeContainerOOMKilled",
                status=AlertStatus.FIRING,
                labels={
                    "alertname": "KubeContainerOOMKilled",
                    "namespace": "hdsp",
                    "pod": "data-processor-xyz789",
                    "container": "processor",
                    "severity": "critical",
                },
                annotations={
                    "summary": "Container OOMKilled in hdsp/data-processor-xyz789",
                    "description": "Container was terminated due to OOM",
                },
                starts_at=now - timedelta(minutes=10),
                fingerprint="xyz789ghi012",
            ),
            # HIGH: Memory Pressure
            PrometheusAlert(
                alert_name="KubeNodeMemoryPressure",
                status=AlertStatus.FIRING,
                labels={
                    "alertname": "KubeNodeMemoryPressure",
                    "node": "worker-node-3",
                    "severity": "warning",
                },
                annotations={
                    "summary": "Node worker-node-3 under memory pressure",
                    "description": "Node memory usage is above 90%",
                },
                starts_at=now - timedelta(minutes=15),
                fingerprint="node123mem456",
            ),
            # MEDIUM: Resource quota
            PrometheusAlert(
                alert_name="KubeQuotaAlmostFull",
                status=AlertStatus.FIRING,
                labels={
                    "alertname": "KubeQuotaAlmostFull",
                    "namespace": "default",
                    "resource": "cpu",
                    "severity": "info",
                },
                annotations={
                    "summary": "Namespace default CPU quota almost full",
                    "description": "CPU quota usage is at 85%",
                },
                starts_at=now - timedelta(minutes=30),
                fingerprint="quota123cpu456",
            ),
        ]

    def fetch_firing_alerts(self) -> List[PrometheusAlert]:
        """Return mock firing alerts.

        Returns:
            List of mock PrometheusAlert objects
        """
        logger.info(f"[MOCK] Returning {len(self._mock_alerts)} mock alerts")
        return self._mock_alerts.copy()

    def fetch_alert_groups(self) -> List[Dict[str, Any]]:
        """Return mock alert groups.

        Returns:
            List of mock alert group dictionaries
        """
        groups = {}
        for alert in self._mock_alerts:
            key = f"{alert.namespace}:{alert.alert_name}"
            if key not in groups:
                groups[key] = {
                    "labels": {"namespace": alert.namespace, "alertname": alert.alert_name},
                    "alerts": [],
                }
            groups[key]["alerts"].append(alert.model_dump())

        return list(groups.values())

    def inject_alert(self, alert: PrometheusAlert) -> None:
        """Inject a custom alert for testing.

        Args:
            alert: Alert to inject
        """
        self._mock_alerts.append(alert)
        logger.info(f"[MOCK] Injected alert: {alert.alert_name}")

    def clear_alerts(self) -> None:
        """Clear all mock alerts."""
        self._mock_alerts.clear()
        logger.info("[MOCK] Cleared all mock alerts")

    def reset_to_defaults(self) -> None:
        """Reset to default mock alerts."""
        self._mock_alerts.clear()
        self._setup_default_alerts()
        logger.info("[MOCK] Reset to default mock alerts")


class PrometheusAlertFetcher:
    """Alert fetcher with automatic provider selection."""

    def __init__(
        self,
        alertmanager_url: Optional[str] = None,
        use_mock: Optional[bool] = None,
    ):
        """Initialize alert fetcher.

        Args:
            alertmanager_url: Alertmanager URL (for real provider)
            use_mock: Force mock mode (auto-detect if None)
        """
        # Auto-detect provider
        if use_mock is None:
            use_mock = os.environ.get("PROMETHEUS_MOCK", "").lower() == "true"

        if use_mock:
            self._provider = MockAlertFetcher()
            logger.info("Using Mock Alert Fetcher")
        else:
            self._provider = RealAlertFetcher(alertmanager_url=alertmanager_url)
            logger.info(f"Using Real Alert Fetcher: {alertmanager_url or 'default'}")

        self._is_mock = use_mock

    @property
    def is_mock(self) -> bool:
        """Check if using mock provider."""
        return self._is_mock

    @property
    def provider(self) -> BaseAlertFetcher:
        """Get underlying provider."""
        return self._provider

    def fetch_firing_alerts(self) -> List[PrometheusAlert]:
        """Fetch all currently firing alerts.

        Returns:
            List of PrometheusAlert objects
        """
        return self._provider.fetch_firing_alerts()

    def fetch_alert_groups(self) -> List[Dict[str, Any]]:
        """Fetch alert groups.

        Returns:
            List of alert group dictionaries
        """
        return self._provider.fetch_alert_groups()


def create_alert_fetcher(
    alertmanager_url: Optional[str] = None,
    use_mock: Optional[bool] = None,
) -> PrometheusAlertFetcher:
    """Factory function to create alert fetcher.

    Args:
        alertmanager_url: Alertmanager URL
        use_mock: Force mock mode

    Returns:
        PrometheusAlertFetcher instance
    """
    return PrometheusAlertFetcher(
        alertmanager_url=alertmanager_url,
        use_mock=use_mock,
    )
