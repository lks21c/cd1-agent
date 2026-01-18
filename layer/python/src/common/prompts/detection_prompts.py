"""
Detection Prompts for Anomaly Detection and Log Summarization.

Templates for preprocessing and anomaly classification.
"""

from typing import Any, Dict, List, Optional


DETECTION_SYSTEM_PROMPT = """You are an expert log analyst specializing in AWS infrastructure.
Your role is to identify anomalies, categorize issues, and summarize log patterns efficiently.

Focus on:
1. Error patterns and their severity
2. Unusual frequency or timing of events
3. Resource utilization anomalies
4. Security-related events
5. Performance degradation signals

Be concise but thorough in your analysis."""


def build_detection_prompt(
    logs: List[Dict[str, Any]],
    service_name: str,
    time_window: str = "last_hour",
    baseline_patterns: Optional[List[str]] = None,
) -> str:
    """
    Build prompt for anomaly detection in logs.

    Args:
        logs: List of log entries to analyze
        service_name: Name of the service being analyzed
        time_window: Time window description
        baseline_patterns: Known normal patterns to compare against

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        f"## Anomaly Detection: {service_name}",
        f"**Time Window**: {time_window}",
        "",
        "### Log Entries to Analyze",
        _format_logs_for_detection(logs),
        "",
    ]

    if baseline_patterns:
        prompt_parts.extend([
            "### Known Normal Patterns",
            "\n".join(f"- {pattern}" for pattern in baseline_patterns),
            "",
        ])

    prompt_parts.extend([
        "### Detection Task",
        "Analyze the logs above and identify:",
        "",
        "1. **Anomalous Patterns**: Unusual log entries or sequences",
        "2. **Error Classification**: Type and severity of errors",
        "3. **Frequency Analysis**: Abnormal event rates",
        "4. **Correlation Signals**: Related events that might indicate a root cause",
        "",
        "For each anomaly found, provide:",
        "- Description of the anomaly",
        "- Severity (critical/high/medium/low)",
        "- Confidence (0.0-1.0)",
        "- Recommended action",
    ])

    return "\n".join(prompt_parts)


def build_log_summarization_prompt(
    logs: List[Dict[str, Any]],
    max_summary_tokens: int = 1000,
    focus_areas: Optional[List[str]] = None,
) -> str:
    """
    Build prompt for hierarchical log summarization.

    This implements the 80-90% token reduction strategy by creating
    focused summaries that preserve critical information.

    Args:
        logs: List of log entries to summarize
        max_summary_tokens: Target token count for summary
        focus_areas: Specific areas to emphasize in summary

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        "## Log Summarization Task",
        "",
        f"**Target Summary Length**: ~{max_summary_tokens} tokens",
        "",
        "### Raw Logs",
        _format_logs_for_summarization(logs),
        "",
    ]

    if focus_areas:
        prompt_parts.extend([
            "### Focus Areas",
            "\n".join(f"- {area}" for area in focus_areas),
            "",
        ])

    prompt_parts.extend([
        "### Summarization Guidelines",
        "",
        "Create a hierarchical summary with the following structure:",
        "",
        "**1. Executive Summary** (2-3 sentences)",
        "- Overall system health status",
        "- Most critical issues identified",
        "",
        "**2. Error Summary**",
        "- Group similar errors together",
        "- Include error counts and time ranges",
        "- Note any error patterns or trends",
        "",
        "**3. Performance Indicators**",
        "- Latency patterns",
        "- Throughput observations",
        "- Resource utilization signals",
        "",
        "**4. Notable Events**",
        "- Unusual but non-error events",
        "- Configuration changes detected",
        "- Service state transitions",
        "",
        "**5. Actionable Insights**",
        "- Immediate attention required",
        "- Recommended investigations",
        "",
        "IMPORTANT: Preserve critical details (timestamps, error codes, affected resources)",
        "while eliminating redundancy. Each error type should be mentioned once with count.",
    ])

    return "\n".join(prompt_parts)


def build_pattern_extraction_prompt(
    logs: List[Dict[str, Any]],
    known_patterns: Optional[Dict[str, str]] = None,
) -> str:
    """
    Build prompt for extracting reusable patterns from logs.

    Args:
        logs: List of log entries to extract patterns from
        known_patterns: Previously identified patterns

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        "## Pattern Extraction Task",
        "",
        "Extract reusable log patterns for future matching.",
        "",
        "### Sample Logs",
        _format_logs_for_summarization(logs[:20]),
        "",
    ]

    if known_patterns:
        prompt_parts.extend([
            "### Known Patterns",
        ])
        for pattern_name, pattern_regex in known_patterns.items():
            prompt_parts.append(f"- **{pattern_name}**: `{pattern_regex}`")
        prompt_parts.append("")

    prompt_parts.extend([
        "### Extraction Guidelines",
        "",
        "For each unique log pattern, provide:",
        "1. Pattern name (descriptive identifier)",
        "2. Regex pattern (capturing variable parts)",
        "3. Category (error/warning/info/debug)",
        "4. Priority (critical/high/medium/low)",
        "",
        "Focus on error and warning patterns.",
        "Use named capture groups for important values.",
    ])

    return "\n".join(prompt_parts)


def _format_logs_for_detection(logs: List[Dict[str, Any]], max_entries: int = 50) -> str:
    """Format log entries for detection analysis."""
    lines = []

    for log in logs[:max_entries]:
        timestamp = log.get("timestamp", "")
        level = log.get("log_level", log.get("level", "INFO"))
        message = log.get("message", str(log))
        service = log.get("service_name", "")

        # Truncate long messages
        if len(message) > 300:
            message = message[:300] + "..."

        if service:
            lines.append(f"[{timestamp}] [{level}] [{service}] {message}")
        else:
            lines.append(f"[{timestamp}] [{level}] {message}")

    if len(logs) > max_entries:
        lines.append(f"... and {len(logs) - max_entries} more entries")

    return "\n".join(lines)


def _format_logs_for_summarization(
    logs: List[Dict[str, Any]], max_entries: int = 100
) -> str:
    """Format log entries for summarization."""
    lines = []

    # Group by log level for better summarization
    grouped: Dict[str, List[str]] = {"ERROR": [], "WARN": [], "INFO": [], "DEBUG": []}

    for log in logs[:max_entries]:
        level = log.get("log_level", log.get("level", "INFO")).upper()
        timestamp = log.get("timestamp", "")
        message = log.get("message", str(log))

        if level not in grouped:
            level = "INFO"

        # Truncate long messages
        if len(message) > 200:
            message = message[:200] + "..."

        grouped[level].append(f"[{timestamp}] {message}")

    # Output grouped logs
    for level in ["ERROR", "WARN", "INFO", "DEBUG"]:
        if grouped[level]:
            lines.append(f"\n**{level} ({len(grouped[level])} entries)**")
            for entry in grouped[level][:20]:  # Limit per level
                lines.append(entry)
            if len(grouped[level]) > 20:
                lines.append(f"  ... and {len(grouped[level]) - 20} more {level} entries")

    return "\n".join(lines)
