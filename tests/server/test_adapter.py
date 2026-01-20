"""Tests for handler adapter module."""

import pytest

from src.common.server.adapter import HTTPContext, create_handler_endpoint
from src.common.handlers.base_handler import BaseHandler


class MockHandler(BaseHandler):
    """Mock handler for testing."""

    def __init__(self):
        super().__init__("MockHandler")

    def process(self, event, context):
        """Simple process that echoes input."""
        body = self._parse_body(event)
        return {
            "received": body,
            "request_id": getattr(context, "aws_request_id", "unknown"),
        }


class TestHTTPContext:
    """Tests for HTTPContext class."""

    def test_context_creation(self):
        """Test HTTPContext creation."""
        ctx = HTTPContext("test-req-123")

        assert ctx.aws_request_id == "test-req-123"
        assert ctx.function_name == "http-server"
        assert ctx.memory_limit_in_mb == 512

    def test_get_remaining_time(self):
        """Test remaining time method."""
        ctx = HTTPContext("test-req")

        # Should return large value for HTTP (no timeout)
        remaining = ctx.get_remaining_time_in_millis()
        assert remaining == 900000  # 15 minutes


class TestHandlerAdapter:
    """Tests for handler adapter functions."""

    @pytest.mark.asyncio
    async def test_create_handler_endpoint(self):
        """Test creating endpoint from handler."""
        endpoint = create_handler_endpoint(MockHandler)

        result = await endpoint({"test_key": "test_value"})

        assert result["success"] is True
        assert result["data"]["received"]["test_key"] == "test_value"

    @pytest.mark.asyncio
    async def test_handler_endpoint_empty_body(self):
        """Test endpoint with empty body."""
        endpoint = create_handler_endpoint(MockHandler)

        result = await endpoint({})

        assert result["success"] is True
        assert result["data"]["received"] == {}

    @pytest.mark.asyncio
    async def test_handler_endpoint_preserves_request_id(self):
        """Test that request ID is generated."""
        endpoint = create_handler_endpoint(MockHandler)

        result = await endpoint({"data": "test"})

        assert result["success"] is True
        # Request ID should be 8 characters
        assert len(result["data"]["request_id"]) == 8


class TestHandlerIntegration:
    """Integration tests for handler adapter with real handlers."""

    @pytest.mark.asyncio
    async def test_cost_handler_adapter(self):
        """Test adapter with Cost handler."""
        from src.agents.cost.handler import CostDetectionHandler

        endpoint = create_handler_endpoint(CostDetectionHandler)

        result = await endpoint({"detection_type": "all", "days": 7})

        assert result["success"] is True
        assert "data" in result
        assert result["data"]["detection_type"] == "all"

    @pytest.mark.asyncio
    async def test_hdsp_handler_adapter(self):
        """Test adapter with HDSP handler."""
        from src.agents.hdsp.handler import HDSPDetectionHandler

        endpoint = create_handler_endpoint(HDSPDetectionHandler)

        result = await endpoint({"detection_type": "all"})

        assert result["success"] is True
        assert "data" in result
