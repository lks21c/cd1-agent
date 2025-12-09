"""
Unit Tests for BDP Agent Prompts.

Tests for prompt generation and utilities.
"""

import pytest
import json

from src.prompts.analysis_prompts import (
    build_analysis_prompt,
    build_root_cause_prompt,
    ANALYSIS_SYSTEM_PROMPT,
)
from src.prompts.detection_prompts import (
    build_detection_prompt,
    build_log_summarization_prompt,
    build_pattern_extraction_prompt,
)
from src.prompts.reflection_prompts import (
    build_reflection_prompt,
    build_confidence_calibration_prompt,
    REFLECTION_SYSTEM_PROMPT,
)
from src.prompts.replan_prompts import (
    build_replan_prompt,
    build_tool_selection_prompt,
    build_hypothesis_refinement_prompt,
)
from src.prompts.utils import (
    parse_json_response,
    extract_code_block,
    truncate_context,
    estimate_tokens,
    format_log_for_prompt,
    build_context_window,
)


class TestAnalysisPrompts:
    """Test suite for analysis prompts."""

    def test_build_analysis_prompt(self, sample_anomaly_data, sample_log_summary):
        """Test analysis prompt generation."""
        prompt = build_analysis_prompt(
            anomaly_data=sample_anomaly_data,
            log_summary=sample_log_summary,
        )

        assert "Anomaly Detection Alert" in prompt
        assert sample_anomaly_data["service_name"] in prompt
        assert "root cause" in prompt.lower()

    def test_build_analysis_prompt_with_metrics(
        self, sample_anomaly_data, sample_log_summary, sample_metrics_data
    ):
        """Test analysis prompt with metrics data."""
        prompt = build_analysis_prompt(
            anomaly_data=sample_anomaly_data,
            log_summary=sample_log_summary,
            metrics_data=sample_metrics_data,
        )

        assert "CloudWatch Metrics" in prompt

    def test_build_analysis_prompt_with_knowledge_base(
        self, sample_anomaly_data, sample_log_summary, sample_knowledge_base_results
    ):
        """Test analysis prompt with KB context."""
        prompt = build_analysis_prompt(
            anomaly_data=sample_anomaly_data,
            log_summary=sample_log_summary,
            knowledge_base_context=sample_knowledge_base_results,
        )

        assert "Knowledge Base" in prompt

    def test_build_root_cause_prompt(self):
        """Test root cause investigation prompt."""
        prompt = build_root_cause_prompt(
            service_name="test-service",
            error_patterns=["Connection timeout", "Memory exhausted"],
            timeline=[
                {"timestamp": "10:00:00", "description": "First error", "severity": "error"}
            ],
            related_services=["database", "cache"],
        )

        assert "test-service" in prompt
        assert "Connection timeout" in prompt
        assert "Related Services" in prompt

    def test_analysis_system_prompt(self):
        """Test analysis system prompt content."""
        assert "expert" in ANALYSIS_SYSTEM_PROMPT.lower()
        assert "root cause" in ANALYSIS_SYSTEM_PROMPT.lower()
        assert "confidence" in ANALYSIS_SYSTEM_PROMPT.lower()


class TestDetectionPrompts:
    """Test suite for detection prompts."""

    def test_build_detection_prompt(self):
        """Test detection prompt generation."""
        logs = [
            {"timestamp": "10:00:00", "log_level": "ERROR", "message": "Test error"}
        ]

        prompt = build_detection_prompt(
            logs=logs,
            service_name="test-service",
            time_window="last_hour",
        )

        assert "test-service" in prompt
        assert "Detection Task" in prompt

    def test_build_detection_prompt_with_baseline(self):
        """Test detection prompt with baseline patterns."""
        logs = [
            {"timestamp": "10:00:00", "log_level": "ERROR", "message": "Test error"}
        ]

        prompt = build_detection_prompt(
            logs=logs,
            service_name="test-service",
            baseline_patterns=["Normal startup message", "Health check OK"],
        )

        assert "Normal Patterns" in prompt
        assert "Normal startup message" in prompt

    def test_build_log_summarization_prompt(self):
        """Test log summarization prompt."""
        logs = [
            {"timestamp": "10:00:00", "log_level": "ERROR", "message": "Error 1"},
            {"timestamp": "10:01:00", "log_level": "ERROR", "message": "Error 2"},
        ]

        prompt = build_log_summarization_prompt(
            logs=logs,
            max_summary_tokens=500,
        )

        assert "Summarization" in prompt
        assert "500" in prompt

    def test_build_log_summarization_with_focus(self):
        """Test log summarization with focus areas."""
        logs = [
            {"timestamp": "10:00:00", "log_level": "ERROR", "message": "Test"}
        ]

        prompt = build_log_summarization_prompt(
            logs=logs,
            focus_areas=["errors", "performance"],
        )

        assert "Focus Areas" in prompt
        assert "errors" in prompt

    def test_build_pattern_extraction_prompt(self):
        """Test pattern extraction prompt."""
        logs = [
            {"timestamp": "10:00:00", "message": "Connection error to database"}
        ]

        prompt = build_pattern_extraction_prompt(logs=logs)

        assert "Pattern Extraction" in prompt


