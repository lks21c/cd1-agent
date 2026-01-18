"""
RDS Tools for Chat Agent.

대화형 에이전트에서 RDS 데이터를 조회하기 위한 Tool 래퍼.
자연어 쿼리를 스키마 기반 SQL로 변환하여 실행.
"""

from typing import Any, Callable, Dict, List, Optional

from langchain_core.tools import tool

from src.common.services.rds_client import RDSClient, RDSProvider


def create_rds_tools(rds_client: Optional[RDSClient] = None) -> Dict[str, Callable]:
    """
    Chat 에이전트용 RDS Tool 세트 생성.

    Args:
        rds_client: RDS 클라이언트 (없으면 Mock 생성)

    Returns:
        Tool 딕셔너리
    """
    if rds_client is None:
        rds_client = RDSClient(provider=RDSProvider.MOCK)

    @tool
    def query_anomalies(
        service_name: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """
        최근 이상 징후를 조회합니다.

        Args:
            service_name: 서비스명으로 필터 (선택)
            severity: 심각도로 필터 - LOW, MEDIUM, HIGH, CRITICAL (선택)
            limit: 조회할 최대 건수 (기본: 10)

        Returns:
            이상 징후 목록 (마크다운 테이블)
        """
        where = {}
        if service_name:
            where["service_name"] = service_name
        if severity:
            where["severity"] = severity.upper()

        result = rds_client.query_table(
            "anomaly_logs",
            columns=["id", "timestamp", "service_name", "anomaly_type", "severity", "message", "resolved"],
            where=where if where else None,
            order_by="timestamp",
            order_desc=True,
            limit=limit,
        )

        if result.row_count == 0:
            filters = ", ".join([f"{k}={v}" for k, v in where.items()]) if where else "없음"
            return f"조건({filters})에 해당하는 이상 징후가 없습니다."

        # Summary
        summary_lines = [
            f"**총 {result.row_count}건의 이상 징후**",
            "",
        ]

        # Severity breakdown
        severity_counts = {}
        for row in result.rows:
            sev = row.get("severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        if severity_counts:
            sev_str = ", ".join([f"{k}: {v}건" for k, v in sorted(severity_counts.items())])
            summary_lines.append(f"심각도별: {sev_str}")
            summary_lines.append("")

        summary_lines.append(result.to_markdown_table(max_rows=limit))

        return "\n".join(summary_lines)

    @tool
    def query_metrics(
        service_name: str,
        metric_name: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """
        서비스의 메트릭 데이터를 조회합니다.

        Args:
            service_name: 조회할 서비스명 (필수)
            metric_name: 메트릭 이름 - cpu_utilization, memory_usage, request_count, error_rate (선택)
            limit: 조회할 최대 건수 (기본: 20)

        Returns:
            메트릭 데이터 (요약 및 테이블)
        """
        result = rds_client.get_service_metrics(
            service_name=service_name,
            metric_name=metric_name,
            limit=limit,
        )

        if result.row_count == 0:
            return f"'{service_name}' 서비스의 메트릭 데이터가 없습니다."

        # Group by metric for summary
        metrics_data: Dict[str, List[float]] = {}
        units: Dict[str, str] = {}

        for row in result.rows:
            m_name = row.get("metric_name", "unknown")
            m_value = float(row.get("metric_value", 0))
            m_unit = row.get("metric_unit", "")

            if m_name not in metrics_data:
                metrics_data[m_name] = []
                units[m_name] = m_unit
            metrics_data[m_name].append(m_value)

        # Build summary
        lines = [
            f"**{service_name} 메트릭 요약**",
            "",
        ]

        for m_name, values in metrics_data.items():
            unit = units.get(m_name, "")
            latest = values[0]
            avg = sum(values) / len(values)
            max_val = max(values)

            lines.append(f"- **{m_name}**: 최신={latest:.2f}{unit}, 평균={avg:.2f}{unit}, 최대={max_val:.2f}{unit}")

        lines.append("")
        lines.append(result.to_markdown_table(max_rows=10))

        return "\n".join(lines)

    @tool
    def query_remediation_history(
        anomaly_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """
        복구 조치 이력을 조회합니다.

        Args:
            anomaly_id: 특정 이상 징후 ID로 필터 (선택)
            status: 상태로 필터 - PENDING, APPROVED, EXECUTED, FAILED, REJECTED (선택)
            limit: 조회할 최대 건수 (기본: 10)

        Returns:
            조치 이력 목록 (마크다운 테이블)
        """
        result = rds_client.get_remediation_history(
            anomaly_id=anomaly_id,
            status=status,
            limit=limit,
        )

        if result.row_count == 0:
            return "조건에 해당하는 조치 이력이 없습니다."

        # Status breakdown
        status_counts = {}
        for row in result.rows:
            s = row.get("status", "UNKNOWN")
            status_counts[s] = status_counts.get(s, 0) + 1

        lines = [
            f"**총 {result.row_count}건의 조치 이력**",
            "",
        ]

        if status_counts:
            status_str = ", ".join([f"{k}: {v}건" for k, v in sorted(status_counts.items())])
            lines.append(f"상태별: {status_str}")
            lines.append("")

        lines.append(result.to_markdown_table(max_rows=limit))

        return "\n".join(lines)

    @tool
    def get_schema_info(
        table_name: Optional[str] = None,
    ) -> str:
        """
        데이터베이스 스키마 정보를 조회합니다.
        테이블 구조와 컬럼 정보를 확인할 수 있습니다.

        Args:
            table_name: 특정 테이블명 (없으면 전체 테이블 목록)

        Returns:
            스키마 정보
        """
        schema_loader = rds_client.schema_loader

        if table_name:
            try:
                schema = schema_loader.load_table(table_name)
                return schema.to_prompt_context()
            except Exception as e:
                return f"'{table_name}' 테이블 스키마 로드 실패: {str(e)}"
        else:
            return schema_loader.get_llm_context()

    @tool
    def execute_custom_query(
        sql_query: str,
    ) -> str:
        """
        커스텀 SQL SELECT 쿼리를 실행합니다.
        주의: 읽기 전용 쿼리만 허용됩니다.

        Args:
            sql_query: 실행할 SELECT 쿼리

        Returns:
            쿼리 결과 (마크다운 테이블)
        """
        # Safety check
        sql_upper = sql_query.strip().upper()
        if not sql_upper.startswith("SELECT"):
            return "❌ 보안상 SELECT 쿼리만 허용됩니다."

        dangerous = ["DROP", "TRUNCATE", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE"]
        for keyword in dangerous:
            if keyword in sql_upper:
                return f"❌ 보안상 '{keyword}' 키워드가 포함된 쿼리는 실행할 수 없습니다."

        try:
            result = rds_client.query(sql_query)

            if result.row_count == 0:
                return "쿼리 결과가 없습니다."

            lines = [
                f"**{result.row_count}건 조회됨** (실행시간: {result.execution_time_ms:.1f}ms)",
                "",
                result.to_markdown_table(max_rows=20),
            ]

            return "\n".join(lines)

        except Exception as e:
            return f"❌ 쿼리 실행 실패: {str(e)}"

    return {
        "query_anomalies": query_anomalies,
        "query_metrics": query_metrics,
        "query_remediation_history": query_remediation_history,
        "get_schema_info": get_schema_info,
        "execute_custom_query": execute_custom_query,
    }


# Convenience functions for direct import
def query_anomalies(
    rds_client: RDSClient,
    service_name: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 10,
) -> str:
    """이상 징후 조회 (직접 호출용)."""
    tools = create_rds_tools(rds_client)
    return tools["query_anomalies"].func(
        service_name=service_name,
        severity=severity,
        limit=limit,
    )


def query_metrics(
    rds_client: RDSClient,
    service_name: str,
    metric_name: Optional[str] = None,
    limit: int = 20,
) -> str:
    """메트릭 조회 (직접 호출용)."""
    tools = create_rds_tools(rds_client)
    return tools["query_metrics"].func(
        service_name=service_name,
        metric_name=metric_name,
        limit=limit,
    )
