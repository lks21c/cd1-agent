"""
Prometheus Client with Provider Abstraction.

Supports real Prometheus/VictoriaMetrics and mock providers for testing.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class PrometheusProvider(str, Enum):
    """Supported Prometheus provider modes."""

    REAL = "real"
    MOCK = "mock"


class PrometheusQueryResult:
    """Prometheus query result wrapper."""

    def __init__(
        self,
        metric_name: str,
        labels: Dict[str, str],
        values: List[tuple],  # List of (timestamp, value)
    ):
        self.metric_name = metric_name
        self.labels = labels
        self.values = values

    @property
    def latest_value(self) -> Optional[float]:
        """Get the latest value."""
        if self.values:
            return float(self.values[-1][1])
        return None

    @property
    def average_value(self) -> Optional[float]:
        """Calculate average value."""
        if self.values:
            return sum(float(v[1]) for v in self.values) / len(self.values)
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_name": self.metric_name,
            "labels": self.labels,
            "values": self.values,
            "latest_value": self.latest_value,
            "average_value": self.average_value,
        }


class BasePrometheusProvider(ABC):
    """Abstract base class for Prometheus providers."""

    @abstractmethod
    def query(
        self,
        query: str,
        time: Optional[datetime] = None,
    ) -> List[PrometheusQueryResult]:
        """Execute instant query."""
        pass

    @abstractmethod
    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s",
    ) -> List[PrometheusQueryResult]:
        """Execute range query."""
        pass

    @abstractmethod
    def get_metric_metadata(
        self,
        metric_name: str,
    ) -> Dict[str, Any]:
        """Get metric metadata."""
        pass


class RealPrometheusProvider(BasePrometheusProvider):
    """Real Prometheus/VictoriaMetrics provider."""

    def __init__(
        self,
        base_url: str,
        auth_token: Optional[str] = None,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
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
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Make HTTP request to Prometheus API."""
        session = self._get_session()
        url = f"{self.base_url}{endpoint}"

        try:
            response = session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Prometheus API error: {e}")
            raise

    def _parse_result(
        self,
        data: Dict[str, Any],
        result_type: str = "vector",
    ) -> List[PrometheusQueryResult]:
        """Parse Prometheus API response."""
        results = []

        if data.get("status") != "success":
            logger.warning(f"Prometheus query failed: {data.get('error', 'Unknown error')}")
            return results

        result_data = data.get("data", {})
        result_items = result_data.get("result", [])

        for item in result_items:
            metric = item.get("metric", {})
            metric_name = metric.pop("__name__", "unknown")
            labels = metric

            if result_type == "vector":
                # Instant query: [timestamp, value]
                value = item.get("value", [])
                values = [tuple(value)] if value else []
            else:
                # Range query: [[timestamp, value], ...]
                values = [tuple(v) for v in item.get("values", [])]

            results.append(PrometheusQueryResult(
                metric_name=metric_name,
                labels=labels,
                values=values,
            ))

        return results

    def query(
        self,
        query: str,
        time: Optional[datetime] = None,
    ) -> List[PrometheusQueryResult]:
        """Execute instant query."""
        params = {"query": query}
        if time:
            params["time"] = time.timestamp()

        data = self._make_request("/api/v1/query", params)
        return self._parse_result(data, "vector")

    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s",
    ) -> List[PrometheusQueryResult]:
        """Execute range query."""
        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step,
        }

        data = self._make_request("/api/v1/query_range", params)
        return self._parse_result(data, "matrix")

    def get_metric_metadata(
        self,
        metric_name: str,
    ) -> Dict[str, Any]:
        """Get metric metadata."""
        params = {"metric": metric_name}
        data = self._make_request("/api/v1/metadata", params)

        if data.get("status") == "success":
            return data.get("data", {}).get(metric_name, [{}])[0]
        return {}


