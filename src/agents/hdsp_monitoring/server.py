"""
HDSP Monitoring FastAPI Server.

Optional standalone server for development and testing.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from src.agents.hdsp_monitoring.handler import HDSPMonitoringHandler

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Request/Response models
if FASTAPI_AVAILABLE:
    class MonitorRequest(BaseModel):
        """Monitor request body."""
        publish_notifications: bool = True
        min_severity: str = "medium"
        group_alerts: bool = True

    class InjectAlertRequest(BaseModel):
        """Inject alert request for testing."""
        alert_name: str
        namespace: str = "default"
        pod: Optional[str] = None
        node: Optional[str] = None
        severity: str = "warning"
        summary: str = "Test alert"


# Global handler instance
_handler: Optional[HDSPMonitoringHandler] = None


def get_handler() -> HDSPMonitoringHandler:
    """Get or create handler instance."""
    global _handler
    if _handler is None:
        _handler = HDSPMonitoringHandler()
    return _handler


if FASTAPI_AVAILABLE:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan handler."""
        logger.info("HDSP Monitoring Server starting...")
        get_handler()  # Initialize handler
        yield
        logger.info("HDSP Monitoring Server shutting down...")

    app = FastAPI(
        title="HDSP Monitoring API",
        description=(
            "Prometheus Alertmanager-based K8s monitoring system.\n\n"
            "Features:\n"
            "- 3-tier severity classification (CRITICAL, HIGH, MEDIUM)\n"
            "- KakaoTalk notifications for CRITICAL/HIGH alerts\n"
            "- EventBridge integration for all alerts\n"
            "- Alert deduplication and grouping"
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "service": "hdsp-monitoring",
            "version": "0.1.0",
            "endpoints": {
                "monitor": "POST /monitor",
                "health": "GET /health",
                "stats": "GET /stats",
                "inject": "POST /test/inject (mock mode only)",
            },
        }

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        handler = get_handler()
        return {
            "status": "healthy",
            "service": "hdsp-monitoring",
            "cluster": handler.alert_processor.cluster_name,
            "mock_mode": handler.alert_fetcher.is_mock,
        }

    @app.get("/stats")
    async def stats():
        """Get processing statistics."""
        handler = get_handler()
        return {
            "processor_stats": handler.alert_processor.get_stats(),
            "fetcher_is_mock": handler.alert_fetcher.is_mock,
        }

    @app.post("/monitor")
    async def monitor(request: MonitorRequest):
        """Run monitoring check.

        Fetches alerts from Alertmanager, processes them, and sends
        notifications based on severity.

        Returns:
            Monitoring results including alerts and notification status.
        """
        handler = get_handler()

        event = {
            "body": request.model_dump(),
        }

        result = handler.handle(event, None)
        return JSONResponse(content=result)

    @app.post("/test/inject")
    async def inject_alert(request: InjectAlertRequest):
        """Inject test alert (mock mode only).

        Use this endpoint to inject custom alerts for testing.
        Only available when PROMETHEUS_MOCK=true.
        """
        handler = get_handler()

        if not handler.alert_fetcher.is_mock:
            raise HTTPException(
                status_code=400,
                detail="Alert injection only available in mock mode",
            )

        from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
            AlertStatus,
            PrometheusAlert,
        )
        from datetime import datetime

        alert = PrometheusAlert(
            alert_name=request.alert_name,
            status=AlertStatus.FIRING,
            labels={
                "alertname": request.alert_name,
                "namespace": request.namespace,
                "pod": request.pod or "",
                "node": request.node or "",
                "severity": request.severity,
            },
            annotations={
                "summary": request.summary,
            },
            starts_at=datetime.utcnow(),
            fingerprint="",
        )

        handler.alert_fetcher.provider.inject_alert(alert)

        return {
            "success": True,
            "message": f"Injected alert: {request.alert_name}",
        }

    @app.post("/test/reset")
    async def reset_mock():
        """Reset mock alerts to defaults (mock mode only)."""
        handler = get_handler()

        if not handler.alert_fetcher.is_mock:
            raise HTTPException(
                status_code=400,
                detail="Reset only available in mock mode",
            )

        handler.alert_fetcher.provider.reset_to_defaults()
        return {"success": True, "message": "Mock alerts reset to defaults"}

    @app.post("/test/clear")
    async def clear_mock():
        """Clear all mock alerts (mock mode only)."""
        handler = get_handler()

        if not handler.alert_fetcher.is_mock:
            raise HTTPException(
                status_code=400,
                detail="Clear only available in mock mode",
            )

        handler.alert_fetcher.provider.clear_alerts()
        return {"success": True, "message": "Mock alerts cleared"}


def run_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    reload: bool = False,
):
    """Run the FastAPI server."""
    if not FASTAPI_AVAILABLE:
        print("FastAPI not installed. Install with: pip install fastapi uvicorn")
        return

    import uvicorn
    uvicorn.run(
        "src.agents.hdsp_monitoring.server:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HDSP Monitoring Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()
    run_server(host=args.host, port=args.port, reload=args.reload)
