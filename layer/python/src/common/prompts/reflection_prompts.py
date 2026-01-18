"""
Reflection Prompts for Quality Assessment.

Templates for the reflection engine that evaluates analysis quality.
"""

from typing import Any, Dict, List, Optional


REFLECTION_SYSTEM_PROMPT = """You are a critical reviewer for automated root cause analysis.
Your role is to evaluate the quality and reliability of analysis results.

Evaluation Criteria:
1. Evidence Sufficiency: Is there enough data to support conclusions?
2. Logical Consistency: Are the reasoning steps sound and coherent?
3. Actionability: Are the recommendations practical and specific?
4. Risk Assessment: Are potential risks properly identified?

Be skeptical but fair. Flag genuine concerns but don't be overly conservative.
The goal is to prevent both false positives and false negatives in automation decisions."""


def build_reflection_prompt(
    analysis_result: Dict[str, Any],
    original_data: Dict[str, Any],
    iteration_count: int,
    previous_reflections: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Build prompt for reflection engine quality assessment.

    Args:
        analysis_result: The analysis result to evaluate
        original_data: Original anomaly and log data
        iteration_count: Current iteration number
        previous_reflections: Previous reflection results if any

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        "## Reflection Task: Quality Assessment",
        "",
        f"**Iteration**: {iteration_count}",
        "",
        "### Analysis Result to Evaluate",
        _format_analysis_for_reflection(analysis_result),
        "",
        "### Original Context",
        _format_context_for_reflection(original_data),
        "",
    ]

    if previous_reflections:
        prompt_parts.extend([
            "### Previous Reflection Results",
            _format_previous_reflections(previous_reflections),
            "",
        ])

    prompt_parts.extend([
        "### Evaluation Criteria",
        "",
        "**1. Evidence Sufficiency** (0.0-1.0)",
        "- Is there sufficient log/metric evidence for the conclusion?",
        "- Are there multiple corroborating data points?",
        "- Is the sample size adequate?",
        "",
        "**2. Logical Consistency** (0.0-1.0)",
        "- Do the reasoning steps follow logically?",
        "- Are there any contradictions in the analysis?",
        "- Is the root cause plausible given the evidence?",
        "",
        "**3. Actionability** (0.0-1.0)",
        "- Are remediation steps specific and implementable?",
        "- Is the expected outcome clearly stated?",
        "- Are rollback plans provided where appropriate?",
        "",
        "**4. Risk Assessment** (0.0-1.0)",
        "- Are potential risks of remediation identified?",
        "- Is the impact assessment reasonable?",
        "- Are edge cases considered?",
        "",
        "### Decision Guidelines",
        "",
        "Based on your evaluation, determine:",
        "",
        "- **auto_execute** (true/false): Safe for automatic remediation?",
        "  - All scores >= 0.8",
        "  - Confidence >= 0.85",
        "  - No critical concerns",
        "",
        "- **should_continue** (true/false): Need more investigation?",
        "  - Any score < 0.6",
        "  - Significant gaps in evidence",
        "  - Contradictory signals",
        "",
        "Respond with a structured JSON object matching the ReflectionOutput schema.",
    ])

    return "\n".join(prompt_parts)


