"""
BDP Compact Agent HTTP Server.

FastAPI server for BDP Compact Agent - Cost Drift Detection
(port 8005).
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.agents.bdp_cost.handler import BDPCostHandler
from src.common.server.adapter import create_handler_endpoint
from src.common.server.base_app import create_app
from src.common.server.config import get_settings

logger = logging.getLogger(__name__)

# Global state for tracking
_agent_state = {
    "start_time": None,
    "last_detection": None,
    "detection_count": 0,
    "error_count": 0,
    "total_anomalies_found": 0,
}


# ============================================================================
# Request/Response Schemas
# ============================================================================


class BDPDetectionRequest(BaseModel):
    """BDP 비용 드리프트 탐지 요청."""

    days: int = Field(default=14, ge=7, le=90, description="분석 기간 (일)")
    min_cost_threshold: float = Field(
        default=10000, ge=0, description="최소 비용 임계값 (원)"
    )
    publish_alerts: bool = Field(default=True, description="EventBridge 알람 발송 여부")


class ServiceAnomalyResult(BaseModel):
    """서비스별 이상 탐지 결과."""

    service_name: str
    account_id: str
    account_name: str
    severity: str
    confidence_score: float
    current_cost: float
    historical_average: float
    change_percent: float
    spike_duration_days: int
    trend_direction: str
    spike_start_date: Optional[str]
    detection_method: str
    summary: str  # 한글 summary


class BDPDetectionResponse(BaseModel):
    """BDP 비용 드리프트 탐지 응답."""

    detection_type: str
    period_days: int
    accounts_analyzed: int
    services_analyzed: int
    anomalies_detected: bool
    total_anomalies: int
    severity_breakdown: Dict[str, int]
    summary: str
    results: List[ServiceAnomalyResult]
    hitl_request_id: Optional[str]
    detection_timestamp: str


class AgentStatusResponse(BaseModel):
    """에이전트 상태 응답."""

    agent: str
    status: str
    environment: str
    version: str
    uptime_seconds: float
    last_detection: Optional[str]
    detection_count: int
    error_count: int
    total_anomalies_found: int
    config: Dict[str, Any]
    timestamp: str


# ============================================================================
# Application Setup
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for BDP Compact agent."""
    settings = get_settings()
    logger.info("BDP Compact Agent 서버 시작...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"AWS Provider: {settings.aws_provider}")

    _agent_state["start_time"] = datetime.utcnow()

    yield

    logger.info("BDP Compact Agent 서버 종료...")


def create_detection_router() -> APIRouter:
    """BDP Compact detection router 생성."""
    router = APIRouter()

    # Handler endpoint 생성
    _detect_endpoint = create_handler_endpoint(BDPCostHandler)

    @router.post(
        "/detect",
        response_model=BDPDetectionResponse,
        summary="비용 드리프트 탐지 실행",
        description="""
        Multi-Account AWS Cost Explorer 데이터를 분석하여 비용 드리프트를 탐지합니다.

        **탐지 방법:**
        - PyOD ECOD 기반 이상 탐지
        - Ratio 기반 fallback 탐지
        - 트렌드 분석 및 스파이크 지속 기간 계산

        **출력:**
        - 한글 Rich Summary
        - 심각도별 분류 (critical, high, medium, low)
        - Critical 이상시 HITL 요청 자동 생성
        """,
    )
    async def detect(request: BDPDetectionRequest) -> Dict[str, Any]:
        """비용 드리프트 탐지 실행."""
        try:
            result = await _detect_endpoint(request.model_dump())
            _agent_state["last_detection"] = datetime.utcnow().isoformat()
            _agent_state["detection_count"] += 1

            # Extract data from response
            if result.get("success") and "data" in result:
                data = result["data"]
                _agent_state["total_anomalies_found"] += data.get("total_anomalies", 0)
                return data
            elif result.get("success") is False:
                _agent_state["error_count"] += 1
                raise HTTPException(
                    status_code=500,
                    detail=result.get("error", "탐지 실패")
                )

            return result

        except HTTPException:
            raise
        except Exception as e:
            _agent_state["error_count"] += 1
            logger.error(f"탐지 오류: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/status",
        response_model=AgentStatusResponse,
        summary="에이전트 상태 조회",
        description="BDP Compact 에이전트의 현재 상태 및 통계를 조회합니다.",
    )
    async def status() -> Dict[str, Any]:
        """에이전트 상태 조회."""
        settings = get_settings()
        uptime = 0.0
        if _agent_state["start_time"]:
            uptime = (datetime.utcnow() - _agent_state["start_time"]).total_seconds()

        return {
            "agent": "bdp-cost",
            "status": "healthy",
            "environment": settings.environment,
            "version": "1.0.0",
            "uptime_seconds": uptime,
            "last_detection": _agent_state["last_detection"],
            "detection_count": _agent_state["detection_count"],
            "error_count": _agent_state["error_count"],
            "total_anomalies_found": _agent_state["total_anomalies_found"],
            "config": {
                "aws_provider": settings.aws_provider,
                "bdp_provider": settings.bdp_provider,
                "bdp_sensitivity": settings.bdp_sensitivity,
                "bdp_currency": settings.bdp_currency,
                "event_bus": settings.event_bus,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    @router.get(
        "/account",
        summary="현재 계정 정보 조회",
        description="현재 Lambda가 실행 중인 AWS 계정 정보를 조회합니다.",
    )
    async def get_account() -> Dict[str, Any]:
        """현재 계정 정보 조회."""
        from src.agents.bdp_cost.services.cost_explorer_provider import create_provider

        provider = create_provider()
        return provider.get_account_info()

    return router


def create_bdp_cost_app() -> FastAPI:
    """BDP Compact agent FastAPI application 생성."""
    app = create_app(
        agent_name="bdp-cost",
        title="CD1 BDP Compact Agent",
        description="비용 드리프트 탐지 서비스 (PyOD ECOD 기반)",
        lifespan=lifespan,
    )

    # Detection router 추가
    detection_router = create_detection_router()
    app.include_router(
        detection_router,
        prefix="/api/v1",
        tags=["detection"],
    )

    # HITL router 추가
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
app = create_bdp_cost_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.agents.bdp_cost.server:app",
        host=settings.host,
        port=8005,  # BDP Compact는 port 8005 사용
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
    )
