"""
Server Routers Package.

Provides common API routers for all agent servers.
"""

from src.common.server.routers.health import create_health_router
from src.common.server.routers.metrics import create_metrics_router

__all__ = [
    "create_health_router",
    "create_metrics_router",
]
