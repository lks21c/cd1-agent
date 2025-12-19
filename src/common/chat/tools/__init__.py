"""
Chat Tools - 대화형 에이전트용 Tool 래퍼.
"""

from typing import Callable, Dict, Optional

from src.common.services.aws_client import AWSClient
from src.common.services.rds_client import RDSClient
from src.common.services.llm_client import LLMClient
from src.common.chat.tools.cloudwatch import (
    get_cloudwatch_metrics,
    query_cloudwatch_logs,
    create_cloudwatch_tools,
)
from src.common.chat.tools.service_health import (
    get_service_health,
    check_recent_deployments,
    create_service_health_tools,
)
from src.common.chat.tools.prometheus import (
    get_prometheus_metrics,
    get_pod_status,
    create_prometheus_tools,
)
from src.common.chat.tools.rds import (
    create_rds_tools,
    query_anomalies,
    query_metrics,
)
from src.common.chat.tools.drift import (
    analyze_config_drift,
    check_drift_status,
    get_remediation_plan,
    approve_remediation,
    create_drift_tools,
)


def create_chat_tools(
    aws_client: AWSClient,
    rds_client: Optional[RDSClient] = None,
    llm_client: Optional[LLMClient] = None,
) -> Dict[str, Callable]:
    """
    Chat 에이전트용 전체 Tool 세트 생성.

    Args:
        aws_client: AWS 클라이언트
        rds_client: RDS 클라이언트 (선택, 없으면 Mock 사용)
        llm_client: LLM 클라이언트 (선택, Drift 분석용)

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

    # Drift Analysis Tools (LLM 기반 원인 분석 + HITL)
    tools.update(create_drift_tools(llm_client))

    return tools


__all__ = [
    "create_chat_tools",
    "create_rds_tools",
    "create_drift_tools",
    "get_cloudwatch_metrics",
    "query_cloudwatch_logs",
    "get_service_health",
    "check_recent_deployments",
    "get_prometheus_metrics",
    "get_pod_status",
    "query_anomalies",
    "query_metrics",
    # Drift Analysis Tools
    "analyze_config_drift",
    "check_drift_status",
    "get_remediation_plan",
    "approve_remediation",
]
