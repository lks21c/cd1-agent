"""
Log Mock Data for BDP Agent Tests.

Provides log data generators for various test scenarios.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


class LogDataFactory:
    """Factory for generating mock CloudWatch Logs data."""

    @staticmethod
    def create_log_entry(
        message: str,
        timestamp: Optional[datetime] = None,
        log_stream: str = "test-stream",
        level: str = "ERROR",
    ) -> Dict[str, Any]:
        """Create a single log entry."""
        ts = timestamp or datetime.utcnow()
        return {
            "@timestamp": ts.isoformat(),
            "@message": f"{level}: {message}" if not message.startswith(level) else message,
            "@logStream": log_stream,
        }

    @staticmethod
    def create_error_logs(
        count: int,
        base_time: Optional[datetime] = None,
        message_template: str = "Test error message {index}",
        interval_minutes: int = 1,
    ) -> List[Dict[str, Any]]:
        """Create multiple error log entries."""
        base = base_time or datetime.utcnow()
        return [
            LogDataFactory.create_log_entry(
                message=message_template.format(index=i),
                timestamp=base - timedelta(minutes=i * interval_minutes),
                log_stream=f"test-stream-{i % 3}",
            )
            for i in range(count)
        ]

    @staticmethod
    def create_connection_timeout_logs(count: int = 10) -> List[Dict[str, Any]]:
        """Create connection timeout error logs."""
        base = datetime.utcnow()
        messages = [
            "Connection timeout to database after 30s",
            "Failed to establish connection to RDS instance",
            "Socket timeout while waiting for response",
            "Connection pool exhausted - no available connections",
            "Request timed out after 60000ms",
        ]
        return [
            LogDataFactory.create_log_entry(
                message=messages[i % len(messages)],
                timestamp=base - timedelta(minutes=i),
            )
            for i in range(count)
        ]

    @staticmethod
    def create_auth_failure_logs(count: int = 5) -> List[Dict[str, Any]]:
        """Create authentication failure logs."""
        base = datetime.utcnow()
        return [
            LogDataFactory.create_log_entry(
                message=f"Authentication failed for user test_user_{i}@example.com",
                timestamp=base - timedelta(minutes=i),
                log_stream="auth-service-stream",
            )
            for i in range(count)
        ]

    @staticmethod
    def create_mixed_severity_logs() -> List[Dict[str, Any]]:
        """Create logs with various severity levels."""
        base = datetime.utcnow()
        return [
            {"@timestamp": base.isoformat(), "@message": "ERROR: Critical error occurred", "@logStream": "stream-1"},
            {"@timestamp": (base - timedelta(minutes=1)).isoformat(), "@message": "WARN: Warning message", "@logStream": "stream-1"},
            {"@timestamp": (base - timedelta(minutes=2)).isoformat(), "@message": "INFO: Normal operation", "@logStream": "stream-1"},
            {"@timestamp": (base - timedelta(minutes=3)).isoformat(), "@message": "ERROR: Another error", "@logStream": "stream-2"},
            {"@timestamp": (base - timedelta(minutes=4)).isoformat(), "@message": "FATAL: System failure", "@logStream": "stream-2"},
        ]


def generate_error_logs(count: int = 5, error_type: str = "general") -> List[Dict[str, Any]]:
    """Generate error logs based on type.

    Args:
        count: Number of log entries
        error_type: Type of errors (general, timeout, auth, memory)

    Returns:
        List of log entries
    """
    if error_type == "timeout":
        return LogDataFactory.create_connection_timeout_logs(count)
    elif error_type == "auth":
        return LogDataFactory.create_auth_failure_logs(count)
    elif error_type == "memory":
        base = datetime.utcnow()
        return [
            LogDataFactory.create_log_entry(
                message="OutOfMemoryError: Java heap space",
                timestamp=base - timedelta(minutes=i),
            )
            for i in range(count)
        ]
    else:
        return LogDataFactory.create_error_logs(count)


def generate_empty_logs() -> List[Dict[str, Any]]:
    """Generate empty log list."""
    return []


def generate_unicode_logs() -> List[Dict[str, Any]]:
    """Generate logs with unicode characters."""
    base = datetime.utcnow()
    return [
        {
            "@timestamp": base.isoformat(),
            "@message": "ERROR: 데이터베이스 연결 실패 - タイムアウト 🔥",
            "@logStream": "unicode-stream",
        },
        {
            "@timestamp": (base - timedelta(minutes=1)).isoformat(),
            "@message": "Exception: 사용자 인증 오류 - émoji test 💥",
            "@logStream": "unicode-stream",
        },
        {
            "@timestamp": (base - timedelta(minutes=2)).isoformat(),
            "@message": "FATAL: 系统崩溃 - Système en panne ⚠️",
            "@logStream": "unicode-stream",
        },
    ]
