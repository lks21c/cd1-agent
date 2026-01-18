"""
Detection Pattern Service for RDS-based Pattern Detection.

Loads and executes detection patterns from RDS database.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    import pymysql
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


class PatternType(str, Enum):
    """Types of detection patterns."""
    SQL = "SQL"
    METRIC = "METRIC"
    REGEX = "REGEX"


@dataclass
class DetectionPattern:
    """Detection pattern definition from RDS."""
    id: int
    pattern_name: str
    pattern_type: PatternType
    target_service: Optional[str]
    query_template: str
    threshold_config: Dict[str, Any]
    severity: str
    enabled: bool = True
    created_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "DetectionPattern":
        """Create from database row."""
        return cls(
            id=row["id"],
            pattern_name=row["pattern_name"],
            pattern_type=PatternType(row["pattern_type"]),
            target_service=row.get("target_service"),
            query_template=row["query_template"],
            threshold_config=row.get("threshold_config", {}),
            severity=row["severity"],
            enabled=row.get("enabled", True),
            created_at=row.get("created_at"),
        )


@dataclass
class PatternExecutionResult:
    """Result of pattern execution."""
    pattern: DetectionPattern
    is_anomaly: bool
    current_value: Optional[float] = None
    threshold_value: Optional[float] = None
    matched_data: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def signature(self) -> str:
        """Generate unique signature for this result."""
        return f"pattern_{self.pattern.pattern_name}_{self.timestamp[:10]}"


class DetectionPatternService:
    """Service for loading and executing detection patterns from RDS."""

    def __init__(
        self,
        rds_host: Optional[str] = None,
        rds_port: int = 3306,
        rds_database: Optional[str] = None,
        rds_user: Optional[str] = None,
        rds_password: Optional[str] = None,
        use_mock: bool = False,
    ):
        """Initialize the detection pattern service.

        Args:
            rds_host: RDS hostname
            rds_port: RDS port (default: 3306)
            rds_database: Database name
            rds_user: Database username
            rds_password: Database password
            use_mock: Use mock data instead of real RDS connection
        """
        self.rds_host = rds_host or os.getenv("RDS_HOST")
        self.rds_port = rds_port or int(os.getenv("RDS_PORT", "3306"))
        self.rds_database = rds_database or os.getenv("RDS_DATABASE", "cd1_agent")
        self.rds_user = rds_user or os.getenv("RDS_USER")
        self.rds_password = rds_password or os.getenv("RDS_PASSWORD")
        self.use_mock = use_mock or os.getenv("RDS_PROVIDER", "").lower() == "mock"

        self._connection = None

    def _get_connection(self):
        """Get or create database connection."""
        if self.use_mock:
            return None

        if not PYMYSQL_AVAILABLE:
            raise ImportError("pymysql is required for RDS connection. Install with: pip install pymysql")

        if self._connection is None or not self._connection.open:
            self._connection = pymysql.connect(
                host=self.rds_host,
                port=self.rds_port,
                database=self.rds_database,
                user=self.rds_user,
                password=self.rds_password,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
                read_timeout=30,
            )
        return self._connection

    def get_enabled_patterns(self, target_service: Optional[str] = None) -> List[DetectionPattern]:
        """Load all enabled detection patterns from RDS.

        Args:
            target_service: Filter patterns for specific service (optional)

        Returns:
            List of enabled detection patterns
        """
        if self.use_mock:
            return self._get_mock_patterns(target_service)

        connection = self._get_connection()
        try:
            with connection.cursor() as cursor:
                if target_service:
                    sql = """
                        SELECT id, pattern_name, pattern_type, target_service,
                               query_template, threshold_config, severity, enabled, created_at
                        FROM detection_patterns
                        WHERE enabled = TRUE AND (target_service = %s OR target_service IS NULL)
                        ORDER BY severity DESC, pattern_name ASC
                    """
                    cursor.execute(sql, (target_service,))
                else:
                    sql = """
                        SELECT id, pattern_name, pattern_type, target_service,
                               query_template, threshold_config, severity, enabled, created_at
                        FROM detection_patterns
                        WHERE enabled = TRUE
                        ORDER BY severity DESC, pattern_name ASC
                    """
                    cursor.execute(sql)

                rows = cursor.fetchall()
                return [DetectionPattern.from_db_row(row) for row in rows]
        finally:
            connection.commit()

    def execute_pattern(
        self,
        pattern: DetectionPattern,
        context: Optional[Dict[str, Any]] = None,
    ) -> PatternExecutionResult:
        """Execute a single detection pattern.

        Args:
            pattern: The detection pattern to execute
            context: Additional context variables for query template

        Returns:
            Pattern execution result with anomaly detection
        """
        start_time = datetime.utcnow()
        context = context or {}

        try:
            if pattern.pattern_type == PatternType.SQL:
                return self._execute_sql_pattern(pattern, context, start_time)
            elif pattern.pattern_type == PatternType.METRIC:
                return self._execute_metric_pattern(pattern, context, start_time)
            elif pattern.pattern_type == PatternType.REGEX:
                return self._execute_regex_pattern(pattern, context, start_time)
            else:
                return PatternExecutionResult(
                    pattern=pattern,
                    is_anomaly=False,
                    error_message=f"Unknown pattern type: {pattern.pattern_type}",
                    execution_time_ms=self._calc_execution_time(start_time),
                )
        except Exception as e:
            return PatternExecutionResult(
                pattern=pattern,
                is_anomaly=False,
                error_message=str(e),
                execution_time_ms=self._calc_execution_time(start_time),
            )

    def execute_all_patterns(
        self,
        target_service: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[PatternExecutionResult]:
        """Execute all enabled patterns.

        Args:
            target_service: Filter patterns for specific service
            context: Additional context variables

        Returns:
            List of execution results
        """
        patterns = self.get_enabled_patterns(target_service)
        results = []

        for pattern in patterns:
            result = self.execute_pattern(pattern, context)
            results.append(result)

        return results

    def _execute_sql_pattern(
        self,
        pattern: DetectionPattern,
        context: Dict[str, Any],
        start_time: datetime,
    ) -> PatternExecutionResult:
        """Execute SQL-based detection pattern."""
        if self.use_mock:
            return self._mock_sql_execution(pattern, start_time)

        connection = self._get_connection()

        # Substitute context variables in query template
        query = self._substitute_variables(pattern.query_template, context)

        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()

            # Evaluate threshold
            threshold_config = pattern.threshold_config
            count_threshold = threshold_config.get("count_threshold", 0)
            value_field = threshold_config.get("value_field", "count")
            value_threshold = threshold_config.get("value_threshold")

            is_anomaly = False
            current_value = None

            if len(rows) > count_threshold:
                is_anomaly = True
                current_value = len(rows)
            elif value_threshold and rows:
                current_value = rows[0].get(value_field, 0)
                if current_value > value_threshold:
                    is_anomaly = True

            return PatternExecutionResult(
                pattern=pattern,
                is_anomaly=is_anomaly,
                current_value=current_value,
                threshold_value=value_threshold or count_threshold,
                matched_data=list(rows[:10]),  # Limit sample data
                execution_time_ms=self._calc_execution_time(start_time),
            )
        finally:
            connection.commit()

    def _execute_metric_pattern(
        self,
        pattern: DetectionPattern,
        context: Dict[str, Any],
        start_time: datetime,
    ) -> PatternExecutionResult:
        """Execute metric-based detection pattern."""
        # Metric patterns are placeholders for CloudWatch metric queries
        # This would integrate with AWS CloudWatch
        return PatternExecutionResult(
            pattern=pattern,
            is_anomaly=False,
            error_message="Metric patterns require CloudWatch integration",
            execution_time_ms=self._calc_execution_time(start_time),
        )

    def _execute_regex_pattern(
        self,
        pattern: DetectionPattern,
        context: Dict[str, Any],
        start_time: datetime,
    ) -> PatternExecutionResult:
        """Execute regex-based detection pattern."""
        text_to_match = context.get("text", "")
        regex_pattern = pattern.query_template

        try:
            matches = re.findall(regex_pattern, text_to_match, re.MULTILINE)
            threshold = pattern.threshold_config.get("match_threshold", 1)

            is_anomaly = len(matches) >= threshold

            return PatternExecutionResult(
                pattern=pattern,
                is_anomaly=is_anomaly,
                current_value=len(matches),
                threshold_value=threshold,
                matched_data=[{"match": m} for m in matches[:10]],
                execution_time_ms=self._calc_execution_time(start_time),
            )
        except re.error as e:
            return PatternExecutionResult(
                pattern=pattern,
                is_anomaly=False,
                error_message=f"Invalid regex: {e}",
                execution_time_ms=self._calc_execution_time(start_time),
            )

    def _substitute_variables(self, template: str, context: Dict[str, Any]) -> str:
        """Substitute variables in query template."""
        result = template
        for key, value in context.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                # Escape SQL special characters for safety
                if isinstance(value, str):
                    value = value.replace("'", "''")
                result = result.replace(placeholder, str(value))
        return result

    def _calc_execution_time(self, start_time: datetime) -> float:
        """Calculate execution time in milliseconds."""
        delta = datetime.utcnow() - start_time
        return delta.total_seconds() * 1000

    def _get_mock_patterns(self, target_service: Optional[str] = None) -> List[DetectionPattern]:
        """Get mock patterns for testing."""
        mock_patterns = [
            DetectionPattern(
                id=1,
                pattern_name="high_error_rate",
                pattern_type=PatternType.SQL,
                target_service=None,
                query_template="SELECT COUNT(*) as count FROM logs WHERE level = 'ERROR' AND timestamp > NOW() - INTERVAL 1 HOUR",
                threshold_config={"value_field": "count", "value_threshold": 100},
                severity="high",
            ),
            DetectionPattern(
                id=2,
                pattern_name="failed_authentications",
                pattern_type=PatternType.SQL,
                target_service="auth-service",
                query_template="SELECT user_id, COUNT(*) as attempts FROM auth_logs WHERE success = FALSE AND timestamp > NOW() - INTERVAL 15 MINUTE GROUP BY user_id HAVING attempts >= 5",
                threshold_config={"count_threshold": 0},
                severity="critical",
            ),
            DetectionPattern(
                id=3,
                pattern_name="slow_queries",
                pattern_type=PatternType.SQL,
                target_service="database",
                query_template="SELECT query, duration_ms FROM slow_query_log WHERE duration_ms > 5000 AND timestamp > NOW() - INTERVAL 1 HOUR",
                threshold_config={"count_threshold": 10},
                severity="medium",
            ),
            DetectionPattern(
                id=4,
                pattern_name="exception_pattern",
                pattern_type=PatternType.REGEX,
                target_service=None,
                query_template=r"(?:Exception|Error|FATAL|CRITICAL):\s*(.+)",
                threshold_config={"match_threshold": 5},
                severity="high",
            ),
        ]

        if target_service:
            return [p for p in mock_patterns if p.target_service is None or p.target_service == target_service]
        return mock_patterns

    def _mock_sql_execution(
        self,
        pattern: DetectionPattern,
        start_time: datetime,
    ) -> PatternExecutionResult:
        """Mock SQL pattern execution for testing."""
        import random

        # Simulate some randomness for demo purposes
        is_anomaly = random.random() < 0.3  # 30% chance of anomaly
        current_value = random.randint(0, 150)
        threshold = pattern.threshold_config.get("value_threshold", 100)

        if current_value > threshold:
            is_anomaly = True

        return PatternExecutionResult(
            pattern=pattern,
            is_anomaly=is_anomaly,
            current_value=current_value,
            threshold_value=threshold,
            matched_data=[{"sample": "mock_data"}] if is_anomaly else [],
            execution_time_ms=self._calc_execution_time(start_time),
        )

    def close(self):
        """Close database connection."""
        if self._connection and self._connection.open:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
