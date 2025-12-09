"""
Unit Tests for BDP Agent LangGraph Implementation.

Tests for agent tools, nodes, graph, and executor.
"""

import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.agent.tools import (
    get_cloudwatch_metrics,
    query_cloudwatch_logs,
    search_knowledge_base,
    get_service_health,
    analyze_error_pattern,
    check_recent_deployments,
    AGENT_TOOLS,
    set_aws_client,
)
from src.agent.nodes import (
    think_node,
    act_node,
    observe_node,
    reflect_node,
    replan_node,
    finalize_node,
)
from src.agent.graph import (
    create_agent_graph,
    create_simple_graph,
    compile_graph,
    should_continue,
    after_reflection,
)
from src.agent.executor import AgentExecutor, create_executor_from_config
from src.services.aws_client import AWSClient, AWSProvider
from src.models.agent_state import AgentState


class TestAgentTools:
    """Test suite for agent tools."""

    @pytest.fixture(autouse=True)
    def setup_mock_client(self):
        """Set up mock AWS client for all tests."""
        client = AWSClient(provider=AWSProvider.MOCK)
        set_aws_client(client)

    def test_tools_list(self):
        """Test that all tools are registered."""
        assert len(AGENT_TOOLS) == 6

    def test_get_cloudwatch_metrics(self):
        """Test CloudWatch metrics tool."""
        result = get_cloudwatch_metrics.invoke({
            "service_name": "test-function",
            "metric_name": "Errors",
        })

        assert "service_name" in result
        assert "metric_name" in result
        assert result["service_name"] == "test-function"

    def test_query_cloudwatch_logs(self):
        """Test CloudWatch Logs tool."""
        result = query_cloudwatch_logs.invoke({
            "log_group": "/aws/lambda/test",
            "hours": 1,
        })

        assert "log_group" in result
        assert "total_results" in result

    def test_search_knowledge_base(self):
        """Test Knowledge Base search tool."""
        result = search_knowledge_base.invoke({
            "query": "database troubleshooting",
            "max_results": 3,
        })

        assert "query" in result
        assert "results_count" in result

    def test_get_service_health(self):
        """Test service health tool."""
        result = get_service_health.invoke({
            "service_name": "test-function",
        })

        assert "service_name" in result
        assert "status" in result
        assert "health_score" in result

    def test_analyze_error_pattern(self):
        """Test error pattern analysis tool."""
        result = analyze_error_pattern.invoke({
            "error_messages": [
                "Connection timeout to database",
                "Memory limit exceeded",
                "Connection refused",
            ]
        })

        assert "total_errors" in result
        assert "patterns" in result
        assert "dominant_pattern" in result

    def test_analyze_error_pattern_empty(self):
        """Test error pattern analysis with no messages."""
        result = analyze_error_pattern.invoke({
            "error_messages": []
        })

        assert result["status"] == "no_data"

    def test_check_recent_deployments(self):
        """Test deployment check tool."""
        result = check_recent_deployments.invoke({
            "service_name": "test-function",
            "hours": 24,
        })

        assert "service_name" in result
        assert "deployments" in result


class TestAgentNodes:
    """Test suite for agent nodes."""

    @pytest.fixture
    def initial_state(self, sample_anomaly_data, sample_log_summary) -> AgentState:
        """Create initial agent state."""
        return {
            "messages": [
                SystemMessage(content="You are an expert analyst."),
            ],
            "anomaly_data": sample_anomaly_data,
            "log_summary": sample_log_summary,
            "metrics_data": None,
            "knowledge_base_context": None,
            "analysis_result": None,
            "confidence_score": 0.0,
            "remediation_plan": None,
            "iteration_count": 0,
            "max_iterations": 5,
            "should_continue": True,
            "tool_results": [],
            "reflection_history": [],
        }

    def test_think_node_initial(self, initial_state):
        """Test think node on first iteration."""
        result = think_node(initial_state)

        assert "messages" in result
        assert len(result["messages"]) > 0
        assert result["iteration_count"] == 1

    def test_think_node_subsequent(self, initial_state):
        """Test think node on subsequent iterations."""
        initial_state["iteration_count"] = 2
        initial_state["tool_results"] = [
            {"tool_name": "get_metrics", "success": True, "output": {}}
        ]

        result = think_node(initial_state)

        assert result["iteration_count"] == 3

    def test_act_node(self, initial_state):
        """Test act node."""
        result = act_node(initial_state)

        assert "messages" in result
        assert "tool_results" in result
        assert len(result["tool_results"]) > 0

    def test_observe_node(self, initial_state):
        """Test observe node."""
        initial_state["tool_results"] = [
            {"tool_name": "get_metrics", "success": True, "output": {"value": 100}}
        ]

        result = observe_node(initial_state)

        assert "messages" in result
        assert len(result["messages"]) > 0

    def test_reflect_node(self, initial_state):
        """Test reflect node."""
        initial_state["tool_results"] = [
            {"tool_name": "test", "success": True, "output": {}}
        ]

        result = reflect_node(initial_state)

        assert "reflection_history" in result
        assert "confidence_score" in result
        assert "should_continue" in result
        assert len(result["reflection_history"]) == 1

    def test_replan_node(self, initial_state):
        """Test replan node."""
        initial_state["reflection_history"] = [
            {"concerns": ["Need more data"], "overall_confidence": 0.5}
        ]
        initial_state["iteration_count"] = 2

        result = replan_node(initial_state)

        assert "messages" in result

    def test_finalize_node(self, initial_state):
        """Test finalize node."""
        initial_state["tool_results"] = [
            {"tool_name": "get_health", "success": True, "output": {"status": "ok"}}
        ]
        initial_state["reflection_history"] = [
            {"overall_confidence": 0.85, "concerns": []}
        ]

        result = finalize_node(initial_state)

        assert "messages" in result
        assert "analysis_result" in result
        assert result["should_continue"] is False


