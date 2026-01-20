"""Tests for FastAPI server endpoints."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestCostAgentAPI:
    """Tests for Cost Agent API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client for Cost agent."""
        with patch.dict(os.environ, {
            "AWS_PROVIDER": "mock",
            "COST_PROVIDER": "mock",
            "LLM_PROVIDER": "mock",
            "DEBUG": "true",
        }):
            from src.agents.cost.server import app
            return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["agent"] == "cost"

    def test_ready_endpoint(self, client):
        """Test readiness endpoint."""
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "uptime_seconds" in data

    def test_status_endpoint(self, client):
        """Test status endpoint."""
        response = client.get("/api/v1/status")

        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "cost"
        assert "config" in data

    def test_detect_endpoint(self, client):
        """Test detection endpoint."""
        response = client.post(
            "/api/v1/detect",
            json={"detection_type": "all", "days": 7},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["detection_type"] == "all"
        assert "anomalies_detected" in data

    def test_detect_forecast(self, client):
        """Test forecast detection."""
        response = client.post(
            "/api/v1/detect",
            json={"detection_type": "forecast", "days": 7},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["detection_type"] == "forecast"

    def test_hitl_create_request(self, client):
        """Test creating HITL request."""
        response = client.post(
            "/api/v1/hitl/requests",
            json={
                "agent_type": "cost",
                "request_type": "action_approval",
                "payload": {"severity": "high"},
                "title": "Test HITL Request",
                "expires_in_minutes": 60,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["agent_type"] == "cost"
        assert data["status"] == "pending"

    def test_hitl_list_requests(self, client):
        """Test listing HITL requests."""
        # Create a request first
        client.post(
            "/api/v1/hitl/requests",
            json={
                "agent_type": "cost",
                "request_type": "action_approval",
                "payload": {},
                "title": "Test Request",
            },
        )

        response = client.get("/api/v1/hitl/requests")

        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        assert "pending_count" in data

    def test_hitl_pending_count(self, client):
        """Test getting pending count."""
        response = client.get("/api/v1/hitl/pending-count")

        assert response.status_code == 200
        data = response.json()
        assert "pending_count" in data


class TestHDSPAgentAPI:
    """Tests for HDSP Agent API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client for HDSP agent."""
        with patch.dict(os.environ, {
            "AWS_PROVIDER": "mock",
            "LLM_PROVIDER": "mock",
            "DEBUG": "true",
        }):
            from src.agents.hdsp.server import app
            return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "hdsp"

    def test_detect_all(self, client):
        """Test full detection."""
        response = client.post(
            "/api/v1/detect",
            json={"detection_type": "all"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["detection_type"] == "all"

    def test_detect_pod_failure(self, client):
        """Test pod failure detection."""
        response = client.post(
            "/api/v1/detect",
            json={"detection_type": "pod_failure"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["detection_type"] == "pod_failure"


class TestBDPAgentAPI:
    """Tests for BDP Agent API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client for BDP agent."""
        with patch.dict(os.environ, {
            "AWS_PROVIDER": "mock",
            "LLM_PROVIDER": "mock",
            "RDS_PROVIDER": "mock",
            "DEBUG": "true",
        }):
            from src.agents.bdp.server import app
            return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "bdp"

    def test_detect_scheduled(self, client):
        """Test scheduled detection."""
        response = client.post(
            "/api/v1/detect",
            json={"detection_type": "scheduled"},
        )

        assert response.status_code == 200


class TestDriftAgentAPI:
    """Tests for Drift Agent API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client for Drift agent."""
        with patch.dict(os.environ, {
            "AWS_PROVIDER": "mock",
            "LLM_PROVIDER": "mock",
            "ENABLE_DRIFT_ANALYSIS": "false",
            "DEBUG": "true",
        }):
            from src.agents.drift.server import app
            return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "drift"

    def test_status_endpoint(self, client):
        """Test status endpoint."""
        response = client.get("/api/v1/status")

        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "drift"
        assert "drift_analysis_enabled" in data["config"]


class TestMetricsEndpoint:
    """Tests for Prometheus metrics endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        with patch.dict(os.environ, {
            "AWS_PROVIDER": "mock",
            "COST_PROVIDER": "mock",
            "LLM_PROVIDER": "mock",
            "DEBUG": "true",
            "METRICS_ENABLED": "true",
        }):
            from src.agents.cost.server import app
            return TestClient(app)

    def test_metrics_endpoint(self, client):
        """Test metrics endpoint."""
        response = client.get("/metrics")

        assert response.status_code == 200
        # Should return Prometheus format
        assert "text/plain" in response.headers.get("content-type", "")
