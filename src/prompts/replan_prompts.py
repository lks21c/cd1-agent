"""
Replan Prompts for Dynamic Strategy Adjustment.

Templates for replanning when reflection indicates issues.
"""

from typing import Any, Dict, List, Optional


REPLAN_SYSTEM_PROMPT = """You are an expert at adjusting investigation strategies.
When initial analysis is insufficient, you help formulate better approaches.

Your role:
1. Identify gaps in the current investigation
2. Suggest additional data sources or tools
3. Recommend alternative hypotheses to explore
4. Prioritize next steps based on potential impact

Be specific and actionable in your recommendations."""


def build_replan_prompt(
    current_state: Dict[str, Any],
    reflection_result: Dict[str, Any],
    available_tools: List[str],
    iteration_count: int,
    max_iterations: int,
) -> str:
    """
    Build prompt for replanning investigation strategy.

    Args:
        current_state: Current agent state
        reflection_result: Results from reflection evaluation
        available_tools: List of available tools
        iteration_count: Current iteration number
        max_iterations: Maximum allowed iterations

    Returns:
        Formatted prompt string
    """
    remaining_iterations = max_iterations - iteration_count

    prompt_parts = [
        "## Replan Task: Investigation Strategy Adjustment",
        "",
        f"**Iteration**: {iteration_count} / {max_iterations}",
        f"**Remaining Attempts**: {remaining_iterations}",
        "",
        "### Current Investigation State",
        _format_current_state(current_state),
        "",
        "### Reflection Assessment",
        _format_reflection_for_replan(reflection_result),
        "",
        "### Available Tools",
        _format_available_tools(available_tools),
        "",
        "### Replan Guidelines",
        "",
        "Based on the reflection concerns, determine:",
        "",
        "**1. Gap Analysis**",
        "- What information is missing?",
        "- Which evidence is weak or uncertain?",
        "- Are there unexplored angles?",
        "",
        "**2. Tool Selection**",
        "- Which tools would address the gaps?",
        "- What parameters should be used?",
        "- In what order should tools be executed?",
        "",
        "**3. Hypothesis Adjustment**",
        "- Should the current hypothesis be modified?",
        "- Are there alternative explanations to consider?",
        "- What would disprove the current theory?",
        "",
        "**4. Priority Assessment**",
        f"- Given {remaining_iterations} remaining attempts, prioritize high-value actions",
        "- Consider time vs. information value trade-offs",
        "- Focus on decisive evidence gathering",
        "",
        "### Response Format",
        "",
        "Provide a structured replan with:",
        "1. List of tools to execute with parameters",
        "2. Updated hypothesis (if changed)",
        "3. Success criteria for this iteration",
        "4. Fallback strategy if this iteration fails",
    ]

    return "\n".join(prompt_parts)


def build_tool_selection_prompt(
    goal: str,
    available_tools: List[Dict[str, Any]],
    context: Dict[str, Any],
    constraints: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build prompt for intelligent tool selection.

    Args:
        goal: What the agent is trying to achieve
        available_tools: List of tools with descriptions
        context: Current context information
        constraints: Optional constraints on tool usage

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        "## Tool Selection Task",
        "",
        f"**Goal**: {goal}",
        "",
        "### Available Tools",
    ]

    for tool in available_tools:
        name = tool.get("name", "unknown")
        description = tool.get("description", "No description")
        params = tool.get("parameters", {})
        prompt_parts.append(f"\n**{name}**")
        prompt_parts.append(f"Description: {description}")
        if params:
            prompt_parts.append(f"Parameters: {', '.join(params.keys())}")

    prompt_parts.extend([
        "",
        "### Current Context",
        _format_context_summary(context),
        "",
    ])

    if constraints:
        prompt_parts.extend([
            "### Constraints",
            _format_constraints(constraints),
            "",
        ])

    prompt_parts.extend([
        "### Selection Criteria",
        "",
        "Choose tools based on:",
        "1. **Relevance**: How directly does it address the goal?",
        "2. **Information Gain**: What new insights will it provide?",
        "3. **Efficiency**: Time and resource cost",
        "4. **Dependencies**: Does it require other tools first?",
        "",
        "Provide:",
        "- Selected tool(s) in priority order",
        "- Parameters for each tool",
        "- Expected output and how it helps the goal",
    ])

    return "\n".join(prompt_parts)


