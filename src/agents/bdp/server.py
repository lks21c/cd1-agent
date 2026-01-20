"""
BDP Agent HTTP Server.

FastAPI server for BDP Detection Agent - detects log, metric, and pattern
anomalies using CloudWatch and RDS-based detection patterns.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, FastAPI

from src.agents.bdp.handler import DetectionHandler
from src.common.server.adapter import create_handler_endpoint
from src.common.server.base_app import create_app
from src.common.server.config import get_settings
from src.common.server.schemas.detection import (
    AgentStatusResponse,
    BDPDetectionRequest,
    BDPDetectionResponse,
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
    """Application lifespan manager for BDP agent."""
    settings = get_settings()
    logger.info("Starting BDP Detection Agent server...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"AWS Provider: {settings.aws_provider}")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"RDS Host: {settings.rds_host or 'not configured'}")

    _agent_state["start_time"] = datetime.utcnow()

    yield

    logger.info("Shutting down BDP Detection Agent server...")


def create_detection_router() -> APIRouter:
    """Create BDP detection router."""
    router = APIRouter()

    # Create handler endpoint from Lambda handler
    _detect_endpoint = create_handler_endpoint(DetectionHandler)

    @router.post(
        "/detect",
        response_model=BDPDetectionResponse,
        summary="Run BDP Anomaly Detection",
        description="""
        Execute anomaly detection on logs, metrics, and patterns.

        Detection Types:
        - **log_anomaly**: Detect error patterns in CloudWatch Logs with LLM summarization
        - **metric_anomaly**: Detect statistical anomalies in CloudWatch metrics
        - **pattern_anomaly**: Execute RDS-based detection patterns
        - **scheduled**: Run all detection types (for scheduled invocation)
        """,
    )
    async def detect(request: BDPDetectionRequest) -> Dict[str, Any]:
        """Run BDP anomaly detection."""
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
        description="Get current status and statistics of the BDP agent.",
    )
    async def status() -> Dict[str, Any]:
        """Get BDP agent status."""
        settings = get_settings()
        uptime = 0.0
        if _agent_state["start_time"]:
            uptime = (datetime.utcnow() - _agent_state["start_time"]).total_seconds()

        return {
            "agent": "bdp",
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
                "rds_configured": settings.rds_host is not None,
                "dynamodb_table": settings.dynamodb_table,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    return router


def create_bdp_app() -> FastAPI:
    """Create BDP agent FastAPI application."""
    app = create_app(
        agent_name="bdp",
        title="CD1 BDP Detection Agent",
        description="Log, metric, and pattern anomaly detection service",
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

    hitl_router = create_hitl_router(agent_type=HITLAgentType.BDP)
    app.include_router(
        hitl_router,
        prefix="/api/v1",
        tags=["hitl"],
    )

    return app


# Application instance
app = create_bdp_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.agents.bdp.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
    )
