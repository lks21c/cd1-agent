"""
RDS Data API Client with Provider Abstraction.

Supports real AWS RDS Data API and mock providers for testing.
Integrates with SchemaLoader for dynamic query generation.
"""

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import logging

from .schema_loader import (
    SchemaLoader,
    TableSchema,
    get_schema_loader,
    SchemaNotFoundError,
)

logger = logging.getLogger(__name__)


class RDSProvider(str, Enum):
    """Supported RDS provider modes."""

    REAL = "real"
    MOCK = "mock"


class QueryResult:
    """RDS query result wrapper."""

    def __init__(
        self,
        rows: List[Dict[str, Any]],
        column_names: List[str],
        row_count: int,
        execution_time_ms: float = 0.0,
    ):
        self.rows = rows
        self.column_names = column_names
        self.row_count = row_count
        self.execution_time_ms = execution_time_ms

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rows": self.rows,
            "column_names": self.column_names,
            "row_count": self.row_count,
            "execution_time_ms": self.execution_time_ms,
        }

    def to_markdown_table(self, max_rows: int = 20) -> str:
        """Format as markdown table."""
        if not self.rows:
            return "결과 없음"

        # Header
        header = "| " + " | ".join(self.column_names) + " |"
        separator = "| " + " | ".join(["---"] * len(self.column_names)) + " |"

        # Rows
        rows_str = []
        for row in self.rows[:max_rows]:
            values = [str(row.get(col, "")) for col in self.column_names]
            rows_str.append("| " + " | ".join(values) + " |")

        result = "\n".join([header, separator] + rows_str)

        if len(self.rows) > max_rows:
            result += f"\n\n... 외 {len(self.rows) - max_rows}개 행"

        return result