class MockPrometheusProvider(BasePrometheusProvider):
    """Mock Prometheus provider for testing."""

    def __init__(self):
        self._mock_data: Dict[str, List[PrometheusQueryResult]] = {}
        self._setup_default_mock_data()

    def _setup_default_mock_data(self):
        """Setup default mock data for common K8s metrics."""
        now = datetime.now()
        timestamps = [
            (now - timedelta(minutes=i)).timestamp()
            for i in range(5, 0, -1)
        ]

        # Pod restart count mock
        self._mock_data["kube_pod_container_status_restarts_total"] = [
            PrometheusQueryResult(
                metric_name="kube_pod_container_status_restarts_total",
                labels={
                    "namespace": "default",
                    "pod": "app-deployment-abc123",
                    "container": "app",
                },
                values=[(ts, str(i)) for i, ts in enumerate(timestamps)],
            ),
            PrometheusQueryResult(
                metric_name="kube_pod_container_status_restarts_total",
                labels={
                    "namespace": "spark",
                    "pod": "spark-executor-xyz789",
                    "container": "spark",
                },
                values=[(ts, str(i * 2)) for i, ts in enumerate(timestamps)],
            ),
        ]

        # CrashLoopBackOff mock
        self._mock_data["kube_pod_container_status_waiting_reason"] = [
            PrometheusQueryResult(
                metric_name="kube_pod_container_status_waiting_reason",
                labels={
                    "namespace": "spark",
                    "pod": "spark-executor-failed",
                    "container": "spark",
                    "reason": "CrashLoopBackOff",
                },
                values=[(timestamps[-1], "1")],
            ),
        ]

        # OOMKilled mock
        self._mock_data["kube_pod_container_status_last_terminated_reason"] = [
            PrometheusQueryResult(
                metric_name="kube_pod_container_status_last_terminated_reason",
                labels={
                    "namespace": "hdsp",
                    "pod": "data-processor-oom",
                    "container": "processor",
                    "reason": "OOMKilled",
                },
                values=[(timestamps[-1], "1")],
            ),
        ]

        # Node status mock
        self._mock_data["kube_node_status_condition"] = [
            PrometheusQueryResult(
                metric_name="kube_node_status_condition",
                labels={
                    "node": "worker-node-1",
                    "condition": "Ready",
                    "status": "true",
                },
                values=[(timestamps[-1], "1")],
            ),
            PrometheusQueryResult(
                metric_name="kube_node_status_condition",
                labels={
                    "node": "worker-node-2",
                    "condition": "MemoryPressure",
                    "status": "true",
                },
                values=[(timestamps[-1], "1")],
            ),
        ]

        # CPU usage mock
        self._mock_data["container_cpu_usage_seconds_total"] = [
            PrometheusQueryResult(
                metric_name="container_cpu_usage_seconds_total",
                labels={
                    "namespace": "default",
                    "pod": "high-cpu-app",
                    "container": "app",
                },
                values=[(ts, str(0.85 + i * 0.02)) for i, ts in enumerate(timestamps)],
            ),
        ]

        # Memory usage mock
        self._mock_data["container_memory_working_set_bytes"] = [
            PrometheusQueryResult(
                metric_name="container_memory_working_set_bytes",
                labels={
                    "namespace": "hdsp",
                    "pod": "high-memory-app",
                    "container": "app",
                },
                values=[(ts, str(int(3.5e9 + i * 1e8))) for i, ts in enumerate(timestamps)],
            ),
        ]

        # Resource limits mock
        self._mock_data["kube_pod_container_resource_limits"] = [
            PrometheusQueryResult(
                metric_name="kube_pod_container_resource_limits",
                labels={
                    "namespace": "hdsp",
                    "pod": "high-memory-app",
                    "container": "app",
                    "resource": "memory",
                },
                values=[(timestamps[-1], str(int(4e9)))],
            ),
            PrometheusQueryResult(
                metric_name="kube_pod_container_resource_limits",
                labels={
                    "namespace": "default",
                    "pod": "high-cpu-app",
                    "container": "app",
                    "resource": "cpu",
                },
                values=[(timestamps[-1], "1")],
            ),
        ]

    def set_mock_data(
        self,
        metric_name: str,
        results: List[PrometheusQueryResult],
    ):
        """Set mock data for a specific metric."""
        self._mock_data[metric_name] = results

    def inject_anomaly(
        self,
        anomaly_type: str,
        namespace: str = "default",
        pod: str = "test-pod",
        severity: str = "high",
    ):
        """Inject anomaly for testing."""
        now = datetime.now()
        timestamp = now.timestamp()

        if anomaly_type == "crash_loop":
            self._mock_data.setdefault("kube_pod_container_status_waiting_reason", []).append(
                PrometheusQueryResult(
                    metric_name="kube_pod_container_status_waiting_reason",
                    labels={
                        "namespace": namespace,
                        "pod": pod,
                        "container": "main",
                        "reason": "CrashLoopBackOff",
                    },
                    values=[(timestamp, "1")],
                )
            )
        elif anomaly_type == "oom_killed":
            self._mock_data.setdefault("kube_pod_container_status_last_terminated_reason", []).append(
                PrometheusQueryResult(
                    metric_name="kube_pod_container_status_last_terminated_reason",
                    labels={
                        "namespace": namespace,
                        "pod": pod,
                        "container": "main",
                        "reason": "OOMKilled",
                    },
                    values=[(timestamp, "1")],
                )
            )
        elif anomaly_type == "node_pressure":
            self._mock_data.setdefault("kube_node_status_condition", []).append(
                PrometheusQueryResult(
                    metric_name="kube_node_status_condition",
                    labels={
                        "node": pod,
                        "condition": "MemoryPressure",
                        "status": "true",
                    },
                    values=[(timestamp, "1")],
                )
            )
        elif anomaly_type == "high_cpu":
            self._mock_data.setdefault("container_cpu_usage_seconds_total", []).append(
                PrometheusQueryResult(
                    metric_name="container_cpu_usage_seconds_total",
                    labels={
                        "namespace": namespace,
                        "pod": pod,
                        "container": "main",
                    },
                    values=[(timestamp, "0.95")],
                )
            )

    def _match_query(self, query: str) -> List[PrometheusQueryResult]:
        """Match query to mock data."""
        results = []

        # Simple metric name extraction from query
        for metric_name, data in self._mock_data.items():
            if metric_name in query:
                # Apply basic label filtering from query
                for result in data:
                    if self._matches_query_filters(query, result):
                        results.append(result)

        return results

    def _matches_query_filters(
        self,
        query: str,
        result: PrometheusQueryResult,
    ) -> bool:
        """Check if result matches query filters."""
        # Simple filter matching for common patterns
        import re

        # Match patterns like {label="value"}
        label_pattern = r'\{([^}]+)\}'
        match = re.search(label_pattern, query)

        if not match:
            return True

        filter_str = match.group(1)
        filters = {}

        # Parse filters like: namespace="default", reason="OOMKilled"
        for f in filter_str.split(","):
            f = f.strip()
            if "=" in f:
                # Handle both = and =~ operators
                if "=~" in f:
                    key, value = f.split("=~", 1)
                    # Regex match - simplified
                    filters[key.strip()] = ("regex", value.strip().strip('"\''))
                elif "!=" in f:
                    key, value = f.split("!=", 1)
                    filters[key.strip()] = ("neq", value.strip().strip('"\''))
                else:
                    key, value = f.split("=", 1)
                    filters[key.strip()] = ("eq", value.strip().strip('"\''))

        for key, (op, value) in filters.items():
            label_value = result.labels.get(key, "")
            if op == "eq" and label_value != value:
                return False
            elif op == "neq" and label_value == value:
                return False
            elif op == "regex":
                if not re.match(value, label_value):
                    return False

        return True

    def query(
        self,
        query: str,
        time: Optional[datetime] = None,
    ) -> List[PrometheusQueryResult]:
        """Execute instant query (mock)."""
        logger.debug(f"Mock Prometheus instant query: {query}")
        return self._match_query(query)

    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s",
    ) -> List[PrometheusQueryResult]:
        """Execute range query (mock)."""
        logger.debug(f"Mock Prometheus range query: {query}")
        return self._match_query(query)

    def get_metric_metadata(
        self,
        metric_name: str,
    ) -> Dict[str, Any]:
        """Get metric metadata (mock)."""
        metadata = {
            "kube_pod_container_status_restarts_total": {
                "type": "counter",
                "help": "Number of container restarts",
            },
            "kube_pod_container_status_waiting_reason": {
                "type": "gauge",
                "help": "Reason the container is in waiting state",
            },
            "kube_node_status_condition": {
                "type": "gauge",
                "help": "The condition of a cluster node",
            },
            "container_cpu_usage_seconds_total": {
                "type": "counter",
                "help": "Cumulative cpu time consumed",
            },
            "container_memory_working_set_bytes": {
                "type": "gauge",
                "help": "Current working set memory usage",
            },
        }
        return metadata.get(metric_name, {"type": "unknown", "help": "Unknown metric"})


