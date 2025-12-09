"""
LangGraph Nodes for BDP Agent.

Node implementations for the ReAct workflow.
"""

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.models.agent_state import AgentState
from src.models.analysis_result import AnalysisResult, ReflectionOutput
from src.prompts.analysis_prompts import ANALYSIS_SYSTEM_PROMPT, build_analysis_prompt
from src.prompts.reflection_prompts import REFLECTION_SYSTEM_PROMPT, build_reflection_prompt
from src.prompts.replan_prompts import build_replan_prompt


def think_node(state: AgentState) -> Dict[str, Any]:
    """
    Think node: Analyze current state and decide next action.

    This node:
    1. Reviews current evidence and analysis
    2. Identifies information gaps
    3. Formulates next investigation step
    """
    messages = list(state["messages"])

    # Build thinking prompt based on current state
    anomaly_data = state["anomaly_data"]
    log_summary = state["log_summary"]
    tool_results = state.get("tool_results", [])
    iteration = state["iteration_count"]

    if iteration == 0:
        # Initial thinking
        thinking_prompt = f"""
You are analyzing an anomaly. Here is the initial information:

**Anomaly Data:**
- Type: {anomaly_data.get('anomaly_type', 'unknown')}
- Service: {anomaly_data.get('service_name', 'unknown')}
- Severity: {anomaly_data.get('severity', 'medium')}
- Occurrences: {anomaly_data.get('occurrence_count', 1)}

**Log Summary:**
{log_summary}

Based on this information, what additional data do you need to determine the root cause?
Consider:
1. What metrics would help understand the issue?
2. What logs would provide more context?
3. Is there relevant documentation in the knowledge base?

Respond with your analysis plan and which tools to use first.
"""
    else:
        # Subsequent thinking with tool results
        tool_summary = "\n".join([
            f"- {r['tool_name']}: {'Success' if r['success'] else 'Failed'}"
            for r in tool_results[-3:]
        ])

        thinking_prompt = f"""
Iteration {iteration}: Continue your analysis.

**Recent Tool Results:**
{tool_summary}

**Current Evidence:**
- Metrics collected: {len([r for r in tool_results if 'metrics' in r.get('tool_name', '')])}
- Logs analyzed: {len([r for r in tool_results if 'logs' in r.get('tool_name', '')])}

Based on the evidence gathered so far:
1. What is your current hypothesis for the root cause?
2. What additional information would strengthen or refute this hypothesis?
3. Are you ready to form a conclusion, or do you need more data?

If you have enough evidence, prepare your final analysis.
Otherwise, specify which tools to use next.
"""

    messages.append(HumanMessage(content=thinking_prompt))

    return {
        "messages": [HumanMessage(content=thinking_prompt)],
        "iteration_count": iteration + 1,
    }


def act_node(state: AgentState) -> Dict[str, Any]:
    """
    Act node: Execute selected tools based on thinking.

    This node:
    1. Parses tool selection from previous message
    2. Executes tools with appropriate parameters
    3. Collects results for observation
    """
    # In a real implementation, this would:
    # 1. Parse the LLM's tool selection from the message
    # 2. Execute the selected tools via LangChain tool executor
    # 3. Return tool results

    # For the workflow structure, we'll represent tool execution
    messages = list(state["messages"])
    tool_results = list(state.get("tool_results", []))

    # Simulated tool execution result
    # In real implementation, LangGraph would handle tool calling via bind_tools
    execution_result = {
        "tool_name": "get_service_health",
        "input_params": {"service_name": state["anomaly_data"].get("service_name", "unknown")},
        "output": {
            "status": "degraded",
            "health_score": 0.85,
            "error_rate": 0.15,
        },
        "success": True,
        "error_message": None,
    }

    tool_results.append(execution_result)

    # Create tool message for the conversation
    tool_message = ToolMessage(
        content=str(execution_result["output"]),
        tool_call_id=f"call_{len(tool_results)}",
    )

    return {
        "messages": [tool_message],
        "tool_results": tool_results,
    }


def observe_node(state: AgentState) -> Dict[str, Any]:
    """
    Observe node: Process tool results and update understanding.

    This node:
    1. Synthesizes tool execution results
    2. Updates evidence collection
    3. Prepares summary for reflection
    """
    tool_results = state.get("tool_results", [])
    messages = list(state["messages"])

    # Synthesize observations
    observations = []
    for result in tool_results[-3:]:  # Look at recent results
        if result["success"]:
            observations.append(
                f"**{result['tool_name']}**: {result['output']}"
            )
        else:
            observations.append(
                f"**{result['tool_name']}**: Failed - {result.get('error_message', 'Unknown error')}"
            )

    observation_summary = "\n".join(observations)

    observation_message = HumanMessage(
        content=f"""
**Observation Summary (Iteration {state['iteration_count']}):**

{observation_summary}

Based on these observations, update your analysis.
"""
    )

    return {
        "messages": [observation_message],
    }


