"""
Health Check Router.

Provides health, readiness, and liveness endpoints for Kubernetes probes.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Response, status

from src.common.server.config import ServerSettings, get_settings

logger = logging.getLogger(__name__)


class HealthStatus:
    """Health status container."""

    def __init__(self, agent_name: str, settings: ServerSettings):
        self.agent_name = agent_name
        self.settings = settings
        self.start_time = datetime.utcnow()
        self._dependencies_healthy = True
        self._dependency_status: Dict[str, bool] = {}

    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy (liveness)."""
        return True  # Basic liveness - process is running

    @property
    def is_ready(self) -> bool:
        """Check if service is ready to receive traffic."""
        return self._dependencies_healthy

    def set_dependency_status(self, name: str, healthy: bool) -> None:
        """Update dependency health status."""
        self._dependency_status[name] = healthy
        self._dependencies_healthy = all(self._dependency_status.values())

    def get_status(self) -> Dict[str, Any]:
        """Get full health status."""
        return {
            "status": "healthy" if self.is_healthy else "unhealthy",
            "agent": self.agent_name,
            "environment": self.settings.environment,
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
            "dependencies": self._dependency_status,
            "timestamp": datetime.utcnow().isoformat(),
        }


def create_health_router(
    agent_name: str,
    settings: Optional[ServerSettings] = None,
) -> APIRouter:
    """
    Create health check router.

    Args:
        agent_name: Name of the agent
        settings: Server settings

    Returns:
        Configured APIRouter with health endpoints
    """
    router = APIRouter(tags=["health"])
    settings = settings or get_settings()
    health_status = HealthStatus(agent_name=agent_name, settings=settings)

    @router.get("/health")
    async def health_check() -> Dict[str, Any]:
        """
        Liveness probe endpoint.

        Used by Kubernetes to determine if the container is alive.
        Returns 200 if the process is running.
        """
        return {
            "status": "healthy",
            "agent": agent_name,
            "timestamp": datetime.utcnow().isoformat(),
        }

    @router.get("/ready")
    async def readiness_check(response: Response) -> Dict[str, Any]:
        """
        Readiness probe endpoint.

        Used by Kubernetes to determine if the container is ready
        to receive traffic. Checks downstream dependencies.
        """
        status_data = health_status.get_status()

        # Check dependencies based on agent type
        dependency_checks = []

        # DynamoDB check (all agents)
        if settings.aws_provider != "mock":
            dynamodb_healthy = await _check_dynamodb(settings)
            health_status.set_dependency_status("dynamodb", dynamodb_healthy)
            dependency_checks.append(dynamodb_healthy)

        # RDS check (BDP and HITL)
        if settings.rds_host and agent_name in ("bdp", "drift"):
            rds_healthy = await _check_rds(settings)
            health_status.set_dependency_status("rds", rds_healthy)
            dependency_checks.append(rds_healthy)

        # Prometheus check (HDSP only)
        if agent_name == "hdsp":
            prometheus_healthy = await _check_prometheus(settings)
            health_status.set_dependency_status("prometheus", prometheus_healthy)
            dependency_checks.append(prometheus_healthy)

        # Set response status based on checks
        if dependency_checks and not all(dependency_checks):
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            status_data["status"] = "unhealthy"

        return status_data

    @router.get("/status")
    async def status_endpoint() -> Dict[str, Any]:
        """
        Detailed status endpoint.

        Returns comprehensive status information about the agent.
        """
        return {
            **health_status.get_status(),
            "config": {
                "aws_provider": settings.aws_provider,
                "llm_provider": settings.llm_provider,
                "metrics_enabled": settings.metrics_enabled,
            },
        }

    return router


async def _check_dynamodb(settings: ServerSettings) -> bool:
    """Check DynamoDB connectivity."""
    try:
        import boto3

        if settings.is_localstack:
            dynamodb = boto3.client(
                "dynamodb",
                endpoint_url=settings.aws_endpoint_url or "http://localhost:4566",
                region_name=settings.aws_region,
            )
        else:
            dynamodb = boto3.client("dynamodb", region_name=settings.aws_region)

        # Simple list tables call to verify connectivity
        dynamodb.list_tables(Limit=1)
        return True
    except Exception as e:
        logger.warning(f"DynamoDB health check failed: {e}")
        return False


async def _check_rds(settings: ServerSettings) -> bool:
    """Check RDS connectivity."""
    try:
        import pymysql

        connection = pymysql.connect(
            host=settings.rds_host,
            port=settings.rds_port,
            user=settings.rds_user,
            password=settings.rds_password,
            database=settings.rds_database,
            connect_timeout=5,
        )
        connection.ping(reconnect=False)
        connection.close()
        return True
    except Exception as e:
        logger.warning(f"RDS health check failed: {e}")
        return False


async def _check_prometheus(settings: ServerSettings) -> bool:
    """Check Prometheus connectivity."""
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.prometheus_url}/-/ready",
                timeout=5.0,
            )
            return response.status_code == 200
    except Exception as e:
        logger.warning(f"Prometheus health check failed: {e}")
        return False
