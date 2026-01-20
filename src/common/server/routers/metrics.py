"""
Prometheus Metrics Router.

Provides /metrics endpoint for Prometheus scraping.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Response

from src.common.server.config import ServerSettings, get_settings

logger = logging.getLogger(__name__)


def create_metrics_router(settings: Optional[ServerSettings] = None) -> APIRouter:
    """
    Create Prometheus metrics router.

    Args:
        settings: Server settings

    Returns:
        Configured APIRouter with metrics endpoint
    """
    router = APIRouter(tags=["metrics"])
    settings = settings or get_settings()

    # Initialize Prometheus metrics
    try:
        from prometheus_client import (
            CONTENT_TYPE_LATEST,
            REGISTRY,
            Counter,
            Gauge,
            Histogram,
            generate_latest,
        )

        # Common metrics
        prefix = settings.metrics_prefix

        REQUEST_COUNT = Counter(
            f"{prefix}_requests_total",
            "Total number of requests",
            ["method", "endpoint", "status"],
        )

        REQUEST_LATENCY = Histogram(
            f"{prefix}_request_latency_seconds",
            "Request latency in seconds",
            ["method", "endpoint"],
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )

        DETECTION_COUNT = Counter(
            f"{prefix}_detections_total",
            "Total number of detection runs",
            ["agent", "detection_type", "status"],
        )

        ANOMALY_COUNT = Counter(
            f"{prefix}_anomalies_total",
            "Total number of anomalies detected",
            ["agent", "severity"],
        )

        ACTIVE_HITL_REQUESTS = Gauge(
            f"{prefix}_hitl_requests_active",
            "Number of active HITL requests",
            ["agent", "status"],
        )

        @router.get("/metrics")
        async def metrics_endpoint() -> Response:
            """
            Prometheus metrics endpoint.

            Returns metrics in Prometheus exposition format.
            """
            return Response(
                content=generate_latest(REGISTRY),
                media_type=CONTENT_TYPE_LATEST,
            )

        # Store metrics in router state for access from middleware
        router.state = type("RouterState", (), {
            "request_count": REQUEST_COUNT,
            "request_latency": REQUEST_LATENCY,
            "detection_count": DETECTION_COUNT,
            "anomaly_count": ANOMALY_COUNT,
            "active_hitl_requests": ACTIVE_HITL_REQUESTS,
        })()

    except ImportError:
        logger.warning("prometheus_client not installed, metrics disabled")

        @router.get("/metrics")
        async def metrics_disabled() -> Response:
            """Metrics endpoint (disabled)."""
            return Response(
                content="# Metrics disabled - prometheus_client not installed\n",
                media_type="text/plain",
            )

    return router


class MetricsHelper:
    """Helper class for recording metrics from handlers."""

    def __init__(self, settings: Optional[ServerSettings] = None):
        self.settings = settings or get_settings()
        self._enabled = self.settings.metrics_enabled
        self._prefix = self.settings.metrics_prefix

    def record_request(
        self,
        method: str,
        endpoint: str,
        status: int,
        latency: float,
    ) -> None:
        """Record request metrics."""
        if not self._enabled:
            return

        try:
            from prometheus_client import REGISTRY

            # Find counter by name
            REQUEST_COUNT = REGISTRY._names_to_collectors.get(
                f"{self._prefix}_requests_total"
            )
            REQUEST_LATENCY = REGISTRY._names_to_collectors.get(
                f"{self._prefix}_request_latency_seconds"
            )

            if REQUEST_COUNT:
                REQUEST_COUNT.labels(
                    method=method,
                    endpoint=endpoint,
                    status=str(status),
                ).inc()

            if REQUEST_LATENCY:
                REQUEST_LATENCY.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(latency)

        except Exception as e:
            logger.debug(f"Failed to record request metrics: {e}")

    def record_detection(
        self,
        agent: str,
        detection_type: str,
        status: str,
        anomaly_count: int = 0,
        severity_breakdown: Optional[dict] = None,
    ) -> None:
        """Record detection metrics."""
        if not self._enabled:
            return

        try:
            from prometheus_client import REGISTRY

            DETECTION_COUNT = REGISTRY._names_to_collectors.get(
                f"{self._prefix}_detections_total"
            )
            ANOMALY_COUNT = REGISTRY._names_to_collectors.get(
                f"{self._prefix}_anomalies_total"
            )

            if DETECTION_COUNT:
                DETECTION_COUNT.labels(
                    agent=agent,
                    detection_type=detection_type,
                    status=status,
                ).inc()

            if ANOMALY_COUNT and severity_breakdown:
                for severity, count in severity_breakdown.items():
                    if count > 0:
                        ANOMALY_COUNT.labels(
                            agent=agent,
                            severity=severity,
                        ).inc(count)

        except Exception as e:
            logger.debug(f"Failed to record detection metrics: {e}")