class TestReflectionPrompts:
    """Test suite for reflection prompts."""

    def test_build_reflection_prompt(
        self, sample_analysis_result, sample_anomaly_data
    ):
        """Test reflection prompt generation."""
        prompt = build_reflection_prompt(
            analysis_result=sample_analysis_result,
            original_data={"anomaly_data": sample_anomaly_data},
            iteration_count=1,
        )

        assert "Reflection" in prompt
        assert "Evidence Sufficiency" in prompt
        assert "Logical Consistency" in prompt

    def test_build_reflection_prompt_with_history(
        self, sample_analysis_result, sample_anomaly_data, sample_reflection_result
    ):
        """Test reflection prompt with previous reflections."""
        prompt = build_reflection_prompt(
            analysis_result=sample_analysis_result,
            original_data={"anomaly_data": sample_anomaly_data},
            iteration_count=2,
            previous_reflections=[sample_reflection_result],
        )

        assert "Previous Reflection" in prompt

    def test_build_confidence_calibration_prompt(self):
        """Test confidence calibration prompt."""
        prompt = build_confidence_calibration_prompt(
            stated_confidence=0.85,
            evidence_summary="Multiple timeout errors detected",
        )

        assert "Calibration" in prompt
        assert "0.85" in prompt

    def test_reflection_system_prompt(self):
        """Test reflection system prompt content."""
        assert "critical" in REFLECTION_SYSTEM_PROMPT.lower()
        assert "evidence" in REFLECTION_SYSTEM_PROMPT.lower()


class TestReplanPrompts:
    """Test suite for replan prompts."""

    def test_build_replan_prompt(self, sample_reflection_result):
        """Test replan prompt generation."""
        prompt = build_replan_prompt(
            current_state={
                "anomaly_data": {"anomaly_type": "error_spike", "service_name": "test"},
                "analysis_result": {"analysis": {"root_cause": "Test"}, "confidence_score": 0.6},
                "tool_results": [],
            },
            reflection_result=sample_reflection_result,
            available_tools=["get_metrics", "query_logs"],
            iteration_count=2,
            max_iterations=5,
        )

        assert "Replan" in prompt
        assert "Available Tools" in prompt

    def test_build_tool_selection_prompt(self):
        """Test tool selection prompt."""
        tools = [
            {
                "name": "get_cloudwatch_metrics",
                "description": "Get CloudWatch metrics",
                "parameters": {"service_name": "string"},
            }
        ]

        prompt = build_tool_selection_prompt(
            goal="Investigate database timeout",
            available_tools=tools,
            context={"service": "test"},
        )

        assert "Tool Selection" in prompt
        assert "get_cloudwatch_metrics" in prompt

    def test_build_hypothesis_refinement_prompt(self):
        """Test hypothesis refinement prompt."""
        prompt = build_hypothesis_refinement_prompt(
            current_hypothesis="Database connection pool exhausted",
            supporting_evidence=["Timeout errors", "Connection refused"],
            contradicting_evidence=["DB metrics normal"],
            new_data={"metrics": {"connections": 50}},
        )

        assert "Hypothesis" in prompt
        assert "Supporting Evidence" in prompt
        assert "Contradicting Evidence" in prompt


class TestPromptUtils:
    """Test suite for prompt utilities."""

    def test_parse_json_response_valid(self):
        """Test parsing valid JSON."""
        json_str = '{"key": "value", "number": 42}'

        result = parse_json_response(json_str)

        assert result["key"] == "value"
        assert result["number"] == 42

    def test_parse_json_response_from_code_block(self):
        """Test parsing JSON from code block."""
        response = '''Here is the analysis:
```json
{"key": "value"}
```
'''

        result = parse_json_response(response)

        assert result["key"] == "value"

    def test_parse_json_response_with_text(self):
        """Test parsing JSON mixed with text."""
        response = 'The result is: {"key": "value"} as shown.'

        result = parse_json_response(response)

        assert result["key"] == "value"

    def test_parse_json_response_invalid(self):
        """Test parsing invalid JSON raises error."""
        with pytest.raises(ValueError):
            parse_json_response("This is not JSON at all")

    def test_extract_code_block(self):
        """Test extracting code blocks."""
        text = '''Here is some code:
```python
print("Hello")
```
'''

        result = extract_code_block(text, "python")

        assert "print" in result

    def test_extract_code_block_no_language(self):
        """Test extracting code block without language."""
        text = '''Code:
```
some code here
```
'''

        result = extract_code_block(text)

        assert result is not None

    def test_truncate_context(self):
        """Test context truncation."""
        long_text = "x" * 10000

        result = truncate_context(
            long_text,
            max_chars=5000,
            preserve_start=1000,
            preserve_end=1000,
        )

        assert len(result) <= 5100  # Some overhead for truncation message
        assert "truncated" in result.lower()

    def test_truncate_context_short_text(self):
        """Test truncation of short text."""
        short_text = "Short text"

        result = truncate_context(short_text, max_chars=100)

        assert result == short_text

    def test_estimate_tokens(self):
        """Test token estimation."""
        text = "This is a test sentence with about ten words."

        tokens = estimate_tokens(text)

        # Rough estimate: ~4 chars per token
        assert 5 <= tokens <= 20

    def test_format_log_for_prompt(self):
        """Test log formatting."""
        logs = [
            {"timestamp": "10:00:00", "log_level": "ERROR", "message": "Error message"},
            {"timestamp": "10:01:00", "log_level": "INFO", "message": "Info message"},
        ]

        result = format_log_for_prompt(logs)

        assert "[ERROR]" in result
        assert "Error message" in result

    def test_format_log_for_prompt_truncation(self):
        """Test log formatting with truncation."""
        logs = [
            {"timestamp": "10:00:00", "message": "x" * 500}
        ]

        result = format_log_for_prompt(logs, max_message_length=100)

        assert "..." in result

    def test_build_context_window(self):
        """Test context window building."""
        primary = "Primary context content"
        secondary = {
            "Metrics": "Metrics data",
            "Logs": "Log data",
        }

        result = build_context_window(
            primary_context=primary,
            secondary_contexts=secondary,
            max_total_tokens=1000,
        )

        assert "Primary context" in result
        assert "Metrics" in result or "Logs" in result