def build_hypothesis_refinement_prompt(
    current_hypothesis: str,
    supporting_evidence: List[str],
    contradicting_evidence: List[str],
    new_data: Dict[str, Any],
) -> str:
    """
    Build prompt for refining analysis hypothesis.

    Args:
        current_hypothesis: Current root cause hypothesis
        supporting_evidence: Evidence supporting the hypothesis
        contradicting_evidence: Evidence against the hypothesis
        new_data: Newly gathered information

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        "## Hypothesis Refinement Task",
        "",
        "### Current Hypothesis",
        current_hypothesis,
        "",
        "### Supporting Evidence",
    ]

    for evidence in supporting_evidence:
        prompt_parts.append(f"  + {evidence}")

    prompt_parts.extend([
        "",
        "### Contradicting Evidence",
    ])

    for evidence in contradicting_evidence:
        prompt_parts.append(f"  - {evidence}")

    prompt_parts.extend([
        "",
        "### New Information",
        _format_new_data(new_data),
        "",
        "### Refinement Task",
        "",
        "Based on all available evidence:",
        "",
        "1. **Evaluate Current Hypothesis**",
        "   - Is it still viable given new evidence?",
        "   - What confidence level is appropriate?",
        "",
        "2. **Consider Alternatives**",
        "   - What other explanations fit the evidence?",
        "   - Which alternatives should be investigated?",
        "",
        "3. **Provide Refined Hypothesis**",
        "   - Updated root cause statement",
        "   - Key evidence points",
        "   - Confidence score",
        "   - What would definitively prove/disprove it",
    ])

    return "\n".join(prompt_parts)


def _format_current_state(state: Dict[str, Any]) -> str:
    """Format current state for replan prompt."""
    lines = []

    if "anomaly_data" in state:
        anomaly = state["anomaly_data"]
        lines.append(f"**Anomaly**: {anomaly.get('anomaly_type', 'Unknown')} in {anomaly.get('service_name', 'Unknown')}")

    if "analysis_result" in state and state["analysis_result"]:
        result = state["analysis_result"]
        if "analysis" in result:
            lines.append(f"**Current Hypothesis**: {result['analysis'].get('root_cause', 'None')}")
        lines.append(f"**Current Confidence**: {result.get('confidence_score', 0):.2f}")

    if "tool_results" in state:
        tool_count = len(state["tool_results"])
        lines.append(f"**Tools Executed**: {tool_count}")
        for tool_result in state["tool_results"][-3:]:
            name = tool_result.get("tool_name", "Unknown")
            success = "✓" if tool_result.get("success", False) else "✗"
            lines.append(f"  - {name} [{success}]")

    return "\n".join(lines)


def _format_reflection_for_replan(reflection: Dict[str, Any]) -> str:
    """Format reflection result for replan."""
    lines = []

    eval_data = reflection.get("evaluation", {})
    lines.append(f"**Evidence Sufficiency**: {eval_data.get('evidence_sufficiency', 0):.2f}")
    lines.append(f"**Logical Consistency**: {eval_data.get('logical_consistency', 0):.2f}")
    lines.append(f"**Actionability**: {eval_data.get('actionability', 0):.2f}")
    lines.append(f"**Risk Assessment**: {eval_data.get('risk_assessment', 0):.2f}")

    concerns = reflection.get("concerns", [])
    if concerns:
        lines.append("\n**Key Concerns**:")
        for concern in concerns:
            lines.append(f"  ! {concern}")

    recommendations = reflection.get("recommendations", {})
    if recommendations:
        lines.append("\n**Recommendations**:")
        for key, value in recommendations.items():
            lines.append(f"  - {key}: {value}")

    return "\n".join(lines)


def _format_available_tools(tools: List[str]) -> str:
    """Format available tools list."""
    return "\n".join(f"- {tool}" for tool in tools)


def _format_context_summary(context: Dict[str, Any]) -> str:
    """Format context summary."""
    lines = []
    for key, value in context.items():
        if isinstance(value, dict):
            lines.append(f"**{key}**: {len(value)} items")
        elif isinstance(value, list):
            lines.append(f"**{key}**: {len(value)} entries")
        else:
            lines.append(f"**{key}**: {str(value)[:100]}")
    return "\n".join(lines)


def _format_constraints(constraints: Dict[str, Any]) -> str:
    """Format constraints."""
    lines = []
    for key, value in constraints.items():
        lines.append(f"- **{key}**: {value}")
    return "\n".join(lines)


def _format_new_data(data: Dict[str, Any]) -> str:
    """Format new data for hypothesis refinement."""
    lines = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"**{key}** ({len(value)} items):")
            for item in value[:5]:
                lines.append(f"  - {str(item)[:100]}")
        elif isinstance(value, dict):
            lines.append(f"**{key}**:")
            for k, v in list(value.items())[:5]:
                lines.append(f"  - {k}: {str(v)[:100]}")
        else:
            lines.append(f"**{key}**: {str(value)[:200]}")
    return "\n".join(lines)
