"""
Pattern Mock Data for BDP Agent Tests.

Provides detection pattern data generators for various test scenarios.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.bdp.services import DetectionPattern, PatternType, PatternExecutionResult


class PatternDataFactory:
    """Factory for generating mock detection patterns."""

    @staticmethod
    def create_sql_pattern(
        pattern_id: int = 1,
        name: str = "test_pattern",
        query: str = "SELECT COUNT(*) FROM logs WHERE level = 'ERROR'",
        threshold_config: Optional[Dict[str, Any]] = None,
        severity: str = "high",
        target_service: Optional[str] = None,
    ) -> DetectionPattern:
        """Create a SQL detection pattern."""
        return DetectionPattern(
            id=pattern_id,
            pattern_name=name,
            pattern_type=PatternType.SQL,
            target_service=target_service,
            query_template=query,
            threshold_config=threshold_config or {"value_field": "count", "value_threshold": 100},
            severity=severity,
        )

    @staticmethod
    def create_regex_pattern(
        pattern_id: int = 1,
        name: str = "exception_pattern",
        regex: str = r"(?:Exception|Error|FATAL|CRITICAL):\s*(.+)",
        match_threshold: int = 5,
        severity: str = "high",
        target_service: Optional[str] = None,
    ) -> DetectionPattern:
        """Create a REGEX detection pattern."""
        return DetectionPattern(
            id=pattern_id,
            pattern_name=name,
            pattern_type=PatternType.REGEX,
            target_service=target_service,
            query_template=regex,
            threshold_config={"match_threshold": match_threshold},
            severity=severity,
        )

    @staticmethod
    def create_metric_pattern(
        pattern_id: int = 1,
        name: str = "metric_pattern",
        metric_config: Optional[Dict[str, Any]] = None,
        severity: str = "medium",
        target_service: Optional[str] = None,
    ) -> DetectionPattern:
        """Create a METRIC detection pattern."""
        return DetectionPattern(
            id=pattern_id,
            pattern_name=name,
            pattern_type=PatternType.METRIC,
            target_service=target_service,
            query_template="cloudwatch://AWS/Lambda/Errors",
            threshold_config=metric_config or {"threshold": 100, "comparison": "gt"},
            severity=severity,
        )

    @staticmethod
    def create_execution_result(
        pattern: DetectionPattern,
        is_anomaly: bool = False,
        current_value: Optional[float] = None,
        threshold_value: Optional[float] = None,
        matched_data: Optional[List[Dict[str, Any]]] = None,
        error_message: Optional[str] = None,
    ) -> PatternExecutionResult:
        """Create a pattern execution result."""
        return PatternExecutionResult(
            pattern=pattern,
            is_anomaly=is_anomaly,
            current_value=current_value,
            threshold_value=threshold_value,
            matched_data=matched_data or [],
            execution_time_ms=10.5,
            error_message=error_message,
        )


# Predefined pattern sets for common scenarios

HIGH_ERROR_RATE_PATTERN = PatternDataFactory.create_sql_pattern(
    pattern_id=1,
    name="high_error_rate",
    query="SELECT COUNT(*) as count FROM logs WHERE level = 'ERROR' AND timestamp > NOW() - INTERVAL 1 HOUR",
    threshold_config={"value_field": "count", "value_threshold": 100},
    severity="high",
)

FAILED_AUTH_PATTERN = PatternDataFactory.create_sql_pattern(
    pattern_id=2,
    name="failed_authentications",
    query="SELECT user_id, COUNT(*) as attempts FROM auth_logs WHERE success = FALSE GROUP BY user_id HAVING attempts >= 5",
    threshold_config={"count_threshold": 0},
    severity="critical",
    target_service="auth-service",
)

SLOW_QUERY_PATTERN = PatternDataFactory.create_sql_pattern(
    pattern_id=3,
    name="slow_queries",
    query="SELECT query, duration_ms FROM slow_query_log WHERE duration_ms > 5000",
    threshold_config={"count_threshold": 10},
    severity="medium",
    target_service="database",
)

EXCEPTION_PATTERN = PatternDataFactory.create_regex_pattern(
    pattern_id=4,
    name="exception_pattern",
    regex=r"(?:Exception|Error|FATAL|CRITICAL):\s*(.+)",
    match_threshold=5,
    severity="high",
)


def generate_mock_patterns(
    include_types: Optional[List[str]] = None,
    target_service: Optional[str] = None,
) -> List[DetectionPattern]:
    """Generate a set of mock patterns.

    Args:
        include_types: Filter patterns by type (SQL, REGEX, METRIC)
        target_service: Filter patterns by target service

    Returns:
        List of detection patterns
    """
    all_patterns = [
        HIGH_ERROR_RATE_PATTERN,
        FAILED_AUTH_PATTERN,
        SLOW_QUERY_PATTERN,
        EXCEPTION_PATTERN,
    ]

    result = all_patterns

    if include_types:
        type_set = {PatternType(t) for t in include_types}
        result = [p for p in result if p.pattern_type in type_set]

    if target_service:
        result = [p for p in result if p.target_service is None or p.target_service == target_service]

    return result


def generate_pattern_context(
    scenario: str = "normal",
    custom_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate context for pattern execution.

    Args:
        scenario: Predefined scenario (normal, auth_failure, exceptions, mixed)
        custom_text: Custom text to include in context

    Returns:
        Context dictionary for pattern execution
    """
    scenarios = {
        "normal": """
            INFO: Application started successfully
            INFO: Processing 100 requests
            INFO: Completed batch job
            DEBUG: Cache hit ratio: 95%
        """,
        "auth_failure": """
            ERROR: Authentication failed for user1@example.com
            ERROR: Authentication failed for user1@example.com
            ERROR: Authentication failed for user1@example.com
            ERROR: Authentication failed for user1@example.com
            ERROR: Authentication failed for user1@example.com
            ERROR: Account locked: user1@example.com
        """,
        "exceptions": """
            Exception: NullPointerException at com.app.Service.process
            Error: Connection refused to database
            FATAL: Out of memory - heap space exhausted
            CRITICAL: Service degradation detected
            Exception: TimeoutException waiting for response
        """,
        "mixed": """
            INFO: Starting application
            ERROR: Database connection failed
            WARN: Retrying connection...
            Exception: ConnectionException after 3 retries
            FATAL: Unable to start - shutting down
            INFO: Shutdown complete
        """,
    }

    text = custom_text or scenarios.get(scenario, scenarios["normal"])

    return {"text": text.strip()}


def create_anomaly_results(
    pattern_count: int = 4,
    anomaly_indices: Optional[List[int]] = None,
) -> List[PatternExecutionResult]:
    """Create a list of pattern execution results with specified anomalies.

    Args:
        pattern_count: Total number of patterns
        anomaly_indices: Indices of patterns that should be anomalies

    Returns:
        List of PatternExecutionResult objects
    """
    patterns = generate_mock_patterns()[:pattern_count]
    anomaly_indices = anomaly_indices or []

    results = []
    for i, pattern in enumerate(patterns):
        is_anomaly = i in anomaly_indices
        results.append(
            PatternDataFactory.create_execution_result(
                pattern=pattern,
                is_anomaly=is_anomaly,
                current_value=150.0 if is_anomaly else 50.0,
                threshold_value=100.0,
                matched_data=[{"sample": "data"}] if is_anomaly else [],
            )
        )

    return results
