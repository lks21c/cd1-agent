"""
HITL Pydantic Schemas.

Data models for Human-in-the-Loop request/response handling.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class HITLRequestStatus(str, Enum):
    """Status of HITL request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class HITLRequestType(str, Enum):
    """Type of HITL request."""

    ACTION_APPROVAL = "action_approval"
    PROMPT_INPUT = "prompt_input"
    CONFIRMATION = "confirmation"


class HITLAgentType(str, Enum):
    """Agent types that can create HITL requests."""

    COST = "cost"
    BDP = "bdp"
    HDSP = "hdsp"
    DRIFT = "drift"


class HITLRequestCreate(BaseModel):
    """Model for creating a new HITL request."""

    agent_type: HITLAgentType = Field(description="Agent creating the request")
    request_type: HITLRequestType = Field(description="Type of HITL request")
    payload: Dict[str, Any] = Field(description="Detection result or request data")
    title: str = Field(description="Human-readable title")
    description: Optional[str] = Field(default=None, description="Detailed description")
    expires_in_minutes: int = Field(
        default=60,
        ge=5,
        le=10080,  # Max 7 days
        description="Request expiration time in minutes",
    )
    created_by: Optional[str] = Field(default=None, description="User or system creating request")


class HITLRequestResponse(BaseModel):
    """Model for HITL request response/approval."""

    approved: bool = Field(description="Whether the request is approved")
    response: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Response data or modifications",
    )
    comment: Optional[str] = Field(default=None, description="Reviewer comment")
    responded_by: Optional[str] = Field(default=None, description="User responding to request")


class HITLRequest(BaseModel):
    """Full HITL request model."""

    id: str = Field(description="Unique request identifier")
    agent_type: HITLAgentType = Field(description="Agent type")
    request_type: HITLRequestType = Field(description="Request type")
    status: HITLRequestStatus = Field(default=HITLRequestStatus.PENDING)
    payload: Dict[str, Any] = Field(description="Request payload")
    response: Optional[Dict[str, Any]] = Field(default=None, description="Response data")
    title: str = Field(description="Request title")
    description: Optional[str] = Field(default=None)
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    expires_at: datetime = Field(description="Expiration timestamp")
    created_by: Optional[str] = Field(default=None)
    responded_by: Optional[str] = Field(default=None)

    class Config:
        """Pydantic configuration."""

        from_attributes = True


class HITLRequestList(BaseModel):
    """List of HITL requests with metadata."""

    requests: List[HITLRequest] = Field(default_factory=list)
    total: int = Field(default=0, description="Total number of requests")
    pending_count: int = Field(default=0, description="Number of pending requests")


class HITLRequestFilter(BaseModel):
    """Filter parameters for HITL request queries."""

    agent_type: Optional[HITLAgentType] = Field(default=None)
    status: Optional[HITLRequestStatus] = Field(default=None)
    request_type: Optional[HITLRequestType] = Field(default=None)
    created_after: Optional[datetime] = Field(default=None)
    created_before: Optional[datetime] = Field(default=None)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
