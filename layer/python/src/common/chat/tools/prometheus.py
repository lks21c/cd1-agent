"""
Prometheus Tools - Kubernetes 모니터링 관련 Tool.

On-Prem K8s 환경의 Prometheus/VictoriaMetrics 연동.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Prometheus 엔드포인트 설정
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")


def get_prometheus_metrics(
    query: str = "up",
    time_range: str = "5m",
) -> Dict[str, Any]:
    """
    Prometheus PromQL 쿼리 실행.

    Args:
        query: PromQL 쿼리
        time_range: 시간 범위

    Returns:
        쿼리 결과
    """
    logger.info(f"Prometheus 쿼리: {query}")

    # TODO: 실제 Prometheus API 호출 구현
    # 현재는 Mock 데이터 반환

    mock_results = {
        "up": {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"job": "kubernetes-nodes"}, "value": [datetime.utcnow().timestamp(), "1"]},
                    {"metric": {"job": "kubernetes-pods"}, "value": [datetime.utcnow().timestamp(), "1"]},
                ]
            }
        },
        "kube_pod_status_phase": {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"namespace": "spark", "pod": "spark-executor-1", "phase": "Running"}, "value": [datetime.utcnow().timestamp(), "1"]},
                    {"metric": {"namespace": "spark", "pod": "spark-executor-2", "phase": "Running"}, "value": [datetime.utcnow().timestamp(), "1"]},
                    {"metric": {"namespace": "spark", "pod": "spark-driver", "phase": "Running"}, "value": [datetime.utcnow().timestamp(), "1"]},
                ]
            }
        },
    }

    # 쿼리에 맞는 Mock 데이터 반환
    for key, data in mock_results.items():
        if key in query:
            return {
                "query": query,
                "time_range": time_range,
                "result": data,
                "success": True,
            }

    return {
        "query": query,
        "time_range": time_range,
        "result": {"status": "success", "data": {"resultType": "vector", "result": []}},
        "success": True,
    }


def get_pod_status(
    namespace: str = "default",
    pod_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pod 상태 조회.

    Args:
        namespace: Kubernetes 네임스페이스
        pod_name: Pod 이름 (선택)

    Returns:
        Pod 상태 정보
    """
    logger.info(f"Pod 상태 조회: {namespace}/{pod_name or '*'}")

    # TODO: 실제 Prometheus/Kubernetes API 호출 구현
    # 현재는 Mock 데이터 반환

    mock_pods = [
        {
            "name": "spark-executor-1",
            "namespace": namespace,
            "status": "Running",
            "restarts": 0,
            "cpu_usage": "250m",
            "memory_usage": "2Gi",
            "memory_limit": "4Gi",
        },
        {
            "name": "spark-executor-2",
            "namespace": namespace,
            "status": "Running",
            "restarts": 0,
            "cpu_usage": "300m",
            "memory_usage": "2.5Gi",
            "memory_limit": "4Gi",
        },
        {
            "name": "spark-driver",
            "namespace": namespace,
            "status": "Running",
            "restarts": 1,
            "cpu_usage": "500m",
            "memory_usage": "3Gi",
            "memory_limit": "4Gi",
        },
    ]

    if pod_name:
        pods = [p for p in mock_pods if p["name"] == pod_name]
    else:
        pods = mock_pods

    # 상태 요약
    total = len(pods)
    running = len([p for p in pods if p["status"] == "Running"])
    issues = len([p for p in pods if p["restarts"] > 2 or p["status"] != "Running"])

    return {
        "namespace": namespace,
        "pods": pods,
        "summary": {
            "total": total,
            "running": running,
            "issues": issues,
        },
        "success": True,
    }


def get_node_status() -> Dict[str, Any]:
    """
    Node 상태 조회.

    Returns:
        Node 상태 정보
    """
    logger.info("Node 상태 조회")

    # TODO: 실제 Prometheus/Kubernetes API 호출 구현
    # 현재는 Mock 데이터 반환

    mock_nodes = [
        {
            "name": "node-1",
            "status": "Ready",
            "cpu_capacity": "8",
            "cpu_usage": "4.5",
            "memory_capacity": "32Gi",
            "memory_usage": "24Gi",
            "conditions": {
                "MemoryPressure": False,
                "DiskPressure": False,
                "PIDPressure": False,
            },
        },
        {
            "name": "node-2",
            "status": "Ready",
            "cpu_capacity": "8",
            "cpu_usage": "3.2",
            "memory_capacity": "32Gi",
            "memory_usage": "20Gi",
            "conditions": {
                "MemoryPressure": False,
                "DiskPressure": False,
                "PIDPressure": False,
            },
        },
    ]

    # 상태 요약
    total = len(mock_nodes)
    ready = len([n for n in mock_nodes if n["status"] == "Ready"])
    issues = len([n for n in mock_nodes if any(n["conditions"].values())])

    return {
        "nodes": mock_nodes,
        "summary": {
            "total": total,
            "ready": ready,
            "issues": issues,
        },
        "success": True,
    }


def create_prometheus_tools() -> Dict[str, Callable]:
    """Prometheus Tool 세트 생성."""

    return {
        "get_prometheus_metrics": get_prometheus_metrics,
        "get_pod_status": get_pod_status,
        "get_node_status": get_node_status,
    }
