"""
HITL Router for FastAPI.

Provides API endpoints for HITL request management.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from src.common.hitl.schemas import (
    HITLAgentType,
    HITLRequest,
    HITLRequestCreate,
    HITLRequestFilter,
    HITLRequestList,
    HITLRequestResponse,
    HITLRequestStatus,
)
from src.common.hitl.store import HITLStore
from src.common.server.config import get_settings

logger = logging.getLogger(__name__)


def create_hitl_router(
    agent_type: Optional[HITLAgentType] = None,
    store: Optional[HITLStore] = None,
) -> APIRouter:
    """
    Create HITL router for an agent server.

    Args:
        agent_type: Agent type for filtering (optional, filters by agent if set)
        store: HITLStore instance (creates new one if not provided)

    Returns:
        Configured APIRouter with HITL endpoints
    """
    router = APIRouter(prefix="/hitl", tags=["hitl"])

    # Initialize store if not provided
    settings = get_settings()
    _store = store or HITLStore(
        rds_host=settings.rds_host,
        rds_port=settings.rds_port,
        rds_database=settings.rds_database,
        rds_user=settings.rds_user,
        rds_password=settings.rds_password,
        use_mock=settings.aws_provider == "mock" or settings.rds_host is None,
    )

    @router.post(
        "/requests",
        response_model=HITLRequest,
        status_code=status.HTTP_201_CREATED,
        summary="Create HITL Request",
        description="Create a new Human-in-the-Loop approval request.",
    )
    async def create_request(request: HITLRequestCreate) -> HITLRequest:
        """Create a new HITL request."""
        try:
            # If router is scoped to an agent, enforce agent type
            if agent_type and request.agent_type != agent_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Agent type must be {agent_type.value} for this server",
                )

            return _store.create(request)
        except Exception as e:
            logger.error(f"Failed to create HITL request: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )

    @router.get(
        "/requests",
        response_model=HITLRequestList,
        summary="List HITL Requests",
        description="List HITL requests with optional filtering.",
    )
    async def list_requests(
        agent_type_filter: Optional[HITLAgentType] = Query(
            default=None,
            alias="agent_type",
            description="Filter by agent type",
        ),
        status_filter: Optional[HITLRequestStatus] = Query(
            default=None,
            alias="status",
            description="Filter by status",
        ),
        limit: int = Query(default=50, ge=1, le=100, description="Maximum results"),
        offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    ) -> HITLRequestList:
        """List HITL requests with filtering."""
        try:
            # Apply agent scope if router is scoped
            filter_agent = agent_type_filter
            if agent_type:
                filter_agent = agent_type

            filter_obj = HITLRequestFilter(
                agent_type=filter_agent,
                status=status_filter,
                limit=limit,
                offset=offset,
            )

            # Expire stale requests before listing
            _store.expire_stale_requests()

            requests = _store.list_requests(filter_obj)
            pending_count = _store.get_pending_count(filter_agent)

            return HITLRequestList(
                requests=requests,
                total=len(requests),
                pending_count=pending_count,
            )
        except Exception as e:
            logger.error(f"Failed to list HITL requests: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )

    @router.get(
        "/requests/{request_id}",
        response_model=HITLRequest,
        summary="Get HITL Request",
        description="Get a specific HITL request by ID.",
    )
    async def get_request(request_id: str) -> HITLRequest:
        """Get a HITL request by ID."""
        try:
            request = _store.get(request_id)
            if not request:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Request {request_id} not found",
                )

            # Check agent scope
            if agent_type and request.agent_type != agent_type:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Request {request_id} not found",
                )

            return request
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get HITL request: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )

    @router.put(
        "/requests/{request_id}",
        response_model=HITLRequest,
        summary="Respond to HITL Request",
        description="Approve or reject a pending HITL request.",
    )
    async def respond_to_request(
        request_id: str,
        response: HITLRequestResponse,
    ) -> HITLRequest:
        """Respond to (approve/reject) a HITL request."""
        try:
            # Check if request exists
            existing = _store.get(request_id)
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Request {request_id} not found",
                )

            # Check agent scope
            if agent_type and existing.agent_type != agent_type:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Request {request_id} not found",
                )

            # Check if still pending
            if existing.status != HITLRequestStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Request is not pending (status: {existing.status.value})",
                )

            # Check if expired
            if existing.expires_at < datetime.utcnow():
                _store.expire_stale_requests()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Request has expired",
                )

            result = _store.respond(request_id, response)
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to respond to request",
                )

            logger.info(
                f"HITL request {request_id} "
                f"{'approved' if response.approved else 'rejected'} "
                f"by {response.responded_by or 'unknown'}"
            )

            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to respond to HITL request: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )

    @router.delete(
        "/requests/{request_id}",
        response_model=HITLRequest,
        summary="Cancel HITL Request",
        description="Cancel a pending HITL request.",
    )
    async def cancel_request(request_id: str) -> HITLRequest:
        """Cancel a pending HITL request."""
        try:
            # Check if request exists
            existing = _store.get(request_id)
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Request {request_id} not found",
                )

            # Check agent scope
            if agent_type and existing.agent_type != agent_type:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Request {request_id} not found",
                )

            result = _store.cancel(request_id)
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot cancel request (status: {existing.status.value})",
                )

            logger.info(f"HITL request {request_id} cancelled")
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel HITL request: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )

    @router.get(
        "/pending-count",
        summary="Get Pending Count",
        description="Get the count of pending HITL requests.",
    )
    async def get_pending_count() -> Dict[str, Any]:
        """Get the count of pending HITL requests."""
        try:
            count = _store.get_pending_count(agent_type)
            return {
                "pending_count": count,
                "agent_type": agent_type.value if agent_type else None,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get pending count: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )

    return router
