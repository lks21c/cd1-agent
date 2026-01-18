"""
Observe Node - Tool 실행 결과 관찰 및 요약.
"""

import json
import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.common.chat.state import ChatStateDict, ChatPhase
from src.common.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def observe_node(state: ChatStateDict, llm_client: LLMClient) -> Dict[str, Any]:
    """
    Tool 실행 결과를 관찰하고 요약합니다.

    Args:
        state: 현재 상태
        llm_client: LLM 클라이언트

    Returns:
        업데이트된 상태 필드
    """
    logger.info("Observe node: 결과 관찰 중...")

    tool_executions = state.get("tool_executions", [])
    current_plan = state.get("current_plan", "")

    # Tool 실행 결과 요약
    execution_summaries = []
    for execution in tool_executions:
        tool_name = execution.get("tool_name", "unknown")
        success = execution.get("success", False)
        output = execution.get("output", "")
        error = execution.get("error_message", "")

        if success:
            # 출력 요약 (너무 길면 자름)
            output_str = str(output)
            if len(output_str) > 500:
                output_str = output_str[:500] + "..."
            execution_summaries.append(f"- {tool_name}: 성공\n  결과: {output_str}")
        else:
            execution_summaries.append(f"- {tool_name}: 실패\n  오류: {error}")

    execution_summary = "\n".join(execution_summaries) if execution_summaries else "실행된 Tool 없음"

    # LLM을 사용해 관찰 요약 생성
    observe_prompt = f"""다음 Tool 실행 결과를 분석하고 핵심 정보를 요약하세요.

계획: {current_plan}

실행 결과:
{execution_summary}

다음 형식으로 요약하세요:
1. 수집된 주요 정보
2. 발견된 이상 징후 (있는 경우)
3. 추가 조사 필요 여부
"""

    try:
        observation = llm_client.generate(
            prompt=observe_prompt,
            temperature=0.3,
            max_tokens=1024,
        )
    except Exception as e:
        logger.error(f"Observe node: LLM 호출 실패 - {e}")
        observation = f"Tool 실행 완료:\n{execution_summary}"

    # 메시지 추가
    new_message = AIMessage(content=f"[관찰] {observation[:300]}...")

    logger.info("Observe node: 관찰 완료")

    return {
        "messages": [new_message],
        "phase": ChatPhase.OBSERVING.value,
        "observation": observation,
    }


def create_observe_node(llm_client: LLMClient):
    """LLM 클라이언트를 주입한 observe_node 생성."""
    def _observe_node(state: ChatStateDict) -> Dict[str, Any]:
        return observe_node(state, llm_client)
    return _observe_node