class PrometheusClient:
    """Prometheus client with automatic provider selection."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        provider: Optional[PrometheusProvider] = None,
    ):
        """
        Initialize Prometheus client.

        Args:
            base_url: Prometheus/VictoriaMetrics base URL
            auth_token: Optional authentication token
            provider: Force specific provider (auto-detect if None)
        """
        self.base_url = base_url or os.environ.get(
            "PROMETHEUS_URL", "http://localhost:9090"
        )
        self.auth_token = auth_token or os.environ.get("PROMETHEUS_AUTH_TOKEN")

        # Auto-detect provider
        if provider is None:
            if os.environ.get("PROMETHEUS_MOCK", "").lower() == "true":
                provider = PrometheusProvider.MOCK
            elif os.environ.get("AWS_MOCK", "").lower() == "true":
                # If AWS is mocked, also mock Prometheus
                provider = PrometheusProvider.MOCK
            else:
                provider = PrometheusProvider.REAL

        self.provider_type = provider

        if provider == PrometheusProvider.MOCK:
            self._provider = MockPrometheusProvider()
            logger.info("Using Mock Prometheus Provider")
        else:
            self._provider = RealPrometheusProvider(
                base_url=self.base_url,
                auth_token=self.auth_token,
            )
            logger.info(f"Using Real Prometheus Provider: {self.base_url}")

    @property
    def provider(self) -> BasePrometheusProvider:
        """Get the underlying provider."""
        return self._provider

    def query(
        self,
        query: str,
        time: Optional[datetime] = None,
    ) -> List[PrometheusQueryResult]:
        """Execute instant query."""
        return self._provider.query(query, time)

    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s",
    ) -> List[PrometheusQueryResult]:
        """Execute range query."""
        return self._provider.query_range(query, start, end, step)

    def get_metric_metadata(
        self,
        metric_name: str,
    ) -> Dict[str, Any]:
        """Get metric metadata."""
        return self._provider.get_metric_metadata(metric_name)

    # Convenience methods for common K8s queries

    def get_pod_restarts(
        self,
        namespace: Optional[str] = None,
        time_range_minutes: int = 5,
    ) -> List[PrometheusQueryResult]:
        """Get pod restart counts."""
        query = "kube_pod_container_status_restarts_total"
        if namespace:
            query = f'{query}{{namespace="{namespace}"}}'

        end = datetime.now()
        start = end - timedelta(minutes=time_range_minutes)
        return self.query_range(query, start, end)

    def get_crash_loop_pods(
        self,
        namespace: Optional[str] = None,
    ) -> List[PrometheusQueryResult]:
        """Get pods in CrashLoopBackOff state."""
        query = 'kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"}'
        if namespace:
            query = f'kube_pod_container_status_waiting_reason{{namespace="{namespace}", reason="CrashLoopBackOff"}}'

        return self.query(query)

    def get_oom_killed_pods(
        self,
        namespace: Optional[str] = None,
    ) -> List[PrometheusQueryResult]:
        """Get pods terminated due to OOMKilled."""
        query = 'kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}'
        if namespace:
            query = f'kube_pod_container_status_last_terminated_reason{{namespace="{namespace}", reason="OOMKilled"}}'

        return self.query(query)

    def get_node_conditions(
        self,
        condition: Optional[str] = None,
    ) -> List[PrometheusQueryResult]:
        """Get node conditions."""
        if condition:
            query = f'kube_node_status_condition{{condition="{condition}", status="true"}}'
        else:
            query = 'kube_node_status_condition{status="true"}'

        return self.query(query)

    def get_high_cpu_pods(
        self,
        namespace: Optional[str] = None,
        threshold: float = 0.9,
        time_range_minutes: int = 5,
    ) -> List[PrometheusQueryResult]:
        """Get pods with high CPU usage."""
        namespace_filter = f'namespace="{namespace}"' if namespace else ""

        query = f'''
            sum(rate(container_cpu_usage_seconds_total{{{namespace_filter}, container!="POD"}}[5m])) by (namespace, pod)
            /
            sum(kube_pod_container_resource_limits{{{namespace_filter}, resource="cpu"}}) by (namespace, pod)
            > {threshold}
        '''.strip()

        return self.query(query)

    def get_high_memory_pods(
        self,
        namespace: Optional[str] = None,
        threshold: float = 0.85,
    ) -> List[PrometheusQueryResult]:
        """Get pods with high memory usage."""
        namespace_filter = f'namespace="{namespace}"' if namespace else ""

        query = f'''
            sum(container_memory_working_set_bytes{{{namespace_filter}, container!="POD"}}) by (namespace, pod)
            /
            sum(kube_pod_container_resource_limits{{{namespace_filter}, resource="memory"}}) by (namespace, pod)
            > {threshold}
        '''.strip()

        return self.query(query)


# Module-level convenience function
def get_prometheus_client(
    base_url: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> PrometheusClient:
    """Get Prometheus client instance."""
    return PrometheusClient(base_url=base_url, auth_token=auth_token)


if __name__ == "__main__":
    # Test mock provider
    import os
    os.environ["PROMETHEUS_MOCK"] = "true"

    client = PrometheusClient()
    print(f"Provider type: {client.provider_type}")

    # Test queries
    print("\n=== CrashLoopBackOff Pods ===")
    results = client.get_crash_loop_pods()
    for r in results:
        print(f"  {r.labels.get('namespace')}/{r.labels.get('pod')}: {r.latest_value}")

    print("\n=== OOMKilled Pods ===")
    results = client.get_oom_killed_pods()
    for r in results:
        print(f"  {r.labels.get('namespace')}/{r.labels.get('pod')}: {r.latest_value}")

    print("\n=== Node Conditions ===")
    results = client.get_node_conditions()
    for r in results:
        print(f"  {r.labels.get('node')} - {r.labels.get('condition')}: {r.latest_value}")

    print("\n=== Pod Restarts ===")
    results = client.get_pod_restarts()
    for r in results:
        print(f"  {r.labels.get('namespace')}/{r.labels.get('pod')}: {r.latest_value}")
