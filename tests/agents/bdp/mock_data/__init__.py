"""
Mock Data Module for BDP Agent Tests.

Provides reusable mock data generators and factories for testing.
"""

from tests.agents.bdp.mock_data.logs import (
    LogDataFactory,
    generate_error_logs,
    generate_empty_logs,
    generate_unicode_logs,
)
from tests.agents.bdp.mock_data.metrics import (
    MetricDataFactory,
    generate_normal_metrics,
    generate_spike_metrics,
    generate_critical_spike_metrics,
)
from tests.agents.bdp.mock_data.patterns import (
    PatternDataFactory,
    generate_mock_patterns,
    generate_pattern_context,
)

__all__ = [
    # Log factories
    "LogDataFactory",
    "generate_error_logs",
    "generate_empty_logs",
    "generate_unicode_logs",
    # Metric factories
    "MetricDataFactory",
    "generate_normal_metrics",
    "generate_spike_metrics",
    "generate_critical_spike_metrics",
    # Pattern factories
    "PatternDataFactory",
    "generate_mock_patterns",
    "generate_pattern_context",
]
