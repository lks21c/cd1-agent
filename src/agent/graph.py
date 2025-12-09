"""
LangGraph Graph Definition for BDP Agent.

StateGraph configuration for ReAct workflow.
"""

from typing import Literal

from langgraph.graph import END, StateGraph

from src.models.agent_state import AgentState
from src.agent.nodes import (
    think_node,
    act_node,
    observe_node,
    reflect_node,
    replan_node,
    finalize_node,
)


def should_continue(state: AgentState) -> Literal["reflect", "finalize"]:
    """
    Determine if agent should continue iterating or finalize.

    Routes to:
    - "reflect": If iteration limit not reached
    - "finalize": If max iterations reached
    """
    iteration = state["iteration_count"]
    max_iterations = state["max_iterations"]

    if iteration >= max_iterations:
        return "finalize"
    return "reflect"


def after_reflection(state: AgentState) -> Literal["replan", "finalize"]:
    """
    Route after reflection based on confidence.

    Routes to:
    - "replan": If should_continue is True (need more investigation)
    - "finalize": If should_continue is False (ready to conclude)
    """
    if state.get("should_continue", True):
        return "replan"
    return "finalize"


def create_agent_graph() -> StateGraph:
    """
    Create the LangGraph StateGraph for BDP Agent.

    The graph implements a ReAct loop:
    1. Think: Analyze current state, decide next action
    2. Act: Execute selected tools
    3. Observe: Process tool results
    4. Reflect: Evaluate analysis quality
    5. Replan (if needed): Adjust strategy
    6. Finalize: Produce final result

    Returns:
        Compiled StateGraph ready for execution
    """
    # Create graph with AgentState
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("think", think_node)
    workflow.add_node("act", act_node)
    workflow.add_node("observe", observe_node)
    workflow.add_node("reflect", reflect_node)
    workflow.add_node("replan", replan_node)
    workflow.add_node("finalize", finalize_node)

    # Set entry point
    workflow.set_entry_point("think")

    # Add edges for main flow
    workflow.add_edge("think", "act")
    workflow.add_edge("act", "observe")

    # Conditional edge after observe
    workflow.add_conditional_edges(
        "observe",
        should_continue,
        {
            "reflect": "reflect",
            "finalize": "finalize",
        },
    )

    # Conditional edge after reflect
    workflow.add_conditional_edges(
        "reflect",
        after_reflection,
        {
            "replan": "replan",
            "finalize": "finalize",
        },
    )

    # Replan goes back to think
    workflow.add_edge("replan", "think")

    # Finalize ends the workflow
    workflow.add_edge("finalize", END)

    return workflow


def create_simple_graph() -> StateGraph:
    """
    Create a simplified graph for testing.

    This graph skips the full ReAct loop and goes:
    think -> act -> finalize

    Returns:
        Compiled StateGraph for simple execution
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("think", think_node)
    workflow.add_node("act", act_node)
    workflow.add_node("finalize", finalize_node)

    workflow.set_entry_point("think")

    workflow.add_edge("think", "act")
    workflow.add_edge("act", "finalize")
    workflow.add_edge("finalize", END)

    return workflow


def compile_graph(graph: StateGraph, checkpointer=None):
    """
    Compile a StateGraph for execution.

    Args:
        graph: StateGraph to compile
        checkpointer: Optional checkpointer for state persistence

    Returns:
        Compiled graph ready for invocation
    """
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()
