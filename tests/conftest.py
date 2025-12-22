"""
Pytest Configuration and Fixtures.

Shared fixtures for CD1 Agent test suite.
"""

import os
import pytest
from datetime import datetime
from typing import Any, Dict, List

# Set test environment
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AWS_REGION", "ap-northeast-2")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("AWS_PROVIDER", "mock")


@pytest.fixture
def sample_anomaly_data() -> Dict[str, Any]:
    """Provide sample anomaly data for testing."""
    return {
        "signature": "test_anomaly_001",
        "anomaly_type": "error_spike",
        "service_name": "test-lambda-function",
        "first_seen": "2024-01-15T10:00:00Z",
        "last_seen": "2024-01-15T10:30:00Z",
        "occurrence_count": 15,
        "sample_logs": [
            {
                "timestamp": "2024-01-15T10:25:00Z",
                "service_name": "test-lambda-function",
                "log_level": "ERROR",
                "message": "Connection timeout to database after 30s",
            },
            {
                "timestamp": "2024-01-15T10:26:00Z",
                "service_name": "test-lambda-function",
                "log_level": "ERROR",
                "message": "Failed to process request: database unavailable",
            },
        ],
        "metrics_snapshot": {
            "error_rate": 0.15,
            "latency_p99": 5000,
            "invocations": 100,
        },
        "severity": "high",
    }


@pytest.fixture
def sample_log_summary() -> str:
    """Provide sample log summary for testing."""
    return """
## Error Summary
- 15 errors detected in last 30 minutes
- Primary error: Connection timeout to database
- Secondary error: Request processing failures

## Pattern Analysis
- 80% of errors are database connection related
- Errors started at 10:00:00Z
- Error rate increasing over time

## Affected Components
- Lambda function: test-lambda-function
- Database: production-db
"""


@pytest.fixture
def sample_metrics_data() -> Dict[str, Any]:
    """Provide sample CloudWatch metrics data."""
    return {
        "errors": {
            "namespace": "AWS/Lambda",
            "values": [0, 0, 2, 5, 8, 15],
        },
        "duration": {
            "namespace": "AWS/Lambda",
            "values": [100, 150, 500, 2000, 5000, 5000],
        },
        "invocations": {
            "namespace": "AWS/Lambda",
            "values": [50, 55, 60, 58, 62, 55],
        },
    }


@pytest.fixture
def sample_knowledge_base_results() -> List[Dict[str, Any]]:
    """Provide sample knowledge base search results."""
    return [
        {
            "content": "Database connection timeouts can occur when the connection pool is exhausted. Recommend increasing pool size or implementing connection recycling.",
            "score": 0.92,
            "metadata": {"source": "runbook-db-troubleshooting.pdf"},
        },
        {
            "content": "Lambda functions connecting to RDS may experience timeouts if VPC configuration is incorrect or NAT gateway is overloaded.",
            "score": 0.85,
            "metadata": {"source": "aws-lambda-best-practices.pdf"},
        },
    ]


@pytest.fixture
def mock_llm_responses() -> Dict[str, Any]:
    """Provide mock LLM responses for testing."""
    return {
        "generate": '{"analysis": {"root_cause": "Database connection pool exhausted", "impact_severity": "high", "affected_services": ["test-lambda-function", "production-db"], "evidence": ["Connection timeout errors", "Increasing latency"]}, "confidence_score": 0.85, "reasoning": "Multiple timeout errors indicate resource exhaustion", "remediations": [], "requires_human_review": false}',
        "structured": {
            "analysis": {
                "root_cause": "Database connection pool exhausted",
                "impact_severity": "high",
                "affected_services": ["test-lambda-function", "production-db"],
                "evidence": ["Connection timeout errors", "Increasing latency"],
            },
            "confidence_score": 0.85,
            "reasoning": "Multiple timeout errors indicate resource exhaustion",
            "remediations": [],
            "requires_human_review": False,
        },
    }