def reflect_node(state: AgentState) -> Dict[str, Any]:
    """
    Reflect node: Evaluate analysis quality and confidence.

    This node:
    1. Assesses evidence sufficiency
    2. Checks logical consistency
    3. Determines if more investigation is needed
    """
    reflection_history = list(state.get("reflection_history", []))

    # Build reflection context
    analysis_result = state.get("analysis_result", {})
    original_data = {
        "anomaly_data": state["anomaly_data"],
        "log_summary": state["log_summary"],
        "metrics_data": state.get("metrics_data"),
        "knowledge_base_context": state.get("knowledge_base_context"),
    }

    # In real implementation, would call LLM with reflection prompt
    # For now, simulate reflection based on iteration count and data

    tool_count = len(state.get("tool_results", []))
    iteration = state["iteration_count"]

    # Simulate reflection scores
    evidence_sufficiency = min(0.5 + (tool_count * 0.1), 0.95)
    logical_consistency = 0.8  # Assume reasonable consistency
    actionability = 0.7 if analysis_result else 0.4
    risk_assessment = 0.75

    overall_confidence = (
        evidence_sufficiency * 0.3
        + logical_consistency * 0.3
        + actionability * 0.2
        + risk_assessment * 0.2
    )

    # Determine if we should continue
    should_continue = overall_confidence < 0.7 and iteration < state["max_iterations"]

    concerns = []
    if evidence_sufficiency < 0.6:
        concerns.append("Need more supporting evidence")
    if actionability < 0.5:
        concerns.append("Remediation steps not clear enough")

    reflection_result = {
        "evidence_sufficiency": evidence_sufficiency,
        "logical_consistency": logical_consistency,
        "actionability": actionability,
        "risk_assessment": risk_assessment,
        "overall_confidence": overall_confidence,
        "concerns": concerns,
        "should_continue": should_continue,
        "reason": "Continuing investigation" if should_continue else "Sufficient evidence gathered",
    }

    reflection_history.append(reflection_result)

    # Update state
    return {
        "reflection_history": reflection_history,
        "confidence_score": overall_confidence,
        "should_continue": should_continue,
    }


def replan_node(state: AgentState) -> Dict[str, Any]:
    """
    Replan node: Adjust investigation strategy based on reflection.

    This node:
    1. Analyzes reflection concerns
    2. Identifies information gaps
    3. Formulates new investigation approach
    """
    reflection_history = state.get("reflection_history", [])
    latest_reflection = reflection_history[-1] if reflection_history else {}

    concerns = latest_reflection.get("concerns", [])
    iteration = state["iteration_count"]

    # Build replan message
    replan_content = f"""
**Replanning (Iteration {iteration})**

Previous reflection identified these concerns:
{chr(10).join(f'- {c}' for c in concerns) if concerns else '- No specific concerns'}

Confidence score: {latest_reflection.get('overall_confidence', 0):.2f}

Adjusting investigation strategy:
1. Focus on addressing the identified gaps
2. Prioritize high-value data sources
3. Consider alternative hypotheses

What additional tools or approaches should we try?
"""

    return {
        "messages": [HumanMessage(content=replan_content)],
    }


def finalize_node(state: AgentState) -> Dict[str, Any]:
    """
    Finalize node: Produce final analysis result.

    This node:
    1. Synthesizes all gathered evidence
    2. Produces final root cause analysis
    3. Generates remediation recommendations
    """
    anomaly_data = state["anomaly_data"]
    tool_results = state.get("tool_results", [])
    reflection_history = state.get("reflection_history", [])

    # Calculate final confidence
    latest_reflection = reflection_history[-1] if reflection_history else {}
    confidence = latest_reflection.get("overall_confidence", 0.5)

    # Determine if human review is needed
    requires_human_review = confidence < 0.85
    review_reason = None
    if requires_human_review:
        if confidence < 0.5:
            review_reason = "Low confidence - insufficient evidence for automated action"
        else:
            review_reason = "Moderate confidence - recommend human verification"

    # Build analysis result
    service_name = anomaly_data.get("service_name", "unknown")
    anomaly_type = anomaly_data.get("anomaly_type", "unknown")

    # Synthesize root cause from tool results
    root_cause = f"Analysis of {anomaly_type} in {service_name}"
    evidence_list = []

    for result in tool_results:
        if result["success"]:
            evidence_list.append(
                f"{result['tool_name']}: {str(result['output'])[:100]}"
            )

    analysis_result = {
        "analysis": {
            "root_cause": root_cause,
            "impact_severity": anomaly_data.get("severity", "medium"),
            "affected_services": [service_name],
            "evidence": evidence_list[:5],
        },
        "confidence_score": confidence,
        "reasoning": f"Based on {len(tool_results)} tool executions and {len(reflection_history)} reflection cycles",
        "remediations": [],
        "requires_human_review": requires_human_review,
        "review_reason": review_reason,
    }

    # Add remediation based on confidence
    if confidence >= 0.7:
        analysis_result["remediations"] = [
            {
                "action_type": "notify",
                "priority": 1,
                "parameters": {"channel": "slack", "message": f"Issue detected in {service_name}"},
                "expected_outcome": "Team notified of issue",
                "rollback_plan": "N/A",
                "estimated_impact": "low",
                "requires_approval": False,
            }
        ]

    # Create final message
    final_message = AIMessage(
        content=f"""
**Final Analysis Complete**

**Root Cause:** {root_cause}
**Confidence:** {confidence:.2%}
**Requires Human Review:** {requires_human_review}

**Evidence ({len(evidence_list)} items):**
{chr(10).join(f'- {e}' for e in evidence_list[:5])}

**Recommendation:** {'Proceed with automated remediation' if confidence >= 0.85 else 'Request human approval before proceeding'}
"""
    )

    return {
        "messages": [final_message],
        "analysis_result": analysis_result,
        "should_continue": False,
    }
