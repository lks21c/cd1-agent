"""
Drift Agent HTTP Server.

FastAPI server for Drift Detection Agent - detects configuration drifts
between local baseline files and current AWS resource configurations.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, FastAPI

from src.agents.drift.handler import DriftDetectionHandler
from src.common.server.adapter import create_handler_endpoint
from src.common.server.base_app import create_app
from src.common.server.config import get_settings
from src.common.server.schemas.detection import (
    AgentStatusResponse,
    DriftDetectionRequest,
    DriftDetectionResponse,
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
    """Application lifespan manager for Drift agent."""
    settings = get_settings()
    logger.info("Starting Drift Detection Agent server...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"AWS Provider: {settings.aws_provider}")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"Drift Analysis Enabled: {settings.enable_drift_analysis}")

    _agent_state["start_time"] = datetime.utcnow()

    yield

    logger.info("Shutting down Drift Detection Agent server...")


def create_detection_router() -> APIRouter:
    """Create Drift detection router."""
    router = APIRouter()

    # Create handler endpoint from Lambda handler
    _detect_endpoint = create_handler_endpoint(DriftDetectionHandler)

    @router.post(
        "/detect",
        response_model=DriftDetectionResponse,
        summary="Run Drift Detection",
        description="""
        Execute configuration drift detection against AWS resources.

        Supported Resource Types:
        - **eks**: EKS cluster and node group configurations
        - **msk**: Kafka cluster configurations
        - **s3**: Bucket security and lifecycle configurations
        - **emr**: EMR cluster and instance group configurations
        - **mwaa**: Airflow environment configurations

        Features:
        - Compares current AWS configuration against local baseline files
        - Severity classification (critical, high, medium, low)
        - Optional LLM-based root cause analysis for high-severity drifts
        """,
    )
    async def detect(request: DriftDetectionRequest) -> Dict[str, Any]:
        """Run drift detection."""
        try:
            # Transform request to match handler expectations
            request_data = {
                "resource_types": [rt.upper() for rt in request.resource_types],
                "severity_threshold": request.severity_threshold.upper(),
            }

            result = await _detect_endpoint(request_data)
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
        description="Get current status and statistics of the Drift agent.",
    )
    async def status() -> Dict[str, Any]:
        """Get Drift agent status."""
        settings = get_settings()
        uptime = 0.0
        if _agent_state["start_time"]:
            uptime = (datetime.utcnow() - _agent_state["start_time"]).total_seconds()

        return {
            "agent": "drift",
            "status": "healthy",
            "environment": settings.environment,
            "version": "1.0.0",
            "uptime_seconds": uptime,
            "last_detection": _agent_state["last_detection"],
            "detection_count": _agent_state["detection_count"],
            "error_count": _agent_state["error_count"],
            "config": {
                "aws_provider": settings.aws_provider,
                "llm_provider": settings.llm_provider,
                "drift_analysis_enabled": settings.enable_drift_analysis,
                "max_drifts_to_analyze": settings.max_drifts_to_analyze,
                "dynamodb_table": settings.dynamodb_table,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    return router


def create_drift_app() -> FastAPI:
    """Create Drift agent FastAPI application."""
    app = create_app(
        agent_name="drift",
        title="CD1 Drift Detection Agent",
        description="AWS configuration drift detection service with LLM analysis",
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

    hitl_router = create_hitl_router(agent_type=HITLAgentType.DRIFT)
    app.include_router(
        hitl_router,
        prefix="/api/v1",
        tags=["hitl"],
    )

    return app


# Application instance
app = create_drift_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.agents.drift.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
    )