@pytest.fixture
def mock_aws_data() -> Dict[str, Any]:
    """Provide mock AWS service data."""
    return {
        "cloudwatch_metrics": {
            "namespace": "AWS/Lambda",
            "metric": "Errors",
            "datapoints": [
                {"Timestamp": "2024-01-15T10:00:00Z", "Sum": 0, "Unit": "Count"},
                {"Timestamp": "2024-01-15T10:05:00Z", "Sum": 2, "Unit": "Count"},
                {"Timestamp": "2024-01-15T10:10:00Z", "Sum": 5, "Unit": "Count"},
            ],
        },
        "cloudwatch_logs": [
            {
                "@timestamp": "2024-01-15T10:25:00Z",
                "@message": "ERROR: Connection timeout",
                "@logStream": "test-stream",
            }
        ],
        "knowledge_base": [
            {
                "content": "Mock KB result",
                "score": 0.9,
                "metadata": {"source": "mock.pdf"},
            }
        ],
    }


@pytest.fixture
def sample_cost_data() -> Dict[str, Dict[str, Any]]:
    """Provide sample cost data for anomaly detection."""
    return {
        "AWS Lambda": {
            "current_cost": 150.0,
            "historical_costs": [100.0, 102.0, 98.0, 105.0, 101.0, 103.0, 100.0],
            "timestamps": [
                "2024-01-08",
                "2024-01-09",
                "2024-01-10",
                "2024-01-11",
                "2024-01-12",
                "2024-01-13",
                "2024-01-14",
            ],
        },
        "Amazon EC2": {
            "current_cost": 210.0,
            "historical_costs": [200.0, 202.0, 198.0, 205.0, 201.0, 203.0, 200.0],
            "timestamps": [
                "2024-01-08",
                "2024-01-09",
                "2024-01-10",
                "2024-01-11",
                "2024-01-12",
                "2024-01-13",
                "2024-01-14",
            ],
        },
    }


@pytest.fixture
def lambda_context():
    """Provide mock Lambda context object."""

    class MockLambdaContext:
        aws_request_id = "test-request-id-12345"
        function_name = "test-function"
        memory_limit_in_mb = 256
        invoked_function_arn = "arn:aws:lambda:ap-northeast-2:123456789:function:test"

        def get_remaining_time_in_millis(self):
            return 30000

    return MockLambdaContext()


@pytest.fixture
def sample_analysis_result() -> Dict[str, Any]:
    """Provide sample analysis result."""
    return {
        "analysis": {
            "root_cause": "Database connection pool exhausted",
            "impact_severity": "high",
            "affected_services": ["test-lambda-function"],
            "evidence": ["15 timeout errors", "Latency spike to 5000ms"],
        },
        "confidence_score": 0.87,
        "reasoning": "Multiple corroborating signals indicate database resource exhaustion",
        "remediations": [
            {
                "action_type": "rds_parameter",
                "priority": 1,
                "parameters": {
                    "parameter_group": "production-db-params",
                    "parameter_name": "max_connections",
                    "parameter_value": "200",
                },
                "expected_outcome": "Increase connection pool capacity",
                "rollback_plan": "Revert parameter to previous value",
                "estimated_impact": "low",
                "requires_approval": True,
            }
        ],
        "requires_human_review": False,
    }


@pytest.fixture
def sample_reflection_result() -> Dict[str, Any]:
    """Provide sample reflection result."""
    return {
        "evaluation": {
            "evidence_sufficiency": 0.85,
            "logical_consistency": 0.90,
            "actionability": 0.80,
            "risk_assessment": 0.75,
        },
        "overall_confidence": 0.82,
        "concerns": ["Consider checking for concurrent connection limits"],
        "recommendations": {"additional_investigation": "Check RDS connection metrics"},
        "auto_execute": False,
        "reason": "High confidence but recommend verification",
    }


# Markers for test categorization
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "llm: Tests requiring LLM")
    config.addinivalue_line("markers", "aws: Tests requiring AWS services")
