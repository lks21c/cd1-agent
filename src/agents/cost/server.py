"""
Cost Agent HTTP Server.

FastAPI server for Cost Detection Agent - detects AWS cost anomalies
using Cost Explorer and ensemble anomaly detection methods.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, FastAPI

from src.agents.cost.handler import CostDetectionHandler
from src.common.server.adapter import create_handler_endpoint
from src.common.server.base_app import create_app
from src.common.server.config import get_settings
from src.common.server.schemas.detection import (
    AgentStatusResponse,
    CostDetectionRequest,
    CostDetectionResponse,
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
    """Application lifespan manager for Cost agent."""
    settings = get_settings()
    logger.info("Starting Cost Detection Agent server...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"AWS Provider: {settings.aws_provider}")
    logger.info(f"Cost Provider: {settings.cost_provider}")

    _agent_state["start_time"] = datetime.utcnow()

    yield

    logger.info("Shutting down Cost Detection Agent server...")


def create_detection_router() -> APIRouter:
    """Create Cost detection router."""
    router = APIRouter()

    # Create handler endpoint from Lambda handler
    _detect_endpoint = create_handler_endpoint(CostDetectionHandler)

    @router.post(
        "/detect",
        response_model=CostDetectionResponse,
        summary="Run Cost Anomaly Detection",
        description="""
        Execute cost anomaly detection on AWS Cost Explorer data.

        Detection Types:
        - **all**: Full detection using Ratio, StdDev, Trend, and Luminol methods
        - **forecast**: Cost forecast for upcoming days
        - **aws_anomalies**: Fetch anomalies from AWS Cost Anomaly Detection service
        """,
    )
    async def detect(request: CostDetectionRequest) -> Dict[str, Any]:
        """Run cost anomaly detection."""
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
        description="Get current status and statistics of the Cost agent.",
    )
    async def status() -> Dict[str, Any]:
        """Get Cost agent status."""
        settings = get_settings()
        uptime = 0.0
        if _agent_state["start_time"]:
            uptime = (datetime.utcnow() - _agent_state["start_time"]).total_seconds()

        return {
            "agent": "cost",
            "status": "healthy",
            "environment": settings.environment,
            "version": "1.0.0",
            "uptime_seconds": uptime,
            "last_detection": _agent_state["last_detection"],
            "detection_count": _agent_state["detection_count"],
            "error_count": _agent_state["error_count"],
            "config": {
                "aws_provider": settings.aws_provider,
                "cost_provider": settings.cost_provider,
                "cost_sensitivity": settings.cost_sensitivity,
                "dynamodb_table": settings.dynamodb_table,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    return router


def create_cost_app() -> FastAPI:
    """Create Cost agent FastAPI application."""
    app = create_app(
        agent_name="cost",
        title="CD1 Cost Detection Agent",
        description="AWS Cost anomaly detection service using ensemble methods",
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

    hitl_router = create_hitl_router(agent_type=HITLAgentType.COST)
    app.include_router(
        hitl_router,
        prefix="/api/v1",
        tags=["hitl"],
    )

    return app


# Application instance
app = create_cost_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.agents.cost.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
    )
