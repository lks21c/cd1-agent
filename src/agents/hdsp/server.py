"""
HDSP Agent HTTP Server.

FastAPI server for HDSP Detection Agent - detects Kubernetes cluster
anomalies using Prometheus metrics.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, FastAPI

from src.agents.hdsp.handler import HDSPDetectionHandler
from src.common.server.adapter import create_handler_endpoint
from src.common.server.base_app import create_app
from src.common.server.config import get_settings
from src.common.server.schemas.detection import (
    AgentStatusResponse,
    HDSPDetectionRequest,
    HDSPDetectionResponse,
)

logger = logging.getLogger(__name__)

# Global state for tracking
_agent_state = {
    "start_time": None,
    "last_detection": None,
    "detection_count": 0,
    "error_count": 0,
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for HDSP agent."""
    settings = get_settings()
    logger.info("Starting HDSP Detection Agent server...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"AWS Provider: {settings.aws_provider}")
    logger.info(f"Prometheus URL: {settings.prometheus_url}")

    _agent_state["start_time"] = datetime.utcnow()

    yield

    logger.info("Shutting down HDSP Detection Agent server...")


def create_detection_router() -> APIRouter:
    """Create HDSP detection router."""
    router = APIRouter()

    # Create handler endpoint from Lambda handler
    _detect_endpoint = create_handler_endpoint(HDSPDetectionHandler)

    @router.post(
        "/detect",
        response_model=HDSPDetectionResponse,
        summary="Run HDSP Anomaly Detection",
        description="""
        Execute Kubernetes cluster anomaly detection using Prometheus metrics.

        Detection Types:
        - **all**: Full detection (pod failures, node pressure, resource anomalies)
        - **pod_failure**: Detect CrashLoopBackOff, OOMKilled, excessive restarts
        - **node_pressure**: Detect MemoryPressure, DiskPressure, NotReady nodes
        - **resource**: Detect high CPU/Memory usage anomalies
        """,
    )
    async def detect(request: HDSPDetectionRequest) -> Dict[str, Any]:
        """Run HDSP anomaly detection."""
        try:
            result = await _detect_endpoint(request.model_dump())
            _agent_state["last_detection"] = datetime.utcnow().isoformat()
            _agent_state["detection_count"] += 1

            # Extract data from response
            if result.get("success") and "data" in result:
                return result["data"]
            elif result.get("success") is False:
                _agent_state["error_count"] += 1
                raise ValueError(result.get("error", "Detection failed"))

            return result
        except Exception as e:
            _agent_state["error_count"] += 1
            raise

    @router.get(
        "/status",
        response_model=AgentStatusResponse,
        summary="Get Agent Status",
        description="Get current status and statistics of the HDSP agent.",
    )
    async def status() -> Dict[str, Any]:
        """Get HDSP agent status."""
        settings = get_settings()
        uptime = 0.0
        if _agent_state["start_time"]:
            uptime = (datetime.utcnow() - _agent_state["start_time"]).total_seconds()

        return {
            "agent": "hdsp",
            "status": "healthy",
            "environment": settings.environment,
            "version": "1.0.0",
            "uptime_seconds": uptime,
            "last_detection": _agent_state["last_detection"],
            "detection_count": _agent_state["detection_count"],
            "error_count": _agent_state["error_count"],
            "config": {
                "aws_provider": settings.aws_provider,
                "prometheus_url": settings.prometheus_url,
                "dynamodb_table": settings.dynamodb_table,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    return router


def create_hdsp_app() -> FastAPI:
    """Create HDSP agent FastAPI application."""
    app = create_app(
        agent_name="hdsp",
        title="CD1 HDSP Detection Agent",
        description="Kubernetes cluster anomaly detection using Prometheus metrics",
        lifespan=lifespan,
    )

    # Include detection router
    detection_router = create_detection_router()
    app.include_router(
        detection_router,
        prefix="/api/v1",
        tags=["detection"],
    )

    # Include HITL router
    from src.common.hitl.router import create_hitl_router
    from src.common.hitl.schemas import HITLAgentType

    hitl_router = create_hitl_router(agent_type=HITLAgentType.HDSP)
    app.include_router(
        hitl_router,
        prefix="/api/v1",
        tags=["hitl"],
    )

    return app


# Application instance
app = create_hdsp_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.agents.hdsp.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
    )
