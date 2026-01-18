"""
Service Health Tools - 서비스 상태 관련 Tool.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from src.common.services.aws_client import AWSClient

logger = logging.getLogger(__name__)


def get_service_health(
    aws_client: AWSClient,
    service_name: str = "default",
) -> Dict[str, Any]:
    """
    서비스 전체 상태 조회.

    Args:
        aws_client: AWS 클라이언트
        service_name: 서비스 이름

    Returns:
        서비스 상태 정보
    """
    logger.info(f"서비스 상태 조회: {service_name}")

    try:
        # 메트릭 수집
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)

        # CPU 사용률
        cpu_metrics = aws_client.get_cloudwatch_metrics(
            namespace="AWS/Lambda",
            metric_name="Duration",
            dimensions=[{"Name": "FunctionName", "Value": service_name}],
            start_time=start_time,
            end_time=end_time,
            period=300,
            statistics=["Average"],
        )

        # 에러율
        error_metrics = aws_client.get_cloudwatch_metrics(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions=[{"Name": "FunctionName", "Value": service_name}],
            start_time=start_time,
            end_time=end_time,
            period=300,
            statistics=["Sum"],
        )

        # 호출 횟수
        invocation_metrics = aws_client.get_cloudwatch_metrics(
            namespace="AWS/Lambda",
            metric_name="Invocations",
            dimensions=[{"Name": "FunctionName", "Value": service_name}],
            start_time=start_time,
            end_time=end_time,
            period=300,
            statistics=["Sum"],
        )

        # 상태 계산
        total_invocations = sum(invocation_metrics.get("values", [0]))
        total_errors = sum(error_metrics.get("values", [0]))
        error_rate = (total_errors / total_invocations * 100) if total_invocations > 0 else 0

        # 상태 판단
        if error_rate > 10:
            health_status = "critical"
        elif error_rate > 5:
            health_status = "warning"
        else:
            health_status = "healthy"

        return {
            "service_name": service_name,
            "health_status": health_status,
            "metrics": {
                "total_invocations": total_invocations,
                "total_errors": total_errors,
                "error_rate": f"{error_rate:.2f}%",
                "avg_duration": cpu_metrics.get("average", 0),
            },
            "time_range": f"{start_time.isoformat()} ~ {end_time.isoformat()}",
            "success": True,
        }

    except Exception as e:
        logger.error(f"서비스 상태 조회 실패: {e}")
        return {
            "service_name": service_name,
            "health_status": "unknown",
            "error": str(e),
            "success": False,
        }


def check_recent_deployments(
    aws_client: AWSClient,
    service_name: str = "default",
    hours: int = 24,
) -> Dict[str, Any]:
    """
    최근 배포 이력 조회.

    Args:
        aws_client: AWS 클라이언트
        service_name: 서비스 이름
        hours: 조회 기간 (시간)

    Returns:
        배포 이력
    """
    logger.info(f"배포 이력 조회: {service_name}")

    # TODO: 실제 배포 이력 조회 구현
    # CodeDeploy, Lambda 버전, ECS 태스크 등에서 조회

    return {
        "service_name": service_name,
        "deployments": [
            {
                "version": "v1.2.3",
                "timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                "status": "success",
                "changes": ["Bug fix for authentication", "Performance improvement"],
            }
        ],
        "time_range": f"최근 {hours}시간",
        "success": True,
    }


def create_service_health_tools(aws_client: AWSClient) -> Dict[str, Callable]:
    """Service Health Tool 세트 생성."""

    def _get_health(**kwargs) -> Dict[str, Any]:
        return get_service_health(aws_client, **kwargs)

    def _check_deployments(**kwargs) -> Dict[str, Any]:
        return check_recent_deployments(aws_client, **kwargs)

    return {
        "get_service_health": _get_health,
        "check_recent_deployments": _check_deployments,
    }
