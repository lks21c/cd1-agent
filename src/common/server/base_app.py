"""
FastAPI Application Factory.

Provides factory function to create FastAPI application instances
with consistent configuration for all agent servers.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.common.server.config import ServerSettings, get_settings
from src.common.server.middleware import setup_logging, setup_middleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def default_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Default application lifespan manager.

    Handles startup and shutdown events for resource management.
    """
    # Startup
    settings = get_settings()
    logger.info(f"Starting {settings.agent_name} server...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.agent_name} server...")


def create_app(
    agent_name: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    version: str = "1.0.0",
    settings: Optional[ServerSettings] = None,
    lifespan: Optional[Callable] = None,
    include_health: bool = True,
    include_metrics: bool = True,
) -> FastAPI:
    """
    Create FastAPI application instance.

    Args:
        agent_name: Name of the agent (cost, hdsp, bdp, drift)
        title: API title (defaults to agent name)
        description: API description
        version: API version
        settings: Server settings (uses default if not provided)
        lifespan: Custom lifespan manager
        include_health: Include health check endpoints
        include_metrics: Include Prometheus metrics endpoint

    Returns:
        Configured FastAPI application

    Example:
        from src.common.server import create_app

        app = create_app(
            agent_name="cost",
            title="Cost Detection Agent",
            description="AWS Cost anomaly detection service",
        )
    """
    settings = settings or get_settings()

    # Setup logging before app creation
    setup_logging(settings.log_level)

    # Create app with lifespan
    app = FastAPI(
        title=title or f"CD1 {agent_name.upper()} Agent",
        description=description or f"CD1 Agent - {agent_name.capitalize()} Detection Service",
        version=version,
        lifespan=lifespan or default_lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
    )

    # Store settings in app state
    app.state.settings = settings
    app.state.agent_name = agent_name

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Setup middleware
    setup_middleware(app)

    # Include health router
    if include_health:
        from src.common.server.routers.health import create_health_router

        health_router = create_health_router(agent_name=agent_name, settings=settings)
        app.include_router(health_router)

    # Include metrics router
    if include_metrics and settings.metrics_enabled:
        from src.common.server.routers.metrics import create_metrics_router

        metrics_router = create_metrics_router(settings=settings)
        app.include_router(metrics_router)

    logger.info(f"Created FastAPI app for {agent_name} agent")

    return app


def create_agent_app(
    agent_name: str,
    detection_router: Any,
    lifespan: Optional[Callable] = None,
    **kwargs: Dict[str, Any],
) -> FastAPI:
    """
    Create agent-specific FastAPI application.

    Convenience function that creates app and includes detection router.

    Args:
        agent_name: Name of the agent
        detection_router: Detection API router
        lifespan: Custom lifespan manager
        **kwargs: Additional arguments passed to create_app

    Returns:
        Configured FastAPI application with detection endpoints
    """
    app = create_app(
        agent_name=agent_name,
        lifespan=lifespan,
        **kwargs,
    )

    # Include detection router
    app.include_router(
        detection_router,
        prefix="/api/v1",
        tags=["detection"],
    )

    return app
