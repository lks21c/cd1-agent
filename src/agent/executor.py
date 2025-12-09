"""
Agent Executor for BDP Agent.

High-level interface for running the LangGraph agent.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.models.agent_state import AgentState, AgentExecutionResult
from src.models.analysis_result import AnalysisResult
from src.services.llm_client import LLMClient, LLMProvider
from src.services.aws_client import AWSClient, AWSProvider
from src.agent.graph import create_agent_graph, create_simple_graph, compile_graph
from src.agent.tools import set_aws_client

logger = logging.getLogger(__name__)


class AgentExecutor:
    """
    High-level executor for the BDP Agent.

    Provides a simple interface to run the agent workflow
    with proper initialization and result handling.

    Usage:
        executor = AgentExecutor()
        result = executor.run(
            anomaly_data={"signature": "...", "anomaly_type": "..."},
            log_summary="Error patterns detected...",
        )
    """

    def __init__(
        self,
        llm_provider: LLMProvider = LLMProvider.MOCK,
        aws_provider: AWSProvider = AWSProvider.MOCK,
        max_iterations: int = 5,
        use_simple_graph: bool = False,
    ):
        """
        Initialize the agent executor.

        Args:
            llm_provider: LLM provider to use
            aws_provider: AWS provider to use
            max_iterations: Maximum ReAct iterations
            use_simple_graph: Use simplified graph for testing
        """
        self.llm_client = LLMClient(provider=llm_provider)
        self.aws_client = AWSClient(provider=aws_provider)
        self.max_iterations = max_iterations

        # Inject AWS client into tools
        set_aws_client(self.aws_client)

        # Create and compile graph
        if use_simple_graph:
            graph = create_simple_graph()
        else:
            graph = create_agent_graph()

        self.compiled_graph = compile_graph(graph)

    def run(
        self,
        anomaly_data: Dict[str, Any],
        log_summary: str,
        metrics_data: Optional[Dict[str, Any]] = None,
        knowledge_base_context: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentExecutionResult:
        """
        Run the agent workflow.

        Args:
            anomaly_data: Detected anomaly information
            log_summary: Summarized log data
            metrics_data: Optional CloudWatch metrics
            knowledge_base_context: Optional KB search results

        Returns:
            AgentExecutionResult with analysis and recommendations
        """
        logger.info(f"Starting agent execution for: {anomaly_data.get('signature', 'unknown')}")
        start_time = datetime.utcnow()

        # Initialize state
        initial_state: AgentState = {
            "messages": [
                SystemMessage(content="You are an expert DevOps engineer analyzing system anomalies."),
                HumanMessage(content=f"Analyze this anomaly: {anomaly_data.get('anomaly_type', 'unknown')} in {anomaly_data.get('service_name', 'unknown')}"),
            ],
            "anomaly_data": anomaly_data,
            "log_summary": log_summary,
            "metrics_data": metrics_data,
            "knowledge_base_context": knowledge_base_context,
            "analysis_result": None,
            "confidence_score": 0.0,
            "remediation_plan": None,
            "iteration_count": 0,
            "max_iterations": self.max_iterations,
            "should_continue": True,
            "tool_results": [],
            "reflection_history": [],
        }

        try:
            # Execute graph
            final_state = self.compiled_graph.invoke(initial_state)

            # Extract result
            analysis_result = final_state.get("analysis_result", {})
            confidence_score = final_state.get("confidence_score", 0.0)

            # Build execution result
            result: AgentExecutionResult = {
                "root_cause": analysis_result.get("analysis", {}).get("root_cause", "Unable to determine"),
                "confidence_score": confidence_score,
                "remediation_plan": {
                    "actions": analysis_result.get("remediations", []),
                    "priority": "high" if confidence_score >= 0.8 else "medium",
                },
                "evidence": analysis_result.get("analysis", {}).get("evidence", []),
                "reasoning": analysis_result.get("reasoning", ""),
                "requires_human_review": analysis_result.get("requires_human_review", True),
                "review_reason": analysis_result.get("review_reason"),
            }

            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Agent execution completed in {duration:.2f}s "
                f"(confidence: {confidence_score:.2%})"
            )

            return result

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")

            # Return error result
            return {
                "root_cause": f"Execution failed: {str(e)}",
                "confidence_score": 0.0,
                "remediation_plan": {},
                "evidence": [],
                "reasoning": f"Agent execution encountered an error: {str(e)}",
                "requires_human_review": True,
                "review_reason": f"Execution error: {str(e)}",
            }

    def run_async(
        self,
        anomaly_data: Dict[str, Any],
        log_summary: str,
        **kwargs,
    ):
        """
        Run the agent workflow asynchronously.

        Args:
            anomaly_data: Detected anomaly information
            log_summary: Summarized log data
            **kwargs: Additional arguments passed to run()

        Yields:
            Intermediate states during execution
        """
        logger.info(f"Starting async agent execution for: {anomaly_data.get('signature', 'unknown')}")

        initial_state: AgentState = {
            "messages": [
                SystemMessage(content="You are an expert DevOps engineer analyzing system anomalies."),
            ],
            "anomaly_data": anomaly_data,
            "log_summary": log_summary,
            "metrics_data": kwargs.get("metrics_data"),
            "knowledge_base_context": kwargs.get("knowledge_base_context"),
            "analysis_result": None,
            "confidence_score": 0.0,
            "remediation_plan": None,
            "iteration_count": 0,
            "max_iterations": self.max_iterations,
            "should_continue": True,
            "tool_results": [],
            "reflection_history": [],
        }

        # Stream execution
        for state in self.compiled_graph.stream(initial_state):
            yield state

    def get_state_summary(self, state: AgentState) -> Dict[str, Any]:
        """
        Get a summary of the current agent state.

        Args:
            state: Current agent state

        Returns:
            Dictionary with state summary
        """
        return {
            "iteration": state["iteration_count"],
            "max_iterations": state["max_iterations"],
            "confidence": state["confidence_score"],
            "should_continue": state["should_continue"],
            "tools_executed": len(state.get("tool_results", [])),
            "reflections": len(state.get("reflection_history", [])),
            "has_result": state.get("analysis_result") is not None,
        }


def create_executor_from_config(config: Dict[str, Any]) -> AgentExecutor:
    """
    Create an AgentExecutor from configuration.

    Args:
        config: Configuration dictionary with provider settings

    Returns:
        Configured AgentExecutor
    """
    llm_provider = LLMProvider(config.get("llm_provider", "mock"))
    aws_provider = AWSProvider(config.get("aws_provider", "mock"))
    max_iterations = config.get("max_iterations", 5)

    return AgentExecutor(
        llm_provider=llm_provider,
        aws_provider=aws_provider,
        max_iterations=max_iterations,
    )
