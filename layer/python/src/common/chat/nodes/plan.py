"""
Plan Node - 사용자 요청 분석 및 계획 수립.
"""

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, AIMessage

from src.common.chat.state import ChatStateDict, ChatPhase
from src.common.chat.config import get_prompts
from src.common.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def plan_node(state: ChatStateDict, llm_client: LLMClient) -> Dict[str, Any]:
    """
    사용자 요청을 분석하고 실행 계획을 수립합니다.

    Args:
        state: 현재 상태
        llm_client: LLM 클라이언트

    Returns:
        업데이트된 상태 필드
    """
    logger.info("Plan node: 실행 계획 수립 중...")

    prompts = get_prompts()
    user_input = state.get("user_input", "")

    # 대화 컨텍스트 구성
    context_parts = []
    for msg in state.get("messages", [])[-5:]:
        if hasattr(msg, "content"):
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            context_parts.append(f"{role}: {msg.content}")
    context = "\n".join(context_parts) if context_parts else "없음"

    # 계획 프롬프트 생성
    plan_prompt = prompts.plan_prompt.format(
        context=context,
        user_input=user_input,
    )

    try:
        # LLM 호출
        response = llm_client.generate(
            prompt=plan_prompt,
            system_prompt=prompts.system_prompt,
            temperature=0.3,
        )

        # JSON 파싱 시도
        try:
            # JSON 블록 추출
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            plan_data = json.loads(json_str)
            current_plan = json.dumps(plan_data, ensure_ascii=False, indent=2)

            logger.info(f"Plan node: 계획 수립 완료 - {plan_data.get('intent', 'unknown')}")

        except json.JSONDecodeError:
            # JSON 파싱 실패시 텍스트 그대로 사용
            current_plan = response
            logger.warning("Plan node: JSON 파싱 실패, 텍스트 계획 사용")

    except Exception as e:
        logger.error(f"Plan node: LLM 호출 실패 - {e}")
        current_plan = json.dumps({
            "intent": "사용자 요청 처리",
            "steps": ["정보 수집", "분석", "응답"],
            "tools_needed": [],
            "confidence": 0.5,
        }, ensure_ascii=False)

    # 새 메시지 추가
    new_message = AIMessage(content=f"[계획 수립] {current_plan[:200]}...")

    return {
        "messages": [new_message],
        "phase": ChatPhase.PLANNING.value,
        "current_plan": current_plan,
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


def create_plan_node(llm_client: LLMClient):
    """LLM 클라이언트를 주입한 plan_node 생성."""
    def _plan_node(state: ChatStateDict) -> Dict[str, Any]:
        return plan_node(state, llm_client)
    return _plan_node
