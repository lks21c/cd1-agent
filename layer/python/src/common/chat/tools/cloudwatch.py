"""
CloudWatch Tools - AWS CloudWatch 관련 Tool.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from src.common.services.aws_client import AWSClient

logger = logging.getLogger(__name__)


def get_cloudwatch_metrics(
    aws_client: AWSClient,
    service_name: str = "default",
    metric_name: str = "CPUUtilization",
    namespace: str = "AWS/Lambda",
    hours: int = 1,
) -> Dict[str, Any]:
    """
    CloudWatch 메트릭 조회.

    Args:
        aws_client: AWS 클라이언트
        service_name: 서비스 이름
        metric_name: 메트릭 이름
        namespace: CloudWatch 네임스페이스
        hours: 조회 기간 (시간)

    Returns:
        메트릭 데이터
    """
    logger.info(f"CloudWatch 메트릭 조회: {service_name}/{metric_name}")

    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        result = aws_client.get_cloudwatch_metrics(
            namespace=namespace,
            metric_name=metric_name,
            dimensions=[{"Name": "FunctionName", "Value": service_name}],
            start_time=start_time,
            end_time=end_time,
            period=300,  # 5분
            statistics=["Average", "Maximum", "Minimum"],
        )

        return {
            "service_name": service_name,
            "metric_name": metric_name,
            "namespace": namespace,
            "time_range": f"{start_time.isoformat()} ~ {end_time.isoformat()}",
            "data": result,
            "success": True,
        }

    except Exception as e:
        logger.error(f"CloudWatch 메트릭 조회 실패: {e}")
        return {
            "service_name": service_name,
            "metric_name": metric_name,
            "error": str(e),
            "success": False,
        }


def query_cloudwatch_logs(
    aws_client: AWSClient,
    log_group: str = "/aws/lambda/default",
    query: str = "fields @timestamp, @message | sort @timestamp desc | limit 20",
    hours: int = 1,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    CloudWatch Logs Insights 쿼리 실행.

    Args:
        aws_client: AWS 클라이언트
        log_group: 로그 그룹
        query: Insights 쿼리
        hours: 조회 기간 (시간)
        limit: 최대 결과 수

    Returns:
        로그 쿼리 결과
    """
    logger.info(f"CloudWatch Logs 쿼리: {log_group}")

    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        result = aws_client.query_cloudwatch_logs(
            log_group_name=log_group,
            query_string=query,
            start_time=int(start_time.timestamp()),
            end_time=int(end_time.timestamp()),
            limit=limit,
        )

        # 결과 정리
        logs = []
        if result and "results" in result:
            for row in result["results"][:limit]:
                log_entry = {}
                for field in row:
                    log_entry[field.get("field", "unknown")] = field.get("value", "")
                logs.append(log_entry)

        return {
            "log_group": log_group,
            "time_range": f"{start_time.isoformat()} ~ {end_time.isoformat()}",
            "query": query,
            "logs": logs,
            "count": len(logs),
            "success": True,
        }

    except Exception as e:
        logger.error(f"CloudWatch Logs 쿼리 실패: {e}")
        return {
            "log_group": log_group,
            "error": str(e),
            "success": False,
        }


def create_cloudwatch_tools(aws_client: AWSClient) -> Dict[str, Callable]:
    """CloudWatch Tool 세트 생성."""

    def _get_metrics(**kwargs) -> Dict[str, Any]:
        return get_cloudwatch_metrics(aws_client, **kwargs)

    def _query_logs(**kwargs) -> Dict[str, Any]:
        return query_cloudwatch_logs(aws_client, **kwargs)

    return {
        "get_cloudwatch_metrics": _get_metrics,
        "query_cloudwatch_logs": _query_logs,
    }
