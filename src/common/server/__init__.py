"""
Server Module for HTTP-based Agent Deployment.

Provides FastAPI application factory and common server components
for migrating Lambda handlers to Kubernetes pods.
"""

from src.common.server.base_app import create_app
from src.common.server.config import ServerSettings, get_settings
from src.common.server.adapter import HTTPContext, create_handler_endpoint

__all__ = [
    "create_app",
    "ServerSettings",
    "get_settings",
    "HTTPContext",
    "create_handler_endpoint",
]
