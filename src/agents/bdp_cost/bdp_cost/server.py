"""
BDP Compact Agent HTTP Server.

FastAPI server for BDP Compact Agent - Multi-Account Cost Drift Detection
(port 8005).

Standalone version - no dependency on src.common
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from bdp_cost.handler import BDPCostHandler
from bdp_cost.services.multi_account_provider import create_provider

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


class HealthResponse(BaseModel):
    """헬스체크 응답."""

    status: str
    timestamp: str


# ============================================================================
# Application Setup
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for BDP Compact agent."""
    env = os.getenv("ENVIRONMENT", "development")
    logger.info("BDP Compact Agent 서버 시작...")
    logger.info(f"Environment: {env}")

    _agent_state["start_time"] = datetime.utcnow()

    yield

    logger.info("BDP Compact Agent 서버 종료...")


def create_bdp_cost_app() -> FastAPI:
    """BDP Compact agent FastAPI application 생성."""
    app = FastAPI(
        title="CD1 BDP Compact Agent",
        description="Multi-Account 비용 드리프트 탐지 서비스 (PyOD ECOD 기반)",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Handler instance
    bdp_handler = BDPCostHandler()

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """헬스체크 엔드포인트."""
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        }

    @app.post("/api/v1/detect", response_model=BDPDetectionResponse)
    async def detect(request: BDPDetectionRequest):
        """비용 드리프트 탐지 실행."""
        try:
            result = bdp_handler.handle(request.model_dump())
            _agent_state["last_detection"] = datetime.utcnow().isoformat()
            _agent_state["detection_count"] += 1

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

    @app.get("/api/v1/status", response_model=AgentStatusResponse)
    async def status():
        """에이전트 상태 조회."""
        env = os.getenv("ENVIRONMENT", "development")
        uptime = 0.0
        if _agent_state["start_time"]:
            uptime = (datetime.utcnow() - _agent_state["start_time"]).total_seconds()

        return {
            "agent": "bdp-cost",
            "status": "healthy",
            "environment": env,
            "version": "0.1.0",
            "uptime_seconds": uptime,
            "last_detection": _agent_state["last_detection"],
            "detection_count": _agent_state["detection_count"],
            "error_count": _agent_state["error_count"],
            "total_anomalies_found": _agent_state["total_anomalies_found"],
            "config": {
                "bdp_provider": os.getenv("BDP_PROVIDER", "mock"),
                "bdp_sensitivity": float(os.getenv("BDP_SENSITIVITY", "0.7")),
                "bdp_currency": os.getenv("BDP_CURRENCY", "KRW"),
                "event_bus": os.getenv("EVENT_BUS", "cd1-agent-events"),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    @app.get("/api/v1/accounts")
    async def get_accounts():
        """설정된 계정 목록 조회."""
        provider = create_provider()
        accounts = provider.get_accounts()

        return {
            "accounts": [
                {
                    "account_id": acc.account_id,
                    "account_name": acc.account_name,
                    "has_role_arn": acc.role_arn is not None,
                    "region": acc.region,
                }
                for acc in accounts
            ],
            "total": len(accounts),
        }

    return app


# Application instance
app = create_bdp_cost_app()


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8005"))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    uvicorn.run(
        "bdp_cost.server:app",
        host=host,
        port=port,  # BDP Compact는 port 8005 사용
        reload=debug,
    )
