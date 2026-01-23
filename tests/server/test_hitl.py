"""Tests for HITL (Human-in-the-Loop) module."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

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
        # Create a request with minimum expiry
        created = mock_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Expired Request",
            expires_in_minutes=5,
        ))

        # Manually set expires_at to past (simulating an expired request)
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


class TestHITLStoreSQLite:
    """Tests for HITLStore with SQLite provider."""

    @pytest.fixture
    def sqlite_store(self, tmp_path):
        """Create SQLite HITL store with temp file."""
        db_path = tmp_path / "test_hitl.db"
        store = HITLStore(provider="sqlite", sqlite_path=str(db_path))
        store.ensure_table()
        yield store
        store.close()

    def test_sqlite_provider_initialization(self, tmp_path):
        """Test SQLite provider initialization."""
        db_path = tmp_path / "test_init.db"
        store = HITLStore(provider="sqlite", sqlite_path=str(db_path))

        assert store.provider == "sqlite"
        assert store.use_mock is False
        store.close()

    def test_sqlite_ensure_table(self, tmp_path):
        """Test SQLite table creation."""
        db_path = tmp_path / "test_table.db"
        store = HITLStore(provider="sqlite", sqlite_path=str(db_path))
        store.ensure_table()

        # Verify table exists
        conn = store._get_sqlite_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='hitl_requests'"
        )
        assert cursor.fetchone() is not None
        store.close()

    def test_sqlite_create_request(self, sqlite_store):
        """Test creating a HITL request with SQLite."""
        request = HITLRequestCreate(
            agent_type=HITLAgentType.BDP,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={"severity": "medium", "cluster": "prod-1"},
            title="BDP Anomaly Approval",
            description="Test description",
            expires_in_minutes=45,
        )

        result = sqlite_store.create(request)

        assert result.id is not None
        assert len(result.id) == 36  # UUID format
        assert result.agent_type == HITLAgentType.BDP
        assert result.request_type == HITLRequestType.ACTION_APPROVAL
        assert result.status == HITLRequestStatus.PENDING
        assert result.payload == {"severity": "medium", "cluster": "prod-1"}
        assert result.title == "BDP Anomaly Approval"

    def test_sqlite_get_request(self, sqlite_store):
        """Test getting a HITL request by ID with SQLite."""
        create_req = HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.CONFIRMATION,
            payload={"service": "EC2"},
            title="Cost Confirmation",
        )
        created = sqlite_store.create(create_req)

        result = sqlite_store.get(created.id)

        assert result is not None
        assert result.id == created.id
        assert result.agent_type == HITLAgentType.COST
        assert result.payload == {"service": "EC2"}

    def test_sqlite_get_nonexistent(self, sqlite_store):
        """Test getting nonexistent request returns None."""
        result = sqlite_store.get("nonexistent-uuid-1234-5678-abcd")
        assert result is None

    def test_sqlite_list_requests(self, sqlite_store):
        """Test listing HITL requests with SQLite."""
        for i in range(5):
            sqlite_store.create(HITLRequestCreate(
                agent_type=HITLAgentType.HDSP,
                request_type=HITLRequestType.ACTION_APPROVAL,
                payload={"index": i},
                title=f"HDSP Request {i}",
            ))

        results = sqlite_store.list_requests()

        assert len(results) == 5

    def test_sqlite_list_with_filter(self, sqlite_store):
        """Test listing with filter on SQLite."""
        sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Cost Request",
        ))
        sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.BDP,
            request_type=HITLRequestType.CONFIRMATION,
            payload={},
            title="BDP Request",
        ))
        sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.DRIFT,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Drift Request",
        ))

        # Filter by agent type
        filter_obj = HITLRequestFilter(agent_type=HITLAgentType.BDP)
        results = sqlite_store.list_requests(filter_obj)

        assert len(results) == 1
        assert results[0].agent_type == HITLAgentType.BDP

    def test_sqlite_list_with_status_filter(self, sqlite_store):
        """Test listing with status filter."""
        req1 = sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Request 1",
        ))
        sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.BDP,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Request 2",
        ))

        # Approve first request
        sqlite_store.respond(req1.id, HITLRequestResponse(approved=True))

        # Filter by pending status
        filter_obj = HITLRequestFilter(status=HITLRequestStatus.PENDING)
        results = sqlite_store.list_requests(filter_obj)

        assert len(results) == 1
        assert results[0].status == HITLRequestStatus.PENDING

    def test_sqlite_respond_approve(self, sqlite_store):
        """Test approving a request with SQLite."""
        created = sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.DRIFT,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={"drift": "config-change"},
            title="Drift Approval",
        ))

        response = HITLRequestResponse(
            approved=True,
            response={"action": "remediate", "method": "rollback"},
            responded_by="ops-admin",
        )
        result = sqlite_store.respond(created.id, response)

        assert result is not None
        assert result.status == HITLRequestStatus.APPROVED
        assert result.response == {"action": "remediate", "method": "rollback"}
        assert result.responded_by == "ops-admin"

    def test_sqlite_respond_reject(self, sqlite_store):
        """Test rejecting a request with SQLite."""
        created = sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.BDP,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="BDP Approval",
        ))

        response = HITLRequestResponse(
            approved=False,
            comment="Invalid request",
            responded_by="reviewer",
        )
        result = sqlite_store.respond(created.id, response)

        assert result.status == HITLRequestStatus.REJECTED

    def test_sqlite_cancel_request(self, sqlite_store):
        """Test cancelling a request with SQLite."""
        created = sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.PROMPT_INPUT,
            payload={},
            title="Cost Input Request",
        ))

        result = sqlite_store.cancel(created.id)

        assert result is not None
        assert result.status == HITLRequestStatus.CANCELLED

    def test_sqlite_cancel_non_pending_fails(self, sqlite_store):
        """Test cancelling non-pending request fails."""
        created = sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.HDSP,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="HDSP Request",
        ))

        # Approve first
        sqlite_store.respond(created.id, HITLRequestResponse(approved=True))

        # Try to cancel - should fail
        result = sqlite_store.cancel(created.id)
        assert result is None

    def test_sqlite_get_pending_count(self, sqlite_store):
        """Test getting pending count with SQLite."""
        for i in range(4):
            sqlite_store.create(HITLRequestCreate(
                agent_type=HITLAgentType.COST,
                request_type=HITLRequestType.ACTION_APPROVAL,
                payload={},
                title=f"Request {i}",
            ))

        # Approve one
        requests = sqlite_store.list_requests()
        sqlite_store.respond(requests[0].id, HITLRequestResponse(approved=True))

        count = sqlite_store.get_pending_count()
        assert count == 3

    def test_sqlite_get_pending_count_by_agent(self, sqlite_store):
        """Test getting pending count by agent type."""
        sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Cost 1",
        ))
        sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Cost 2",
        ))
        sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.BDP,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="BDP 1",
        ))

        cost_count = sqlite_store.get_pending_count(HITLAgentType.COST)
        bdp_count = sqlite_store.get_pending_count(HITLAgentType.BDP)

        assert cost_count == 2
        assert bdp_count == 1

    def test_sqlite_datetime_handling(self, sqlite_store):
        """Test datetime values are properly stored and retrieved."""
        before_create = datetime.utcnow()

        created = sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload={},
            title="Datetime Test",
            expires_in_minutes=60,
        ))

        after_create = datetime.utcnow()

        # Retrieve and verify
        result = sqlite_store.get(created.id)

        # Allow 1 second tolerance for datetime comparison due to ISO8601 precision
        tolerance = timedelta(seconds=1)
        assert result.created_at >= before_create - tolerance
        assert result.created_at <= after_create + tolerance
        assert result.expires_at > result.created_at

    def test_sqlite_json_payload(self, sqlite_store):
        """Test complex JSON payload storage and retrieval."""
        complex_payload = {
            "anomaly": {
                "type": "cost_spike",
                "severity": "high",
                "metrics": [1.5, 2.3, 4.1],
            },
            "context": {
                "service": "EC2",
                "region": "ap-northeast-2",
                "tags": ["production", "critical"],
            },
            "threshold": 100.0,
            "actual": 250.5,
        }

        created = sqlite_store.create(HITLRequestCreate(
            agent_type=HITLAgentType.COST,
            request_type=HITLRequestType.ACTION_APPROVAL,
            payload=complex_payload,
            title="Complex Payload Test",
        ))

        result = sqlite_store.get(created.id)

        assert result.payload == complex_payload
        assert result.payload["anomaly"]["metrics"] == [1.5, 2.3, 4.1]


class TestHITLStoreProviderResolution:
    """Tests for provider resolution logic."""

    def test_explicit_provider_overrides_env(self, monkeypatch, tmp_path):
        """Test explicit provider parameter overrides environment."""
        monkeypatch.setenv("RDS_PROVIDER", "mysql")
        db_path = tmp_path / "test.db"

        store = HITLStore(provider="sqlite", sqlite_path=str(db_path))

        assert store.provider == "sqlite"
        store.close()

    def test_use_mock_overrides_env(self, monkeypatch):
        """Test use_mock=True overrides environment."""
        monkeypatch.setenv("RDS_PROVIDER", "mysql")

        store = HITLStore(use_mock=True)

        assert store.provider == "mock"
        assert store.use_mock is True

    def test_env_provider_sqlite(self, monkeypatch, tmp_path):
        """Test RDS_PROVIDER=sqlite from environment."""
        monkeypatch.setenv("RDS_PROVIDER", "sqlite")
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("SQLITE_PATH", str(db_path))

        store = HITLStore()

        assert store.provider == "sqlite"
        store.close()

    def test_env_provider_mysql(self, monkeypatch):
        """Test RDS_PROVIDER=mysql from environment."""
        monkeypatch.setenv("RDS_PROVIDER", "mysql")

        store = HITLStore()

        assert store.provider == "mysql"

    def test_default_provider_is_mock(self):
        """Test default provider is mock when nothing specified."""
        store = HITLStore()

        assert store.provider == "mock"
        assert store.use_mock is True

    def test_legacy_use_mock_property(self, tmp_path):
        """Test legacy use_mock property for backward compatibility."""
        db_path = tmp_path / "test.db"

        mock_store = HITLStore(provider="mock")
        sqlite_store = HITLStore(provider="sqlite", sqlite_path=str(db_path))

        assert mock_store.use_mock is True
        assert sqlite_store.use_mock is False

        sqlite_store.close()
