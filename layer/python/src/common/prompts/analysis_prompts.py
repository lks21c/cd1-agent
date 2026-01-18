"""
Analysis Prompts for Root Cause Analysis.

Templates for LLM-based log and metrics analysis.
"""

from typing import Any, Dict, List, Optional


ANALYSIS_SYSTEM_PROMPT = """You are an expert AWS DevOps engineer specializing in root cause analysis.
Your role is to analyze log patterns, metrics, and system behavior to identify the root cause of issues.

When analyzing:
1. Look for error patterns and their frequency
2. Correlate timestamps across different log sources
3. Identify cascading failures and their origin points
4. Consider resource constraints (memory, CPU, connections)
5. Check for configuration issues or deployment changes

Always provide:
- A clear root cause statement
- Evidence supporting your conclusion
- Confidence level (0.0-1.0) based on evidence quality
- Specific remediation steps when possible

Be conservative with confidence scores:
- 0.85+: Strong evidence, multiple corroborating signals
- 0.70-0.84: Good evidence, but some uncertainty
- 0.50-0.69: Moderate evidence, needs more investigation
- Below 0.50: Insufficient evidence, recommend escalation"""


def build_analysis_prompt(
    anomaly_data: Dict[str, Any],
    log_summary: str,
    metrics_data: Optional[Dict[str, Any]] = None,
    knowledge_base_context: Optional[List[Dict[str, Any]]] = None,
    tool_results: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Build the main analysis prompt for root cause analysis.

    Args:
        anomaly_data: Detected anomaly information
        log_summary: Hierarchically summarized logs
        metrics_data: Optional CloudWatch metrics data
        knowledge_base_context: Optional knowledge base search results
        tool_results: Optional results from tool executions

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        "## Anomaly Detection Alert",
        _format_anomaly_section(anomaly_data),
        "",
        "## Log Summary",
        log_summary or "No log summary available.",
        "",
    ]

    if metrics_data:
        prompt_parts.extend([
            "## CloudWatch Metrics",
            _format_metrics_section(metrics_data),
            "",
        ])

    if knowledge_base_context:
        prompt_parts.extend([
            "## Relevant Knowledge Base Context",
            _format_knowledge_base_section(knowledge_base_context),
            "",
        ])

    if tool_results:
        prompt_parts.extend([
            "## Tool Execution Results",
            _format_tool_results_section(tool_results),
            "",
        ])

    prompt_parts.extend([
        "## Analysis Task",
        "Based on the information above, perform root cause analysis:",
        "",
        "1. Identify the most likely root cause",
        "2. List supporting evidence",
        "3. Assess impact severity (critical/high/medium/low)",
        "4. Provide confidence score (0.0-1.0)",
        "5. Suggest remediation actions if confidence >= 0.7",
        "",
        "Respond with a structured JSON object matching the AnalysisResult schema.",
    ])

    return "\n".join(prompt_parts)


