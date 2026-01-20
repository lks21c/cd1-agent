"""
Server Middleware for logging, error handling, and request processing.

Provides common middleware components for all agent servers.
"""

import logging
import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging with timing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        # Log request
        start_time = time.time()
        logger.info(
            f"Request {request_id} started: {request.method} {request.url.path}"
        )

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Log response
            logger.info(
                f"Request {request_id} completed: {response.status_code} "
                f"in {duration:.3f}s"
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration:.3f}s"

            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Request {request_id} failed after {duration:.3f}s: {e}"
            )
            raise


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for global error handling."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except ValueError as e:
            logger.warning(f"Validation error: {e}")
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": str(e),
                    "request_id": getattr(request.state, "request_id", "unknown"),
                },
            )
        except Exception as e:
            logger.exception(f"Unhandled error: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "Internal server error",
                    "request_id": getattr(request.state, "request_id", "unknown"),
                },
            )


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the application."""
    # Order matters: ErrorHandling wraps RequestLogging
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestLoggingMiddleware)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging for the server."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
