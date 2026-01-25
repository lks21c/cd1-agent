"""
BDP Drift Agent - FastAPI Server.

데이터레이크 어플리케이션 레이어의 설정 drift 탐지 API.

Endpoints:
- POST /api/v1/detect - 드리프트 탐지 실행
- GET /api/v1/baselines - 베이스라인 목록 조회
- POST /api/v1/baselines - 베이스라인 생성
- GET /api/v1/baselines/{type}/{id} - 베이스라인 조회
- PUT /api/v1/baselines/{type}/{id} - 베이스라인 업데이트
- DELETE /api/v1/baselines/{type}/{id} - 베이스라인 삭제
- GET /api/v1/baselines/{type}/{id}/history - 버전 이력 조회
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.agents.bdp_drift.handler import BDPDriftHandler
from src.agents.bdp_drift.bdp_drift.services.models import ResourceType

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# FastAPI 앱
app = FastAPI(
    title="BDP Drift Agent API",
    description="데이터레이크 설정 드리프트 탐지 에이전트",
    version="1.0.0",
)

# 전역 핸들러
_handler: Optional[BDPDriftHandler] = None


def get_handler() -> BDPDriftHandler:
    """핸들러 싱글톤."""
    global _handler
    if _handler is None:
        _handler = BDPDriftHandler()
    return _handler


# =============================================================================
# Request/Response Models
# =============================================================================


class DetectionRequest(BaseModel):
    """드리프트 탐지 요청."""

    resource_types: Optional[List[str]] = Field(
        default=None,
        description="대상 리소스 타입 목록 (glue, athena, emr, sagemaker, s3, mwaa, msk, lambda)",
    )
    resource_ids: Optional[List[str]] = Field(
        default=None,
        description="특정 리소스 ID 목록 (format: type/id)",
    )
    publish_alerts: bool = Field(
        default=True,
        description="EventBridge 이벤트 발행 여부",
    )
    send_kakao: bool = Field(
        default=False,
        description="카카오톡 알림 발송 여부",
    )


class BaselineCreateRequest(BaseModel):
    """베이스라인 생성 요청."""

    resource_type: str = Field(
        description="리소스 타입",
    )
    resource_id: str = Field(
        description="리소스 ID",
    )
    config: Dict[str, Any] = Field(
        description="베이스라인 설정",
    )
    resource_arn: Optional[str] = Field(
        default=None,
        description="리소스 ARN",
    )
    description: Optional[str] = Field(
        default=None,
        description="설명",
    )
    tags: Optional[Dict[str, str]] = Field(
        default=None,
        description="태그",
    )
    created_by: str = Field(
        default="api",
        description="생성자",
    )


class BaselineUpdateRequest(BaseModel):
    """베이스라인 업데이트 요청."""

    config: Dict[str, Any] = Field(
        description="새 베이스라인 설정",
    )
    updated_by: str = Field(
        default="api",
        description="수정자",
    )
    reason: Optional[str] = Field(
        default=None,
        description="변경 사유",
    )


class BaselineFromCurrentRequest(BaseModel):
    """현재 설정에서 베이스라인 생성 요청."""

    created_by: str = Field(
        default="api",
        description="생성자",
    )
    description: Optional[str] = Field(
        default=None,
        description="설명",
    )


# =============================================================================
# API Endpoints
# =============================================================================


@app.get("/api/v1/status")
async def get_status():
    """에이전트 상태 조회."""
    handler = get_handler()
    return {
        "status": "healthy",
        "agent": "bdp-drift",
        "version": "1.0.0",
        "provider": handler.provider,
        "baseline_provider": handler.baseline_provider,
        "supported_resources": [rt.value for rt in ResourceType],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/v1/detect")
async def detect_drift(request: DetectionRequest):
    """드리프트 탐지 실행."""
    handler = get_handler()
    result = handler.process(request.model_dump())
    return result


# =============================================================================
# Baseline CRUD Endpoints
# =============================================================================


@app.get("/api/v1/baselines")
async def list_baselines(
    resource_type: Optional[str] = None,
):
    """베이스라인 목록 조회."""
    handler = get_handler()
    baselines = handler.baseline_store.list_baselines(resource_type)

    return {
        "baselines": [
            {
                "resource_type": b.resource_type,
                "resource_id": b.resource_id,
                "version": b.version,
                "config_hash": b.config_hash,
                "description": b.description,
                "updated_at": b.updated_at.isoformat() if b.updated_at else None,
                "updated_by": b.updated_by,
            }
            for b in baselines
        ],
        "total": len(baselines),
    }


@app.post("/api/v1/baselines")
async def create_baseline(request: BaselineCreateRequest):
    """베이스라인 생성."""
    handler = get_handler()

    # 중복 확인
    existing = handler.baseline_store.get_baseline(
        request.resource_type, request.resource_id
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Baseline already exists: {request.resource_type}/{request.resource_id}",
        )

    baseline = handler.baseline_store.create_baseline(
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        config=request.config,
        created_by=request.created_by,
        resource_arn=request.resource_arn,
        description=request.description,
        tags=request.tags,
    )

    return {
        "status": "created",
        "baseline": {
            "resource_type": baseline.resource_type,
            "resource_id": baseline.resource_id,
            "version": baseline.version,
            "config_hash": baseline.config_hash,
        },
    }


@app.post("/api/v1/baselines/from-current/{resource_type}/{resource_id:path}")
async def create_baseline_from_current(
    resource_type: str,
    resource_id: str,
    request: BaselineFromCurrentRequest,
):
    """현재 설정에서 베이스라인 생성."""
    handler = get_handler()

    # 중복 확인
    existing = handler.baseline_store.get_baseline(resource_type, resource_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Baseline already exists: {resource_type}/{resource_id}",
        )

    baseline = handler.detector.create_baseline_from_current(
        resource_type=resource_type,
        resource_id=resource_id,
        created_by=request.created_by,
        description=request.description,
    )

    if baseline is None:
        raise HTTPException(
            status_code=404,
            detail=f"Resource not found: {resource_type}/{resource_id}",
        )

    return {
        "status": "created",
        "baseline": {
            "resource_type": baseline.resource_type,
            "resource_id": baseline.resource_id,
            "version": baseline.version,
            "config_hash": baseline.config_hash,
            "config": baseline.config,
        },
    }


@app.get("/api/v1/baselines/{resource_type}/{resource_id:path}")
async def get_baseline(resource_type: str, resource_id: str):
    """베이스라인 조회."""
    handler = get_handler()
    baseline = handler.baseline_store.get_baseline(resource_type, resource_id)

    if baseline is None:
        raise HTTPException(
            status_code=404,
            detail=f"Baseline not found: {resource_type}/{resource_id}",
        )

    return {
        "baseline": {
            "resource_type": baseline.resource_type,
            "resource_id": baseline.resource_id,
            "version": baseline.version,
            "config": baseline.config,
            "config_hash": baseline.config_hash,
            "resource_arn": baseline.resource_arn,
            "description": baseline.description,
            "tags": baseline.tags,
            "created_at": baseline.created_at.isoformat() if baseline.created_at else None,
            "updated_at": baseline.updated_at.isoformat() if baseline.updated_at else None,
            "created_by": baseline.created_by,
            "updated_by": baseline.updated_by,
        },
    }


@app.put("/api/v1/baselines/{resource_type}/{resource_id:path}")
async def update_baseline(
    resource_type: str,
    resource_id: str,
    request: BaselineUpdateRequest,
):
    """베이스라인 업데이트."""
    handler = get_handler()

    baseline = handler.baseline_store.update_baseline(
        resource_type=resource_type,
        resource_id=resource_id,
        config=request.config,
        updated_by=request.updated_by,
        reason=request.reason,
    )

    if baseline is None:
        raise HTTPException(
            status_code=404,
            detail=f"Baseline not found: {resource_type}/{resource_id}",
        )

    return {
        "status": "updated",
        "baseline": {
            "resource_type": baseline.resource_type,
            "resource_id": baseline.resource_id,
            "version": baseline.version,
            "config_hash": baseline.config_hash,
        },
    }


@app.put("/api/v1/baselines/{resource_type}/{resource_id:path}/from-current")
async def update_baseline_from_current(
    resource_type: str,
    resource_id: str,
    request: BaselineUpdateRequest,
):
    """현재 설정으로 베이스라인 업데이트."""
    handler = get_handler()

    baseline = handler.detector.update_baseline_from_current(
        resource_type=resource_type,
        resource_id=resource_id,
        updated_by=request.updated_by,
        reason=request.reason,
    )

    if baseline is None:
        raise HTTPException(
            status_code=404,
            detail=f"Resource or baseline not found: {resource_type}/{resource_id}",
        )

    return {
        "status": "updated",
        "baseline": {
            "resource_type": baseline.resource_type,
            "resource_id": baseline.resource_id,
            "version": baseline.version,
            "config_hash": baseline.config_hash,
        },
    }


@app.delete("/api/v1/baselines/{resource_type}/{resource_id:path}")
async def delete_baseline(resource_type: str, resource_id: str):
    """베이스라인 삭제."""
    handler = get_handler()

    deleted = handler.baseline_store.delete_baseline(resource_type, resource_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Baseline not found: {resource_type}/{resource_id}",
        )

    return {
        "status": "deleted",
        "resource_type": resource_type,
        "resource_id": resource_id,
    }


# =============================================================================
# History & Version Endpoints
# =============================================================================


@app.get("/api/v1/baselines/{resource_type}/{resource_id:path}/history")
async def get_baseline_history(resource_type: str, resource_id: str):
    """베이스라인 버전 이력 조회."""
    handler = get_handler()
    history = handler.baseline_store.get_version_history(resource_type, resource_id)

    return {
        "history": [
            {
                "id": h.id,
                "version": h.version,
                "change_type": h.change_type,
                "config_hash": h.config_hash,
                "change_reason": h.change_reason,
                "changed_at": h.changed_at.isoformat() if h.changed_at else None,
                "changed_by": h.changed_by,
            }
            for h in history
        ],
        "total": len(history),
    }


@app.get("/api/v1/baselines/{resource_type}/{resource_id:path}/versions/{version}")
async def get_baseline_at_version(
    resource_type: str,
    resource_id: str,
    version: int,
):
    """특정 버전의 베이스라인 조회."""
    handler = get_handler()
    baseline = handler.baseline_store.get_baseline_at_version(
        resource_type, resource_id, version
    )

    if baseline is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version not found: {resource_type}/{resource_id} v{version}",
        )

    return {
        "baseline": {
            "resource_type": baseline.resource_type,
            "resource_id": baseline.resource_id,
            "version": baseline.version,
            "config": baseline.config,
            "config_hash": baseline.config_hash,
        },
    }


@app.post("/api/v1/baselines/{resource_type}/{resource_id:path}/rollback/{version}")
async def rollback_baseline(
    resource_type: str,
    resource_id: str,
    version: int,
    rolled_back_by: str = "api",
):
    """특정 버전으로 롤백."""
    handler = get_handler()

    baseline = handler.baseline_store.rollback_to_version(
        resource_type, resource_id, version, rolled_back_by
    )

    if baseline is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version not found: {resource_type}/{resource_id} v{version}",
        )

    return {
        "status": "rolled_back",
        "baseline": {
            "resource_type": baseline.resource_type,
            "resource_id": baseline.resource_id,
            "version": baseline.version,
            "config_hash": baseline.config_hash,
        },
        "rolled_back_from_version": version,
    }


@app.get("/api/v1/baselines/{resource_type}/{resource_id:path}/compare")
async def compare_versions(
    resource_type: str,
    resource_id: str,
    version_a: int,
    version_b: int,
):
    """두 버전 비교."""
    handler = get_handler()

    diff = handler.baseline_store.compare_versions(
        resource_type, resource_id, version_a, version_b
    )

    if "error" in diff:
        raise HTTPException(status_code=404, detail=diff["error"])

    return diff


# =============================================================================
# Resource Discovery Endpoints
# =============================================================================


@app.get("/api/v1/resources")
async def list_resources(resource_type: Optional[str] = None):
    """현재 AWS 리소스 목록 조회."""
    handler = get_handler()

    if resource_type:
        resources = handler.config_fetcher.list_resources(resource_type)
        return {
            "resource_type": resource_type,
            "resources": resources,
            "total": len(resources),
        }
    else:
        all_resources = {}
        for rt in handler.config_fetcher.supported_resource_types:
            resources = handler.config_fetcher.list_resources(rt)
            all_resources[rt] = resources

        return {
            "resources": all_resources,
            "total": sum(len(r) for r in all_resources.values()),
        }


@app.get("/api/v1/resources/{resource_type}/{resource_id:path}")
async def get_resource_config(resource_type: str, resource_id: str):
    """현재 AWS 리소스 설정 조회."""
    handler = get_handler()

    config = handler.config_fetcher.fetch_config(resource_type, resource_id)

    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"Resource not found: {resource_type}/{resource_id}",
        )

    return {
        "resource": {
            "resource_type": config.resource_type,
            "resource_id": config.resource_id,
            "resource_arn": config.resource_arn,
            "config": config.config,
        },
    }


# =============================================================================
# Main
# =============================================================================


def main():
    """서버 실행."""
    import uvicorn

    port = int(os.getenv("PORT", "8006"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting BDP Drift Agent server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
