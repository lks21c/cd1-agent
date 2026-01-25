"""
Handler Adapter for Lambda-to-HTTP migration.

Provides adapter pattern to reuse existing Lambda handlers
in HTTP server context without modification.
"""

import uuid
from typing import Any, Callable, Dict, Type

from src.common.handlers.base_handler import BaseHandler


class HTTPContext:
    """
    Mock Lambda context for HTTP requests.

    Provides Lambda-compatible context interface for
    handler reuse in HTTP server environment.
    """

    def __init__(self, request_id: str):
        self.aws_request_id = request_id
        self.function_name = "http-server"
        self.memory_limit_in_mb = 512
        self.log_group_name = "/http-server/agent"
        self.log_stream_name = f"http-server/{request_id}"
        self.invoked_function_arn = "arn:aws:lambda:local:http-server"

    def get_remaining_time_in_millis(self) -> int:
        """Return remaining time (unlimited for HTTP)."""
        return 900000  # 15 minutes


def create_handler_endpoint(
    handler_class: Type[BaseHandler],
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    Create HTTP endpoint from Lambda handler class.

    Args:
        handler_class: Lambda handler class extending BaseHandler

    Returns:
        Async endpoint function compatible with FastAPI

    Example:
        from src.agents.hdsp.handler import HDSPDetectionHandler

        endpoint = create_handler_endpoint(HDSPDetectionHandler)

        @router.post("/detect")
        async def detect(request: DetectionRequest):
            return await endpoint(request.model_dump())
    """
    # Create handler instance once (singleton pattern)
    handler_instance = handler_class()

    async def endpoint(request_body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process request through Lambda handler.

        Args:
            request_body: Request payload dictionary

        Returns:
            Handler response dictionary
        """
        # Create Lambda-compatible event
        event = {"body": request_body}

        # Create mock context
        context = HTTPContext(str(uuid.uuid4())[:8])

        # Process through handler
        response = handler_instance.handle(event, context)

        # Extract body from Lambda response format
        if isinstance(response, dict) and "body" in response:
            import json

            body = response["body"]
            if isinstance(body, str):
                return json.loads(body)
            return body

        return response

    return endpoint


def create_sync_handler_endpoint(
    handler_class: Type[BaseHandler],
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    Create synchronous HTTP endpoint from Lambda handler class.

    For handlers that don't support async operations.
    """
    handler_instance = handler_class()

    def endpoint(request_body: Dict[str, Any]) -> Dict[str, Any]:
        """Process request through Lambda handler synchronously."""
        event = {"body": request_body}
        context = HTTPContext(str(uuid.uuid4())[:8])
        response = handler_instance.handle(event, context)

        if isinstance(response, dict) and "body" in response:
            import json

            body = response["body"]
            if isinstance(body, str):
                return json.loads(body)
            return body

        return response

    return endpoint
