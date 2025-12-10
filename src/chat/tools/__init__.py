"""
Chat Tools - 대화형 에이전트용 Tool 래퍼.
"""

from typing import Callable, Dict, Optional

from src.services.aws_client import AWSClient
from src.services.rds_client import RDSClient
from src.chat.tools.cloudwatch import (
    get_cloudwatch_metrics,
    query_cloudwatch_logs,
    create_cloudwatch_tools,
)
from src.chat.tools.service_health import (
    get_service_health,
    check_recent_deployments,
    create_service_health_tools,
)
from src.chat.tools.prometheus import (
    get_prometheus_metrics,
    get_pod_status,
    create_prometheus_tools,
)
from src.chat.tools.rds import (
    create_rds_tools,
    query_anomalies,
    query_metrics,
)


def create_chat_tools(
    aws_client: AWSClient,
    rds_client: Optional[RDSClient] = None,
) -> Dict[str, Callable]:
    """
    Chat 에이전트용 전체 Tool 세트 생성.

    Args:
        aws_client: AWS 클라이언트
        rds_client: RDS 클라이언트 (선택, 없으면 Mock 사용)

    Returns:
        Tool 딕셔너리
    """
    tools = {}

    # CloudWatch Tools
    tools.update(create_cloudwatch_tools(aws_client))

    # Service Health Tools
    tools.update(create_service_health_tools(aws_client))

    # Prometheus Tools (Mock)
    tools.update(create_prometheus_tools())

    # RDS Tools
    tools.update(create_rds_tools(rds_client))

    return tools


__all__ = [
    "create_chat_tools",
    "create_rds_tools",
    "get_cloudwatch_metrics",
    "query_cloudwatch_logs",
    "get_service_health",
    "check_recent_deployments",
    "get_prometheus_metrics",
    "get_pod_status",
    "query_anomalies",
    "query_metrics",
]
