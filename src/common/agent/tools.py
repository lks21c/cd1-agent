"""
LangChain Tools for CD1 Agent.

Tool definitions for the ReAct agent workflow.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from src.common.services.aws_client import AWSClient, AWSProvider


# Global AWS client - will be injected or use mock
_aws_client: Optional[AWSClient] = None


def get_aws_client() -> AWSClient:
    """Get or create AWS client."""
    global _aws_client
    if _aws_client is None:
        _aws_client = AWSClient(provider=AWSProvider.MOCK)
    return _aws_client


def set_aws_client(client: AWSClient) -> None:
    """Set AWS client for dependency injection."""
    global _aws_client
    _aws_client = client


@tool
def get_cloudwatch_metrics(
    service_name: str,
    metric_name: str = "Errors",
    namespace: str = "AWS/Lambda",
    hours: int = 1,
) -> Dict[str, Any]:
    """
    Get CloudWatch metrics for a service.

    Args:
        service_name: Name of the service/function
        metric_name: CloudWatch metric name (default: Errors)
        namespace: CloudWatch namespace (default: AWS/Lambda)
        hours: Hours of data to retrieve (default: 1)

    Returns:
        Dictionary with metric data and statistics
    """
    client = get_aws_client()

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)

    result = client.get_cloudwatch_metrics(
        namespace=namespace,
        metric_name=metric_name,
        dimensions=[{"FunctionName": service_name}],
        start_time=start_time,
        end_time=end_time,
        period=300,
        statistic="Sum" if metric_name == "Errors" else "Average",
    )

    datapoints = result.get("datapoints", [])
    if not datapoints:
        return {
            "service_name": service_name,
            "metric_name": metric_name,
            "status": "no_data",
            "message": f"No {metric_name} data found for {service_name}",
        }

    values = [dp.get("Sum", dp.get("Average", 0)) for dp in datapoints]

    return {
        "service_name": service_name,
        "metric_name": metric_name,
        "namespace": namespace,
        "datapoints_count": len(datapoints),
        "latest_value": values[-1] if values else 0,
        "max_value": max(values) if values else 0,
        "min_value": min(values) if values else 0,
        "average": sum(values) / len(values) if values else 0,
        "time_range": f"{start_time.isoformat()} to {end_time.isoformat()}",
    }


@tool
def query_cloudwatch_logs(
    log_group: str,
    query: Optional[str] = None,
    hours: int = 1,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Query CloudWatch Logs for a log group.

    Args:
        log_group: CloudWatch Log Group name
        query: CloudWatch Logs Insights query (optional, defaults to error search)
        hours: Hours of logs to query (default: 1)
        limit: Maximum number of results (default: 100)

    Returns:
        Dictionary with log query results
    """
    client = get_aws_client()

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)

    if not query:
        query = """
        fields @timestamp, @message, @logStream
        | filter @message like /(?i)(error|exception|failed|timeout)/
        | sort @timestamp desc
        """

    results = client.query_cloudwatch_logs(
        log_group=log_group,
        query=query,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

    # Group by error type
    error_types: Dict[str, int] = {}
    for log in results:
        message = log.get("@message", "")
        if "timeout" in message.lower():
            error_types["timeout"] = error_types.get("timeout", 0) + 1
        elif "memory" in message.lower():
            error_types["memory"] = error_types.get("memory", 0) + 1
        elif "connection" in message.lower():
            error_types["connection"] = error_types.get("connection", 0) + 1
        else:
            error_types["other"] = error_types.get("other", 0) + 1

    return {
        "log_group": log_group,
        "total_results": len(results),
        "time_range": f"{start_time.isoformat()} to {end_time.isoformat()}",
        "error_breakdown": error_types,
        "sample_logs": results[:10],
    }


@tool
def search_knowledge_base(
    query: str,
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    Search the knowledge base for relevant documentation.

    Args:
        query: Search query describing the issue
        max_results: Maximum number of results to return

    Returns:
        Dictionary with knowledge base search results
    """
    client = get_aws_client()

    # Get knowledge base ID from environment or use default
    import os
    kb_id = os.getenv("KNOWLEDGE_BASE_ID", "mock-kb-id")

    results = client.retrieve_knowledge_base(
        knowledge_base_id=kb_id,
        query=query,
        max_results=max_results,
    )

    return {
        "query": query,
        "results_count": len(results),
        "results": [
            {
                "content": r.get("content", "")[:500],
                "score": r.get("score", 0),
                "source": r.get("metadata", {}).get("source", "unknown"),
            }
            for r in results
        ],
    }


@tool
def get_service_health(
    service_name: str,
) -> Dict[str, Any]:
    """
    Get overall health status of a service.

    Args:
        service_name: Name of the service to check

    Returns:
        Dictionary with service health information
    """
    client = get_aws_client()

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=1)

    # Get multiple metrics for health assessment
    metrics = {}

    for metric_name in ["Errors", "Invocations", "Duration", "Throttles"]:
        result = client.get_cloudwatch_metrics(
            namespace="AWS/Lambda",
            metric_name=metric_name,
            dimensions=[{"FunctionName": service_name}],
            start_time=start_time,
            end_time=end_time,
            period=300,
        )
        datapoints = result.get("datapoints", [])
        if datapoints:
            values = [dp.get("Sum", dp.get("Average", 0)) for dp in datapoints]
            metrics[metric_name.lower()] = {
                "latest": values[-1] if values else 0,
                "total": sum(values),
                "average": sum(values) / len(values),
            }

    # Calculate health score
    error_rate = 0
    if metrics.get("invocations", {}).get("total", 0) > 0:
        error_rate = (
            metrics.get("errors", {}).get("total", 0)
            / metrics["invocations"]["total"]
        )

    health_score = 1.0 - min(error_rate, 1.0)

    if health_score >= 0.99:
        status = "healthy"
    elif health_score >= 0.95:
        status = "degraded"
    else:
        status = "unhealthy"

    return {
        "service_name": service_name,
        "status": status,
        "health_score": health_score,
        "error_rate": error_rate,
        "metrics": metrics,
        "time_range": f"{start_time.isoformat()} to {end_time.isoformat()}",
    }


@tool
def analyze_error_pattern(
    error_messages: List[str],
) -> Dict[str, Any]:
    """
    Analyze a list of error messages for patterns.

    Args:
        error_messages: List of error messages to analyze

    Returns:
        Dictionary with pattern analysis results
    """
    if not error_messages:
        return {
            "status": "no_data",
            "message": "No error messages provided",
        }

    # Pattern categories
    patterns = {
        "timeout": [],
        "memory": [],
        "connection": [],
        "authentication": [],
        "rate_limit": [],
        "validation": [],
        "dependency": [],
        "unknown": [],
    }

    for msg in error_messages:
        msg_lower = msg.lower()

        categorized = False
        if "timeout" in msg_lower or "timed out" in msg_lower:
            patterns["timeout"].append(msg)
            categorized = True
        if "memory" in msg_lower or "oom" in msg_lower:
            patterns["memory"].append(msg)
            categorized = True
        if "connection" in msg_lower or "network" in msg_lower:
            patterns["connection"].append(msg)
            categorized = True
        if "auth" in msg_lower or "unauthorized" in msg_lower or "forbidden" in msg_lower:
            patterns["authentication"].append(msg)
            categorized = True
        if "rate" in msg_lower or "throttl" in msg_lower:
            patterns["rate_limit"].append(msg)
            categorized = True
        if "valid" in msg_lower or "invalid" in msg_lower:
            patterns["validation"].append(msg)
            categorized = True
        if "import" in msg_lower or "module" in msg_lower or "dependency" in msg_lower:
            patterns["dependency"].append(msg)
            categorized = True

        if not categorized:
            patterns["unknown"].append(msg)

    # Find dominant pattern
    pattern_counts = {k: len(v) for k, v in patterns.items() if v}
    dominant_pattern = max(pattern_counts, key=pattern_counts.get) if pattern_counts else "unknown"

    return {
        "total_errors": len(error_messages),
        "patterns": pattern_counts,
        "dominant_pattern": dominant_pattern,
        "dominant_count": pattern_counts.get(dominant_pattern, 0),
        "samples": {k: v[:3] for k, v in patterns.items() if v},
    }


@tool
def check_recent_deployments(
    service_name: str,
    hours: int = 24,
) -> Dict[str, Any]:
    """
    Check for recent deployments that might have caused issues.

    Args:
        service_name: Name of the service to check
        hours: Hours to look back for deployments

    Returns:
        Dictionary with deployment information
    """
    # In real implementation, would query deployment tracking system
    # For now, return mock data

    return {
        "service_name": service_name,
        "lookback_hours": hours,
        "deployments": [
            {
                "deployment_id": "deploy-001",
                "timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                "version": "v1.2.3",
                "status": "successful",
                "changes": ["Updated dependencies", "Fixed memory leak"],
            }
        ],
        "recent_changes": True,
        "recommendation": "Recent deployment detected. Consider if changes correlate with issue timing.",
    }


# List of all available tools
AGENT_TOOLS = [
    get_cloudwatch_metrics,
    query_cloudwatch_logs,
    search_knowledge_base,
    get_service_health,
    analyze_error_pattern,
    check_recent_deployments,
]