def build_confidence_calibration_prompt(
    stated_confidence: float,
    evidence_summary: str,
    historical_accuracy: Optional[Dict[str, float]] = None,
) -> str:
    """
    Build prompt for calibrating confidence scores.

    Args:
        stated_confidence: The confidence score from analysis
        evidence_summary: Summary of supporting evidence
        historical_accuracy: Optional historical accuracy metrics

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        "## Confidence Calibration Task",
        "",
        f"**Stated Confidence**: {stated_confidence:.2f}",
        "",
        "### Evidence Summary",
        evidence_summary,
        "",
    ]

    if historical_accuracy:
        prompt_parts.extend([
            "### Historical Accuracy",
            f"- Average accuracy at this confidence level: {historical_accuracy.get('accuracy', 0):.2%}",
            f"- Sample size: {historical_accuracy.get('sample_size', 0)}",
            "",
        ])

    prompt_parts.extend([
        "### Calibration Guidelines",
        "",
        "Evaluate whether the stated confidence is appropriate:",
        "",
        "**Over-confident indicators:**",
        "- Limited evidence for strong claims",
        "- Single source of truth",
        "- Ignoring contradictory signals",
        "- First-time pattern (no historical baseline)",
        "",
        "**Under-confident indicators:**",
        "- Multiple corroborating sources",
        "- Well-known error pattern",
        "- Strong metric correlation",
        "- Previous successful remediation",
        "",
        "Provide:",
        "1. Calibrated confidence score (0.0-1.0)",
        "2. Adjustment rationale",
        "3. Factors increasing confidence",
        "4. Factors decreasing confidence",
    ])

    return "\n".join(prompt_parts)


def _format_analysis_for_reflection(analysis: Dict[str, Any]) -> str:
    """Format analysis result for reflection evaluation."""
    lines = []

    if "analysis" in analysis:
        analysis_details = analysis["analysis"]
        lines.append(f"**Root Cause**: {analysis_details.get('root_cause', 'Not specified')}")
        lines.append(f"**Impact Severity**: {analysis_details.get('impact_severity', 'Unknown')}")

        affected = analysis_details.get("affected_services", [])
        if affected:
            lines.append(f"**Affected Services**: {', '.join(affected)}")

        evidence = analysis_details.get("evidence", [])
        if evidence:
            lines.append("**Evidence**:")
            for e in evidence[:5]:
                lines.append(f"  - {e}")

    lines.append(f"**Confidence Score**: {analysis.get('confidence_score', 0):.2f}")
    lines.append(f"**Reasoning**: {analysis.get('reasoning', 'Not provided')}")

    remediations = analysis.get("remediations", [])
    if remediations:
        lines.append("**Remediation Actions**:")
        for r in remediations[:3]:
            action_type = r.get("action_type", "unknown")
            expected = r.get("expected_outcome", "Not specified")
            lines.append(f"  - {action_type}: {expected}")

    return "\n".join(lines)


def _format_context_for_reflection(data: Dict[str, Any]) -> str:
    """Format original context for reflection."""
    lines = []

    if "anomaly_data" in data:
        anomaly = data["anomaly_data"]
        lines.append(f"**Anomaly Type**: {anomaly.get('anomaly_type', 'Unknown')}")
        lines.append(f"**Service**: {anomaly.get('service_name', 'Unknown')}")
        lines.append(f"**Occurrences**: {anomaly.get('occurrence_count', 1)}")

    if "log_summary" in data:
        summary = data["log_summary"]
        # Truncate for reflection
        if len(summary) > 500:
            summary = summary[:500] + "..."
        lines.append(f"**Log Summary**: {summary}")

    if "metrics_data" in data and data["metrics_data"]:
        lines.append("**Metrics Available**: Yes")
    else:
        lines.append("**Metrics Available**: No")

    if "knowledge_base_context" in data and data["knowledge_base_context"]:
        kb_count = len(data["knowledge_base_context"])
        lines.append(f"**Knowledge Base Results**: {kb_count}")

    return "\n".join(lines)


def _format_previous_reflections(reflections: List[Dict[str, Any]]) -> str:
    """Format previous reflection results."""
    lines = []

    for i, reflection in enumerate(reflections, 1):
        lines.append(f"**Iteration {i}**:")
        lines.append(f"  - Overall Confidence: {reflection.get('overall_confidence', 0):.2f}")
        lines.append(f"  - Should Continue: {reflection.get('should_continue', True)}")

        concerns = reflection.get("concerns", [])
        if concerns:
            lines.append("  - Concerns:")
            for concern in concerns[:3]:
                lines.append(f"    * {concern}")

        lines.append(f"  - Reason: {reflection.get('reason', 'Not specified')}")
        lines.append("")

    return "\n".join(lines)
