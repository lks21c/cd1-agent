"""
Base Handler for Lambda Functions.

Common functionality for all Lambda handlers.
"""

import json
import logging
import os
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class LambdaResponse:
    """Standardized Lambda response structure."""

    status_code: int
    body: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.headers:
            self.headers = {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Lambda response format."""
        return {
            "statusCode": self.status_code,
            "headers": self.headers,
            "body": json.dumps(self.body),
        }


class BaseHandler(ABC):
    """
    Abstract base handler for Lambda functions.

    Provides common functionality:
    - Logging setup
    - Error handling
    - Response formatting
    - Configuration loading
    """

    def __init__(self, logger_name: Optional[str] = None):
        self.logger = logging.getLogger(logger_name or self.__class__.__name__)
        self._setup_logging()
        self.config = self._load_config()

    def _setup_logging(self) -> None:
        """Configure logging based on environment."""
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.logger.setLevel(getattr(logging, log_level, logging.INFO))

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "[%(levelname)s] %(asctime)s - %(name)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        return {
            "environment": os.getenv("ENVIRONMENT", "dev"),
            "region": os.getenv("AWS_REGION", "ap-northeast-2"),
            "llm_provider": os.getenv("LLM_PROVIDER", "mock"),
            "aws_provider": os.getenv("AWS_PROVIDER", "mock"),
            "dynamodb_table": os.getenv("DYNAMODB_TABLE", "bdp-agent-results"),
            "event_bus": os.getenv("EVENT_BUS", "bdp-agent-events"),
            "knowledge_base_id": os.getenv("KNOWLEDGE_BASE_ID", ""),
            "max_iterations": int(os.getenv("MAX_ITERATIONS", "5")),
            "confidence_threshold": float(os.getenv("CONFIDENCE_THRESHOLD", "0.85")),
        }

    def handle(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        Main entry point for Lambda handler.

        Args:
            event: Lambda event payload
            context: Lambda context object

        Returns:
            Lambda response dictionary
        """
        request_id = getattr(context, "aws_request_id", "local")
        start_time = datetime.utcnow()

        self.logger.info(f"Request {request_id} started")
        self.logger.debug(f"Event: {json.dumps(event)[:500]}")

        try:
            # Validate input
            validation_error = self._validate_input(event)
            if validation_error:
                return self._error_response(400, validation_error, request_id).to_dict()

            # Process request
            result = self.process(event, context)

            # Format response
            response = self._success_response(result, request_id)

            duration = (datetime.utcnow() - start_time).total_seconds()
            self.logger.info(f"Request {request_id} completed in {duration:.2f}s")

            return response.to_dict()

        except ValueError as e:
            self.logger.warning(f"Validation error: {e}")
            return self._error_response(400, str(e), request_id).to_dict()

        except Exception as e:
            self.logger.error(f"Unhandled error: {e}")
            self.logger.error(traceback.format_exc())
            return self._error_response(500, "Internal server error", request_id).to_dict()

    @abstractmethod
    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        Process the Lambda event.

        Override in subclasses.

        Args:
            event: Lambda event payload
            context: Lambda context object

        Returns:
            Processing result dictionary
        """
        pass

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """
        Validate input event.

        Override in subclasses for specific validation.

        Args:
            event: Lambda event payload

        Returns:
            Error message if validation fails, None otherwise
        """
        return None

    def _success_response(
        self, result: Dict[str, Any], request_id: str
    ) -> LambdaResponse:
        """Create success response."""
        return LambdaResponse(
            status_code=200,
            body={
                "success": True,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": result,
            },
        )

    def _error_response(
        self, status_code: int, message: str, request_id: str
    ) -> LambdaResponse:
        """Create error response."""
        return LambdaResponse(
            status_code=status_code,
            body={
                "success": False,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
                "error": message,
            },
        )

    def _parse_body(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Parse request body from event."""
        body = event.get("body", {})
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {}
        return body

    def _get_path_parameter(
        self, event: Dict[str, Any], name: str, default: Optional[str] = None
    ) -> Optional[str]:
        """Get path parameter from event."""
        params = event.get("pathParameters", {}) or {}
        return params.get(name, default)

    def _get_query_parameter(
        self, event: Dict[str, Any], name: str, default: Optional[str] = None
    ) -> Optional[str]:
        """Get query string parameter from event."""
        params = event.get("queryStringParameters", {}) or {}
        return params.get(name, default)