class TestAgentGraph:
    """Test suite for agent graph."""

    def test_create_agent_graph(self):
        """Test agent graph creation."""
        graph = create_agent_graph()

        assert graph is not None
        # Check nodes exist
        assert "think" in graph.nodes
        assert "act" in graph.nodes
        assert "observe" in graph.nodes
        assert "reflect" in graph.nodes
        assert "replan" in graph.nodes
        assert "finalize" in graph.nodes

    def test_create_simple_graph(self):
        """Test simple graph creation."""
        graph = create_simple_graph()

        assert graph is not None
        assert "think" in graph.nodes
        assert "act" in graph.nodes
        assert "finalize" in graph.nodes

    def test_compile_graph(self):
        """Test graph compilation."""
        graph = create_agent_graph()
        compiled = compile_graph(graph)

        assert compiled is not None

    def test_should_continue_within_limit(self):
        """Test should_continue routing within limit."""
        state: AgentState = {
            "messages": [],
            "anomaly_data": {},
            "log_summary": "",
            "metrics_data": None,
            "knowledge_base_context": None,
            "analysis_result": None,
            "confidence_score": 0.0,
            "remediation_plan": None,
            "iteration_count": 2,
            "max_iterations": 5,
            "should_continue": True,
            "tool_results": [],
            "reflection_history": [],
        }

        result = should_continue(state)

        assert result == "reflect"

    def test_should_continue_at_limit(self):
        """Test should_continue routing at limit."""
        state: AgentState = {
            "messages": [],
            "anomaly_data": {},
            "log_summary": "",
            "metrics_data": None,
            "knowledge_base_context": None,
            "analysis_result": None,
            "confidence_score": 0.0,
            "remediation_plan": None,
            "iteration_count": 5,
            "max_iterations": 5,
            "should_continue": True,
            "tool_results": [],
            "reflection_history": [],
        }

        result = should_continue(state)

        assert result == "finalize"

    def test_after_reflection_continue(self):
        """Test after_reflection routing to replan."""
        state: AgentState = {
            "messages": [],
            "anomaly_data": {},
            "log_summary": "",
            "metrics_data": None,
            "knowledge_base_context": None,
            "analysis_result": None,
            "confidence_score": 0.5,
            "remediation_plan": None,
            "iteration_count": 2,
            "max_iterations": 5,
            "should_continue": True,
            "tool_results": [],
            "reflection_history": [],
        }

        result = after_reflection(state)

        assert result == "replan"

    def test_after_reflection_finalize(self):
        """Test after_reflection routing to finalize."""
        state: AgentState = {
            "messages": [],
            "anomaly_data": {},
            "log_summary": "",
            "metrics_data": None,
            "knowledge_base_context": None,
            "analysis_result": None,
            "confidence_score": 0.9,
            "remediation_plan": None,
            "iteration_count": 2,
            "max_iterations": 5,
            "should_continue": False,
            "tool_results": [],
            "reflection_history": [],
        }

        result = after_reflection(state)

        assert result == "finalize"


class TestAgentExecutor:
    """Test suite for agent executor."""

    def test_executor_creation(self):
        """Test AgentExecutor creation."""
        executor = AgentExecutor(
            llm_provider="mock",
            aws_provider="mock",
        )

        assert executor is not None
        assert executor.max_iterations == 5

    def test_executor_simple_graph(self):
        """Test AgentExecutor with simple graph."""
        executor = AgentExecutor(use_simple_graph=True)

        assert executor is not None

    def test_executor_run(self, sample_anomaly_data, sample_log_summary):
        """Test AgentExecutor run method."""
        executor = AgentExecutor(use_simple_graph=True)

        result = executor.run(
            anomaly_data=sample_anomaly_data,
            log_summary=sample_log_summary,
        )

        assert "root_cause" in result
        assert "confidence_score" in result
        assert "requires_human_review" in result

    def test_executor_state_summary(self, sample_anomaly_data, sample_log_summary):
        """Test AgentExecutor state summary."""
        executor = AgentExecutor()

        state: AgentState = {
            "messages": [],
            "anomaly_data": sample_anomaly_data,
            "log_summary": sample_log_summary,
            "metrics_data": None,
            "knowledge_base_context": None,
            "analysis_result": None,
            "confidence_score": 0.75,
            "remediation_plan": None,
            "iteration_count": 3,
            "max_iterations": 5,
            "should_continue": True,
            "tool_results": [{}, {}],
            "reflection_history": [{}],
        }

        summary = executor.get_state_summary(state)

        assert summary["iteration"] == 3
        assert summary["confidence"] == 0.75
        assert summary["tools_executed"] == 2
        assert summary["reflections"] == 1

    def test_create_executor_from_config(self):
        """Test creating executor from config."""
        config = {
            "llm_provider": "mock",
            "aws_provider": "mock",
            "max_iterations": 3,
        }

        executor = create_executor_from_config(config)

        assert executor is not None
        assert executor.max_iterations == 3
