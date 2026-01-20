"""Tests for HITL (Human-in-the-Loop) module."""

from datetime import datetime, timedelta

import pytest

from src.common.hitl.schemas import (
    HITLAgentType,
    HITLRequest,
    HITLRequestCreate,
    HITLRequestFilter,
    HITLRequestResponse,
    HITLRequestStatus,
    HITLRequestType,
)
from src.common.hitl.store import HITLStore


class TestHITLSchemas:
    """Tests for HITL Pydantic schemas."""

    def test_hitl_request_create(self):
        """Test HITLRequestCreate model."""
        request = HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={"anomaly": "test"},
            title="Test Request",
            description="Test description",
            expires_in_minutes=30,
        )

        assert request.agent_type == HITLAgentType.COST
        assert request.request_type == HITLRequestType.ACTION_APPROVAL
        assert request.payload == {"anomaly": "test"}
        assert request.title == "Test Request"
        assert request.expires_in_minutes == 30

    def test_hitl_request_response(self):
        """Test HITLRequestResponse model."""
        response = HITLRequestResponse(
            approved=True,
            response={"action": "approved"},
            comment="Looks good",
            responded_by="admin",
        )

        assert response.approved is True
        assert response.response == {"action": "approved"}
        assert response.comment == "Looks good"
        assert response.responded_by == "admin"

    def test_hitl_request_filter(self):
        """Test HITLRequestFilter model."""
        filter_obj = HITLRequestFilter(
            agent_type=HITLAgentType.BDP,
            status=HITLRequestStatus.PENDING,
            limit=10,
            offset=5,
        )

        assert filter_obj.agent_type == HITLAgentType.BDP
        assert filter_obj.status == HITLRequestStatus.PENDING
        assert filter_obj.limit == 10
        assert filter_obj.offset == 5


class TestHITLStore:
    """Tests for HITLStore class."""

    @pytest.fixture
    def mock_store(self):
        """Create mock HITL store."""
        return HITLStore(use_mock=True)

    def test_create_request(self, mock_store):
        """Test creating a HITL request."""
        request = HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={"severity": "high", "service": "EC2"},
            title="Cost Anomaly Approval",
            expires_in_minutes=60,
        )

        result = mock_store.create(request)

        assert result.id is not None
        assert result.agent_type == HITLAgentType.COST
        assert result.request_type == HITLRequestType.ACTION_APPROVAL
        assert result.status == HITLRequestStatus.PENDING
        assert result.payload == {"severity": "high", "service": "EC2"}

    def test_get_request(self, mock_store):
        """Test getting a HITL request by ID."""
        # Create request
        create_req = HITLRequestCreate(
            agent_type=HITLAgentType.HDSP,
            request_type=HITLRequestType.CONFIRMATION,
            payload={"cluster": "prod"},
            title="HDSP Confirmation",
        )
        created = mock_store.create(create_req)

        # Get request
        result = mock_store.get(created.id)

        assert result is not None
        assert result.id == created.id
        assert result.agent_type == HITLAgentType.HDSP

    def test_get_nonexistent_request(self, mock_store):
        """Test getting nonexistent request returns None."""
        result = mock_store.get("nonexistent-id")
        assert result is None

    def test_list_requests(self, mock_store):
        """Test listing HITL requests."""
        # Create multiple requests
        for i in range(3):
            mock_store.create(HITLRequestCreate(
                agent_type=HITLAgentType.COST,
                request_type=HITLRequestType.ACTION_APPROVAL,
                payload={"index": i},
                title=f"Request {i}",
            ))

        results = mock_store.list_requests()

        assert len(results) == 3

    def test_list_requests_with_filter(self, mock_store):
        """Test listing requests with filter."""
        # Create requests for different agents
        mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Cost Request",
        ))
        mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.BDP,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="BDP Request",
        ))

        # Filter by agent type
        filter_obj = HITLRequestFilter(agent_type=HITLAgentType.COST)
        results = mock_store.list_requests(filter_obj)

        assert len(results) == 1
        assert results[0].agent_type == HITLAgentType.COST

    def test_respond_approve(self, mock_store):
        """Test approving a HITL request."""
        # Create request
        created = mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.DRIFT,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={"drift": "detected"},
            title="Drift Approval",
        ))

        # Approve
        response = HITLRequestResponse(
            approved=True,
            response={"action": "remediate"},
            responded_by="admin",
        )
        result = mock_store.respond(created.id, response)

        assert result is not None
        assert result.status == HITLRequestStatus.APPROVED
        assert result.response == {"action": "remediate"}
        assert result.responded_by == "admin"

    def test_respond_reject(self, mock_store):
        """Test rejecting a HITL request."""
        created = mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.BDP,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="BDP Approval",
        ))

        response = HITLRequestResponse(
            approved=False,
            comment="Not appropriate",
            responded_by="reviewer",
        )
        result = mock_store.respond(created.id, response)

        assert result.status == HITLRequestStatus.REJECTED

    def test_cancel_request(self, mock_store):
        """Test cancelling a HITL request."""
        created = mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.PROMPT_INPUT,
            payload={},
            title="Prompt Request",
        ))

        result = mock_store.cancel(created.id)

        assert result is not None
        assert result.status == HITLRequestStatus.CANCELLED

    def test_cancel_non_pending_fails(self, mock_store):
        """Test cancelling non-pending request fails."""
        created = mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.HDSP,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="HDSP Request",
        ))

        # Approve first
        mock_store.respond(created.id, HITLRequestResponse(approved=True))

        # Try to cancel - should fail
        result = mock_store.cancel(created.id)
        assert result is None

    def test_expire_stale_requests(self, mock_store):
        """Test expiring stale requests."""
        # Create a request that's already expired
        created = mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Expired Request",
            expires_in_minutes=0,  # Expires immediately
        ))

        # Manually set expires_at to past
        mock_store._mock_store[created.id].expires_at = (
            datetime.utcnow() - timedelta(minutes=1)
        )

        # Expire stale
        count = mock_store.expire_stale_requests()

        assert count >= 1

        # Verify status
        result = mock_store.get(created.id)
        assert result.status == HITLRequestStatus.EXPIRED

    def test_get_pending_count(self, mock_store):
        """Test getting pending request count."""
        # Create pending requests
        for i in range(3):
            mock_store.create(HITLRequestCreate(
                agent_type=HITLAgentType.COST,
                request_type=HITLRequestType.ACTION_APPROVAL,
                payload={},
                title=f"Request {i}",
            ))

        # Approve one
        requests = mock_store.list_requests()
        mock_store.respond(
            requests[0].id,
            HITLRequestResponse(approved=True),
        )

        count = mock_store.get_pending_count()
        assert count == 2

    def test_get_pending_count_by_agent(self, mock_store):
        """Test getting pending count filtered by agent."""
        mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Cost 1",
        ))
        mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Cost 2",
        ))
        mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.BDP,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="BDP 1",
        ))

        cost_count = mock_store.get_pending_count(HITLAgentType.COST)
        bdp_count = mock_store.get_pending_count(HITLAgentType.BDP)

        assert cost_count == 2
        assert bdp_count == 1
