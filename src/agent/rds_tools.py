"""
RDS Tools for BDP Agent.

LangChain tool definitions for querying RDS via Data API.
Supports schema-aware dynamic query generation.
"""

from typing import Any, Dict, List, Optional
from langchain_core.tools import tool

from src.services.rds_client import RDSClient, RDSProvider, get_rds_client as _get_rds_client


# Global RDS client - will be injected or use mock
_rds_client: Optional[RDSClient] = None


def get_rds_client() -> RDSClient:
    """Get or create RDS client."""
    global _rds_client
    if _rds_client is None:
        _rds_client = _get_rds_client()
    return _rds_client


def set_rds_client(client: RDSClient) -> None:
    """Set RDS client for dependency injection."""
    global _rds_client
    _rds_client = client


@tool
def query_rds_anomalies(
    service_name: Optional[str] = None,
    severity: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    RDS에서 이상 징후 로그를 조회합니다.

    Args:
        service_name: 서비스명으로 필터링 (예: api-gateway, payment-service)
        severity: 심각도로 필터링 (LOW, MEDIUM, HIGH, CRITICAL)
        anomaly_type: 이상 유형으로 필터링 (ERROR_SPIKE, LATENCY, RESOURCE_EXHAUSTION, TRAFFIC_SPIKE)
        resolved: 해결 여부로 필터링 (True=해결됨, False=미해결)
        limit: 최대 결과 수 (기본: 20)

    Returns:
        이상 징후 로그 목록과 요약 정보
    """
    client = get_rds_client()

    # Build WHERE conditions
    where = {}
    if service_name:
        where["service_name"] = service_name
    if severity:
        where["severity"] = severity.upper()
    if anomaly_type:
        where["anomaly_type"] = anomaly_type.upper()
    if resolved is not None:
        where["resolved"] = resolved

    result = client.query_table(
        "anomaly_logs",
        columns=[
            "id", "timestamp", "service_name", "anomaly_type",
            "severity", "source", "message", "resolved"
        ],
        where=where if where else None,
        order_by="timestamp",
        order_desc=True,
        limit=limit,
    )

    # Aggregate statistics
    severity_counts = {}
    type_counts = {}
    service_counts = {}

    for row in result.rows:
        sev = row.get("severity", "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

        atype = row.get("anomaly_type", "UNKNOWN")
        type_counts[atype] = type_counts.get(atype, 0) + 1

        svc = row.get("service_name", "UNKNOWN")
        service_counts[svc] = service_counts.get(svc, 0) + 1

    return {
        "total_count": result.row_count,
        "filters_applied": where,
        "severity_breakdown": severity_counts,
        "type_breakdown": type_counts,
        "service_breakdown": service_counts,
        "anomalies": result.rows,
        "markdown_table": result.to_markdown_table(max_rows=10),
    }


@tool
def query_rds_metrics(
    service_name: str,
    metric_name: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    RDS에서 서비스 메트릭을 조회합니다.

    Args:
        service_name: 서비스명 (필수)
        metric_name: 메트릭 이름으로 필터링 (cpu_utilization, memory_usage, request_count, error_rate)
        limit: 최대 결과 수 (기본: 50)

    Returns:
        서비스 메트릭 시계열 데이터
    """
    client = get_rds_client()

    result = client.get_service_metrics(
        service_name=service_name,
        metric_name=metric_name,
        limit=limit,
    )

    # Group by metric name for summary
    metrics_summary = {}
    for row in result.rows:
        m_name = row.get("metric_name", "unknown")
        m_value = row.get("metric_value", 0)

        if m_name not in metrics_summary:
            metrics_summary[m_name] = {
                "values": [],
                "unit": row.get("metric_unit", ""),
            }
        metrics_summary[m_name]["values"].append(float(m_value))

    # Calculate statistics
    for m_name, m_data in metrics_summary.items():
        values = m_data["values"]
        if values:
            m_data["latest"] = values[0]
            m_data["min"] = min(values)
            m_data["max"] = max(values)
            m_data["avg"] = sum(values) / len(values)
            m_data["count"] = len(values)

    return {
        "service_name": service_name,
        "total_datapoints": result.row_count,
        "metrics_summary": metrics_summary,
        "raw_data": result.rows[:20],  # Limit raw data
        "markdown_table": result.to_markdown_table(max_rows=10),
    }


@tool
def query_rds_remediation_history(
    anomaly_id: Optional[int] = None,
    status: Optional[str] = None,
    action_type: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    RDS에서 복구 조치 이력을 조회합니다.

    Args:
        anomaly_id: 특정 이상 징후 ID로 필터링
        status: 상태로 필터링 (PENDING, APPROVED, EXECUTED, FAILED, REJECTED)
        action_type: 조치 유형으로 필터링 (LAMBDA_RESTART, RDS_PARAMETER, AUTO_SCALING, NOTIFY, ESCALATE)
        limit: 최대 결과 수 (기본: 20)

    Returns:
        복구 조치 이력 목록
    """
    client = get_rds_client()

    where = {}
    if anomaly_id:
        where["anomaly_id"] = anomaly_id
    if status:
        where["status"] = status.upper()
    if action_type:
        where["action_type"] = action_type.upper()

    result = client.query_table(
        "remediation_history",
        columns=[
            "id", "anomaly_id", "timestamp", "action_type", "action_target",
            "status", "approved_by", "confidence_score", "analysis_summary"
        ],
        where=where if where else None,
        order_by="timestamp",
        order_desc=True,
        limit=limit,
    )

    # Status breakdown
    status_counts = {}
    action_counts = {}

    for row in result.rows:
        s = row.get("status", "UNKNOWN")
        status_counts[s] = status_counts.get(s, 0) + 1

        a = row.get("action_type", "UNKNOWN")
        action_counts[a] = action_counts.get(a, 0) + 1

    return {
        "total_count": result.row_count,
        "filters_applied": where,
        "status_breakdown": status_counts,
        "action_breakdown": action_counts,
        "history": result.rows,
        "markdown_table": result.to_markdown_table(max_rows=10),
    }


@tool
def execute_rds_query(
    sql_query: str,
    parameters: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    커스텀 SQL 쿼리를 실행합니다.

    주의: SELECT 쿼리만 허용됩니다. INSERT/UPDATE/DELETE는 거부됩니다.

    Args:
        sql_query: 실행할 SQL SELECT 쿼리
        parameters: 쿼리 파라미터 (예: [{"name": "severity", "value": "HIGH"}])

    Returns:
        쿼리 실행 결과
    """
    # Safety check: Only allow SELECT queries
    sql_upper = sql_query.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return {
            "error": True,
            "message": "보안상 SELECT 쿼리만 허용됩니다. INSERT, UPDATE, DELETE는 실행할 수 없습니다.",
            "query": sql_query,
        }

    # Block dangerous keywords
    dangerous_keywords = ["DROP", "TRUNCATE", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "GRANT", "REVOKE"]
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            return {
                "error": True,
                "message": f"보안상 '{keyword}' 키워드가 포함된 쿼리는 실행할 수 없습니다.",
                "query": sql_query,
            }

    client = get_rds_client()

    try:
        result = client.query(sql_query, parameters)
        return {
            "error": False,
            "row_count": result.row_count,
            "columns": result.column_names,
            "execution_time_ms": result.execution_time_ms,
            "rows": result.rows,
            "markdown_table": result.to_markdown_table(max_rows=20),
        }
    except Exception as e:
        return {
            "error": True,
            "message": f"쿼리 실행 실패: {str(e)}",
            "query": sql_query,
        }


@tool
def get_rds_schema_info(
    table_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    RDS 테이블 스키마 정보를 조회합니다.
    LLM이 쿼리 생성에 참고할 수 있는 컬럼 정보와 설명을 제공합니다.

    Args:
        table_name: 특정 테이블명 (없으면 전체 테이블 목록 반환)

    Returns:
        스키마 정보 (테이블 목록 또는 특정 테이블의 컬럼 정보)
    """
    client = get_rds_client()
    schema_loader = client.schema_loader

    if table_name:
        try:
            schema = schema_loader.load_table(table_name)
            return {
                "table_name": schema.table_name,
                "description": schema.description,
                "columns": [
                    {
                        "name": col.name,
                        "type": col.type,
                        "nullable": col.nullable,
                        "primary_key": col.primary_key,
                        "description": col.description,
                    }
                    for col in schema.columns
                ],
                "indexes": [
                    {"name": idx.name, "columns": idx.columns, "type": idx.type}
                    for idx in schema.indexes
                ],
                "llm_context": schema.to_prompt_context(),
            }
        except Exception as e:
            return {
                "error": True,
                "message": f"스키마 로드 실패: {str(e)}",
                "table_name": table_name,
            }
    else:
        # List all available tables
        tables = schema_loader.list_tables()
        schemas = {}

        for t in tables:
            try:
                s = schema_loader.load_table(t)
                schemas[t] = {
                    "description": s.description,
                    "column_count": len(s.columns),
                    "columns": s.get_column_names(),
                }
            except Exception:
                schemas[t] = {"error": "로드 실패"}

        return {
            "available_tables": tables,
            "table_count": len(tables),
            "schemas": schemas,
            "llm_context": schema_loader.get_llm_context(),
        }


# List of RDS tools
RDS_TOOLS = [
    query_rds_anomalies,
    query_rds_metrics,
    query_rds_remediation_history,
    execute_rds_query,
    get_rds_schema_info,
]
