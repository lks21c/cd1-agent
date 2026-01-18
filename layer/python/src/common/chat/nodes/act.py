"""
Act Node - Tool 실행.
"""

import json
import logging
import time
from typing import Any, Dict, List, Callable

from langchain_core.messages import ToolMessage

from src.common.chat.state import ChatStateDict, ChatPhase, ToolExecution

logger = logging.getLogger(__name__)


def act_node(state: ChatStateDict, tools: Dict[str, Callable]) -> Dict[str, Any]:
    """
    계획에 따라 Tool을 실행합니다.

    Args:
        state: 현재 상태
        tools: 사용 가능한 Tool 딕셔너리

    Returns:
        업데이트된 상태 필드
    """
    logger.info("Act node: Tool 실행 중...")

    current_plan = state.get("current_plan", "{}")
    tool_executions = list(state.get("tool_executions", []))

    # 계획에서 필요한 Tool 추출
    try:
        plan_data = json.loads(current_plan) if isinstance(current_plan, str) else current_plan
        tools_needed = plan_data.get("tools_needed", [])
    except (json.JSONDecodeError, AttributeError):
        tools_needed = []
        logger.warning("Act node: 계획 파싱 실패, 기본 Tool 사용")

    # Tool이 없으면 기본 정보 수집
    if not tools_needed:
        tools_needed = ["get_service_health"]

    new_executions = []
    messages = []

    for tool_name in tools_needed:
        if tool_name not in tools:
            logger.warning(f"Act node: Tool '{tool_name}' 없음, 스킵")
            continue

        start_time = time.time()

        try:
            # Tool 실행
            tool_func = tools[tool_name]

            # 파라미터 추출 (계획에서)
            params = _extract_tool_params(plan_data, tool_name)

            # 실행
            result = tool_func(**params) if params else tool_func()

            execution_time_ms = int((time.time() - start_time) * 1000)

            execution = {
                "tool_name": tool_name,
                "input_params": params,
                "output": result,
                "success": True,
                "error_message": None,
                "execution_time_ms": execution_time_ms,
            }

            new_executions.append(execution)

            # Tool 메시지 추가
            messages.append(ToolMessage(
                content=f"[{tool_name}] 실행 완료: {str(result)[:500]}",
                tool_call_id=f"{tool_name}_{int(time.time())}",
            ))

            logger.info(f"Act node: {tool_name} 실행 완료 ({execution_time_ms}ms)")

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)

            execution = {
                "tool_name": tool_name,
                "input_params": {},
                "output": None,
                "success": False,
                "error_message": str(e),
                "execution_time_ms": execution_time_ms,
            }

            new_executions.append(execution)

            messages.append(ToolMessage(
                content=f"[{tool_name}] 실행 실패: {str(e)}",
                tool_call_id=f"{tool_name}_{int(time.time())}",
            ))

            logger.error(f"Act node: {tool_name} 실행 실패 - {e}")

    # 기존 실행 결과에 새 결과 추가
    tool_executions.extend(new_executions)

    return {
        "messages": messages,
        "phase": ChatPhase.ACTING.value,
        "tool_executions": tool_executions,
    }


def _extract_tool_params(plan_data: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    """계획에서 Tool 파라미터 추출."""
    # 기본 파라미터
    default_params = {
        "get_cloudwatch_metrics": {"service_name": "default", "metric_name": "CPUUtilization"},
        "query_cloudwatch_logs": {"log_group": "/aws/lambda/default", "query": "fields @message"},
        "get_service_health": {"service_name": "default"},
        "search_knowledge_base": {"query": plan_data.get("intent", "")},
        "get_prometheus_metrics": {"query": "up"},
    }

    return default_params.get(tool_name, {})


def create_act_node(tools: Dict[str, Callable]):
    """Tool을 주입한 act_node 생성."""
    def _act_node(state: ChatStateDict) -> Dict[str, Any]:
        return act_node(state, tools)
    return _act_node