def build_root_cause_prompt(
    service_name: str,
    error_patterns: List[str],
    timeline: List[Dict[str, Any]],
    related_services: Optional[List[str]] = None,
) -> str:
    """
    Build a focused root cause investigation prompt.

    Args:
        service_name: Primary affected service
        error_patterns: List of observed error patterns
        timeline: Chronological event timeline
        related_services: Other potentially affected services

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        f"## Root Cause Investigation: {service_name}",
        "",
        "### Observed Error Patterns",
    ]

    for i, pattern in enumerate(error_patterns, 1):
        prompt_parts.append(f"{i}. {pattern}")

    prompt_parts.extend([
        "",
        "### Event Timeline",
    ])

    for event in timeline:
        timestamp = event.get("timestamp", "Unknown")
        description = event.get("description", "")
        severity = event.get("severity", "info")
        prompt_parts.append(f"- [{timestamp}] ({severity}) {description}")

    if related_services:
        prompt_parts.extend([
            "",
            "### Related Services",
            ", ".join(related_services),
        ])

    prompt_parts.extend([
        "",
        "### Analysis Questions",
        "1. What is the earliest indicator of the issue?",
        "2. Is this a cascading failure from an upstream service?",
        "3. Are there any resource exhaustion patterns?",
        "4. What is the blast radius of this issue?",
        "",
        "Provide your root cause analysis with evidence and confidence score.",
    ])

    return "\n".join(prompt_parts)


def _format_anomaly_section(anomaly_data: Dict[str, Any]) -> str:
    """Format anomaly data for the prompt."""
    lines = []

    if "signature" in anomaly_data:
        lines.append(f"**Signature**: {anomaly_data['signature']}")
    if "anomaly_type" in anomaly_data:
        lines.append(f"**Type**: {anomaly_data['anomaly_type']}")
    if "service_name" in anomaly_data:
        lines.append(f"**Service**: {anomaly_data['service_name']}")
    if "severity" in anomaly_data:
        lines.append(f"**Severity**: {anomaly_data['severity']}")
    if "first_seen" in anomaly_data:
        lines.append(f"**First Seen**: {anomaly_data['first_seen']}")
    if "last_seen" in anomaly_data:
        lines.append(f"**Last Seen**: {anomaly_data['last_seen']}")
    if "occurrence_count" in anomaly_data:
        lines.append(f"**Occurrences**: {anomaly_data['occurrence_count']}")

    if "sample_logs" in anomaly_data and anomaly_data["sample_logs"]:
        lines.append("")
        lines.append("**Sample Logs**:")
        for log in anomaly_data["sample_logs"][:5]:
            if isinstance(log, dict):
                msg = log.get("message", str(log))
            else:
                msg = str(log)
            lines.append(f"  - {msg[:200]}...")

    return "\n".join(lines)


def _format_metrics_section(metrics_data: Dict[str, Any]) -> str:
    """Format metrics data for the prompt."""
    lines = []

    for metric_name, metric_values in metrics_data.items():
        if isinstance(metric_values, dict):
            namespace = metric_values.get("namespace", "")
            values = metric_values.get("values", [])
            if values:
                avg_val = sum(values) / len(values)
                max_val = max(values)
                min_val = min(values)
                lines.append(f"**{metric_name}** ({namespace}):")
                lines.append(f"  - Average: {avg_val:.2f}")
                lines.append(f"  - Max: {max_val:.2f}")
                lines.append(f"  - Min: {min_val:.2f}")
        elif isinstance(metric_values, list):
            if metric_values:
                lines.append(f"**{metric_name}**: {metric_values[-1]:.2f} (latest)")

    return "\n".join(lines) if lines else "No metrics data available."


def _format_knowledge_base_section(kb_results: List[Dict[str, Any]]) -> str:
    """Format knowledge base results for the prompt."""
    lines = []

    for i, result in enumerate(kb_results[:5], 1):
        content = result.get("content", "")
        score = result.get("score", 0.0)
        source = result.get("metadata", {}).get("source", "Unknown")

        lines.append(f"**Result {i}** (Score: {score:.2f}, Source: {source})")
        # Truncate content to avoid prompt bloat
        truncated = content[:500] + "..." if len(content) > 500 else content
        lines.append(truncated)
        lines.append("")

    return "\n".join(lines) if lines else "No relevant knowledge base results."


def _format_tool_results_section(tool_results: List[Dict[str, Any]]) -> str:
    """Format tool execution results for the prompt."""
    lines = []

    for result in tool_results:
        tool_name = result.get("tool_name", "Unknown")
        success = result.get("success", False)
        output = result.get("output", {})

        status = "✓" if success else "✗"
        lines.append(f"**{tool_name}** [{status}]")

        if isinstance(output, dict):
            for key, value in list(output.items())[:5]:
                lines.append(f"  - {key}: {value}")
        else:
            lines.append(f"  - Output: {str(output)[:200]}")
        lines.append("")

    return "\n".join(lines) if lines else "No tool results available."