class BaseRDSProvider(ABC):
    """Abstract base class for RDS providers."""

    @abstractmethod
    def execute_query(
        self,
        sql: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        database: Optional[str] = None,
    ) -> QueryResult:
        """Execute SQL query."""
        pass

    @abstractmethod
    def execute_statement(
        self,
        sql: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute SQL statement (INSERT, UPDATE, DELETE)."""
        pass

    @abstractmethod
    def batch_execute(
        self,
        sql: str,
        parameter_sets: List[List[Dict[str, Any]]],
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute batch SQL statements."""
        pass


class RealRDSProvider(BaseRDSProvider):
    """Real RDS Data API provider using boto3."""

    def __init__(
        self,
        cluster_arn: str,
        secret_arn: str,
        database: Optional[str] = None,
        region: Optional[str] = None,
    ):
        import boto3

        self.cluster_arn = cluster_arn
        self.secret_arn = secret_arn
        self.default_database = database
        self.region = region or os.getenv("AWS_REGION", "ap-northeast-2")
        self._client = boto3.client("rds-data", region_name=self.region)

    def _format_parameters(
        self,
        parameters: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Format parameters for RDS Data API."""
        if not parameters:
            return []

        formatted = []
        for param in parameters:
            name = param.get("name")
            value = param.get("value")

            # Auto-detect type
            if isinstance(value, bool):
                formatted.append({"name": name, "value": {"booleanValue": value}})
            elif isinstance(value, int):
                formatted.append({"name": name, "value": {"longValue": value}})
            elif isinstance(value, float):
                formatted.append({"name": name, "value": {"doubleValue": value}})
            elif value is None:
                formatted.append({"name": name, "value": {"isNull": True}})
            else:
                formatted.append({"name": name, "value": {"stringValue": str(value)}})

        return formatted

    def _parse_response(
        self,
        response: Dict[str, Any],
    ) -> QueryResult:
        """Parse RDS Data API response."""
        columns = [col["name"] for col in response.get("columnMetadata", [])]

        rows = []
        for record in response.get("records", []):
            row = {}
            for i, field in enumerate(record):
                col_name = columns[i] if i < len(columns) else f"col_{i}"

                # Extract value from field
                if "isNull" in field and field["isNull"]:
                    row[col_name] = None
                elif "stringValue" in field:
                    row[col_name] = field["stringValue"]
                elif "longValue" in field:
                    row[col_name] = field["longValue"]
                elif "doubleValue" in field:
                    row[col_name] = field["doubleValue"]
                elif "booleanValue" in field:
                    row[col_name] = field["booleanValue"]
                elif "blobValue" in field:
                    row[col_name] = field["blobValue"]
                else:
                    row[col_name] = str(field)

            rows.append(row)

        return QueryResult(
            rows=rows,
            column_names=columns,
            row_count=len(rows),
        )

    def execute_query(
        self,
        sql: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        database: Optional[str] = None,
    ) -> QueryResult:
        """Execute SQL query."""
        import time

        start_time = time.time()

        params = {
            "resourceArn": self.cluster_arn,
            "secretArn": self.secret_arn,
            "sql": sql,
            "includeResultMetadata": True,
        }

        db = database or self.default_database
        if db:
            params["database"] = db

        formatted_params = self._format_parameters(parameters)
        if formatted_params:
            params["parameters"] = formatted_params

        response = self._client.execute_statement(**params)

        result = self._parse_response(response)
        result.execution_time_ms = (time.time() - start_time) * 1000

        return result

    def execute_statement(
        self,
        sql: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute SQL statement."""
        params = {
            "resourceArn": self.cluster_arn,
            "secretArn": self.secret_arn,
            "sql": sql,
        }

        db = database or self.default_database
        if db:
            params["database"] = db

        formatted_params = self._format_parameters(parameters)
        if formatted_params:
            params["parameters"] = formatted_params

        response = self._client.execute_statement(**params)

        return {
            "number_of_records_updated": response.get("numberOfRecordsUpdated", 0),
            "generated_fields": response.get("generatedFields", []),
        }

    def batch_execute(
        self,
        sql: str,
        parameter_sets: List[List[Dict[str, Any]]],
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute batch SQL statements."""
        params = {
            "resourceArn": self.cluster_arn,
            "secretArn": self.secret_arn,
            "sql": sql,
            "parameterSets": [
                self._format_parameters(ps) for ps in parameter_sets
            ],
        }

        db = database or self.default_database
        if db:
            params["database"] = db

        response = self._client.batch_execute_statement(**params)

        return {
            "update_results": response.get("updateResults", []),
        }


class MockRDSProvider(BaseRDSProvider):
    """Mock RDS provider for testing."""

    def __init__(self):
        self._mock_data: Dict[str, List[Dict[str, Any]]] = {}
        self._setup_default_mock_data()
        self.call_history: List[Dict[str, Any]] = []

    def _setup_default_mock_data(self):
        """Setup default mock data."""
        now = datetime.now()

        # Mock anomaly_logs
        self._mock_data["anomaly_logs"] = [
            {
                "id": 1,
                "timestamp": (now - timedelta(hours=2)).isoformat(),
                "service_name": "api-gateway",
                "anomaly_type": "ERROR_SPIKE",
                "severity": "HIGH",
                "source": "CLOUDWATCH",
                "message": "Error rate increased to 15%",
                "resolved": False,
            },
            {
                "id": 2,
                "timestamp": (now - timedelta(hours=1)).isoformat(),
                "service_name": "payment-service",
                "anomaly_type": "LATENCY",
                "severity": "MEDIUM",
                "source": "PROMETHEUS",
                "message": "P99 latency exceeded 2s",
                "resolved": False,
            },
            {
                "id": 3,
                "timestamp": (now - timedelta(days=1)).isoformat(),
                "service_name": "order-service",
                "anomaly_type": "RESOURCE_EXHAUSTION",
                "severity": "CRITICAL",
                "source": "CLOUDWATCH",
                "message": "Memory usage at 95%",
                "resolved": True,
                "resolved_at": (now - timedelta(hours=20)).isoformat(),
            },
        ]

        # Mock service_metrics
        self._mock_data["service_metrics"] = [
            {
                "id": 1,
                "timestamp": now.isoformat(),
                "service_name": "api-gateway",
                "metric_name": "cpu_utilization",
                "metric_value": 45.5,
                "metric_unit": "percent",
                "source": "CLOUDWATCH",
            },
            {
                "id": 2,
                "timestamp": now.isoformat(),
                "service_name": "api-gateway",
                "metric_name": "memory_usage",
                "metric_value": 2147483648,
                "metric_unit": "bytes",
                "source": "CLOUDWATCH",
            },
        ]

        # Mock remediation_history
        self._mock_data["remediation_history"] = [
            {
                "id": 1,
                "anomaly_id": 3,
                "timestamp": (now - timedelta(hours=20)).isoformat(),
                "action_type": "LAMBDA_RESTART",
                "action_target": "arn:aws:lambda:ap-northeast-2:123456789:function:order-service",
                "status": "EXECUTED",
                "approved_by": "ops@company.com",
                "confidence_score": 0.85,
                "analysis_summary": "메모리 누수로 인한 리소스 고갈. Lambda 재시작으로 해결.",
            },
        ]

    def set_mock_data(self, table_name: str, data: List[Dict[str, Any]]):
        """Set mock data for a table."""
        self._mock_data[table_name] = data

    def add_mock_record(self, table_name: str, record: Dict[str, Any]):
        """Add a mock record to a table."""
        if table_name not in self._mock_data:
            self._mock_data[table_name] = []
        self._mock_data[table_name].append(record)

    def _record_call(self, method: str, **kwargs):
        """Record method call for verification."""
        self.call_history.append({"method": method, **kwargs})

    def _parse_simple_query(self, sql: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Parse simple SELECT query to extract table and conditions."""
        import re

        sql_lower = sql.lower().strip()

        # Extract table name
        table_match = re.search(r'from\s+(\w+)', sql_lower)
        table_name = table_match.group(1) if table_match else None

        # Extract simple WHERE conditions
        conditions = {}
        where_match = re.search(r'where\s+(.+?)(?:order|limit|$)', sql_lower, re.DOTALL)
        if where_match:
            where_clause = where_match.group(1)
            # Parse simple conditions like "column = 'value'" or "column = :param"
            cond_matches = re.findall(r'(\w+)\s*=\s*[\'"]?(\w+)[\'"]?', where_clause)
            for col, val in cond_matches:
                conditions[col] = val

        return table_name, conditions if conditions else None

    def _filter_data(
        self,
        data: List[Dict[str, Any]],
        conditions: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter data based on conditions."""
        if not conditions:
            return data

        filtered = []
        for row in data:
            match = True
            for col, val in conditions.items():
                row_val = str(row.get(col, "")).lower()
                if row_val != str(val).lower():
                    match = False
                    break
            if match:
                filtered.append(row)

        return filtered

    def execute_query(
        self,
        sql: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        database: Optional[str] = None,
    ) -> QueryResult:
        """Execute SQL query (mock)."""
        self._record_call("execute_query", sql=sql, parameters=parameters, database=database)

        table_name, conditions = self._parse_simple_query(sql)

        if not table_name or table_name not in self._mock_data:
            logger.warning(f"Mock data not found for table: {table_name}")
            return QueryResult(rows=[], column_names=[], row_count=0)

        data = self._mock_data[table_name]
        filtered = self._filter_data(data, conditions)

        # Extract column names from first row
        column_names = list(filtered[0].keys()) if filtered else []

        return QueryResult(
            rows=filtered,
            column_names=column_names,
            row_count=len(filtered),
            execution_time_ms=5.0,  # Mock execution time
        )

    def execute_statement(
        self,
        sql: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute SQL statement (mock)."""
        self._record_call("execute_statement", sql=sql, parameters=parameters, database=database)

        return {
            "number_of_records_updated": 1,
            "generated_fields": [{"longValue": 100}],
        }

    def batch_execute(
        self,
        sql: str,
        parameter_sets: List[List[Dict[str, Any]]],
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute batch SQL statements (mock)."""
        self._record_call("batch_execute", sql=sql, parameter_sets=parameter_sets, database=database)

        return {
            "update_results": [{"generatedFields": []} for _ in parameter_sets],
        }


class RDSClient:
    """
    RDS Data API client with schema integration.

    Usage:
        # Mock for testing
        client = RDSClient(provider=RDSProvider.MOCK)

        # Real AWS
        client = RDSClient(
            provider=RDSProvider.REAL,
            cluster_arn="arn:aws:rds:...",
            secret_arn="arn:aws:secretsmanager:...",
        )

        # Execute query
        result = client.query("SELECT * FROM anomaly_logs WHERE severity = :severity", [
            {"name": "severity", "value": "HIGH"}
        ])

        # Schema-aware query
        result = client.query_table(
            "anomaly_logs",
            columns=["id", "service_name", "severity"],
            where={"severity": "HIGH"},
            limit=10,
        )
    """

    def __init__(
        self,
        provider: RDSProvider = RDSProvider.MOCK,
        cluster_arn: Optional[str] = None,
        secret_arn: Optional[str] = None,
        database: Optional[str] = None,
        region: Optional[str] = None,
        schema_loader: Optional[SchemaLoader] = None,
    ):
        self.provider_type = provider
        self._schema_loader = schema_loader or get_schema_loader()

        if provider == RDSProvider.REAL:
            if not cluster_arn or not secret_arn:
                cluster_arn = cluster_arn or os.getenv("RDS_CLUSTER_ARN")
                secret_arn = secret_arn or os.getenv("RDS_SECRET_ARN")

                if not cluster_arn or not secret_arn:
                    raise ValueError(
                        "cluster_arn and secret_arn are required for REAL provider. "
                        "Set RDS_CLUSTER_ARN and RDS_SECRET_ARN environment variables."
                    )

            self._provider = RealRDSProvider(
                cluster_arn=cluster_arn,
                secret_arn=secret_arn,
                database=database or os.getenv("RDS_DATABASE"),
                region=region,
            )
            logger.info("Using Real RDS Provider")
        else:
            self._provider = MockRDSProvider()
            logger.info("Using Mock RDS Provider")

    @property
    def schema_loader(self) -> SchemaLoader:
        """Get schema loader."""
        return self._schema_loader

    def query(
        self,
        sql: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        database: Optional[str] = None,
    ) -> QueryResult:
        """
        Execute raw SQL query.

        Args:
            sql: SQL query string
            parameters: Query parameters (list of {"name": str, "value": Any})
            database: Optional database name

        Returns:
            QueryResult object
        """
        return self._provider.execute_query(sql, parameters, database)

    def execute(
        self,
        sql: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute SQL statement (INSERT, UPDATE, DELETE).

        Args:
            sql: SQL statement
            parameters: Statement parameters
            database: Optional database name

        Returns:
            Execution result
        """
        return self._provider.execute_statement(sql, parameters, database)

    def query_table(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult:
        """
        Execute schema-aware table query.

        Args:
            table_name: Table name
            columns: Columns to select (None for all)
            where: WHERE conditions as dict
            order_by: Column to order by
            order_desc: Descending order
            limit: Result limit
            offset: Result offset

        Returns:
            QueryResult object
        """
        # Validate table exists
        try:
            schema = self._schema_loader.load_table(table_name)
        except SchemaNotFoundError:
            logger.warning(f"Schema not found for table: {table_name}, proceeding without validation")
            schema = None

        # Build column list
        if columns:
            cols_str = ", ".join(columns)
        else:
            cols_str = "*"

        # Build SQL
        sql = f"SELECT {cols_str} FROM {table_name}"
        parameters = []

        # WHERE clause
        if where:
            conditions = []
            for col, val in where.items():
                param_name = f"p_{col}"
                conditions.append(f"{col} = :{param_name}")
                parameters.append({"name": param_name, "value": val})
            sql += " WHERE " + " AND ".join(conditions)

        # ORDER BY
        if order_by:
            sql += f" ORDER BY {order_by}"
            if order_desc:
                sql += " DESC"

        # LIMIT / OFFSET
        sql += f" LIMIT {limit}"
        if offset > 0:
            sql += f" OFFSET {offset}"

        return self.query(sql, parameters if parameters else None)

    def get_recent_anomalies(
        self,
        service_name: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 20,
    ) -> QueryResult:
        """
        Get recent anomalies (convenience method).

        Args:
            service_name: Filter by service name
            severity: Filter by severity (LOW, MEDIUM, HIGH, CRITICAL)
            limit: Result limit

        Returns:
            QueryResult object
        """
        where = {}
        if service_name:
            where["service_name"] = service_name
        if severity:
            where["severity"] = severity

        return self.query_table(
            "anomaly_logs",
            columns=["id", "timestamp", "service_name", "anomaly_type", "severity", "message", "resolved"],
            where=where if where else None,
            order_by="timestamp",
            order_desc=True,
            limit=limit,
        )

    def get_service_metrics(
        self,
        service_name: str,
        metric_name: Optional[str] = None,
        limit: int = 50,
    ) -> QueryResult:
        """
        Get service metrics (convenience method).

        Args:
            service_name: Service name
            metric_name: Optional metric name filter
            limit: Result limit

        Returns:
            QueryResult object
        """
        where = {"service_name": service_name}
        if metric_name:
            where["metric_name"] = metric_name

        return self.query_table(
            "service_metrics",
            where=where,
            order_by="timestamp",
            order_desc=True,
            limit=limit,
        )

    def get_remediation_history(
        self,
        anomaly_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> QueryResult:
        """
        Get remediation history (convenience method).

        Args:
            anomaly_id: Filter by anomaly ID
            status: Filter by status
            limit: Result limit

        Returns:
            QueryResult object
        """
        where = {}
        if anomaly_id:
            where["anomaly_id"] = anomaly_id
        if status:
            where["status"] = status

        return self.query_table(
            "remediation_history",
            where=where if where else None,
            order_by="timestamp",
            order_desc=True,
            limit=limit,
        )

    @property
    def call_history(self) -> List[Dict[str, Any]]:
        """Get call history (only available for mock provider)."""
        if isinstance(self._provider, MockRDSProvider):
            return self._provider.call_history
        return []


# Module-level convenience function
def get_rds_client(
    provider: Optional[RDSProvider] = None,
    **kwargs,
) -> RDSClient:
    """
    Get RDS client instance.

    Auto-detects provider from environment if not specified.

    Args:
        provider: RDS provider (REAL or MOCK)
        **kwargs: Additional arguments for RDSClient

    Returns:
        RDSClient instance
    """
    if provider is None:
        if os.getenv("RDS_MOCK", "").lower() == "true":
            provider = RDSProvider.MOCK
        elif os.getenv("AWS_MOCK", "").lower() == "true":
            provider = RDSProvider.MOCK
        elif os.getenv("RDS_CLUSTER_ARN"):
            provider = RDSProvider.REAL
        else:
            provider = RDSProvider.MOCK

    return RDSClient(provider=provider, **kwargs)


if __name__ == "__main__":
    # Test mock provider
    client = RDSClient(provider=RDSProvider.MOCK)

    print("=== Recent Anomalies ===")
    result = client.get_recent_anomalies()
    print(result.to_markdown_table())

    print("\n=== High Severity Anomalies ===")
    result = client.get_recent_anomalies(severity="HIGH")
    print(result.to_markdown_table())

    print("\n=== Remediation History ===")
    result = client.get_remediation_history()
    print(result.to_markdown_table())

    print("\n=== Custom Query ===")
    result = client.query("SELECT * FROM anomaly_logs WHERE severity = :severity", [
        {"name": "severity", "value": "CRITICAL"}
    ])
    print(result.to_markdown_table())
