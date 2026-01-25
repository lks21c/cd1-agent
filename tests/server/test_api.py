"""Tests for FastAPI server endpoints."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


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
            "LLM_PROVIDER": "mock",
            "DEBUG": "true",
            "METRICS_ENABLED": "true",
        }):
            from src.agents.hdsp.server import app
            return TestClient(app)

    def test_metrics_endpoint(self, client):
        """Test metrics endpoint."""
        response = client.get("/metrics")

        assert response.status_code == 200
        # Should return Prometheus format
        assert "text/plain" in response.headers.get("content-type", "")
