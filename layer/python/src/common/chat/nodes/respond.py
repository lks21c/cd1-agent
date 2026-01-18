"""
Respond Node - 최종 응답 생성.
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.common.chat.state import ChatStateDict, ChatPhase
from src.common.chat.config import get_prompts
from src.common.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def respond_node(state: ChatStateDict, llm_client: LLMClient) -> Dict[str, Any]:
    """
    사용자에게 최종 응답을 생성합니다.

    Args:
        state: 현재 상태
        llm_client: LLM 클라이언트

    Returns:
        업데이트된 상태 필드
    """
    logger.info("Respond node: 응답 생성 중...")

    prompts = get_prompts()

    user_input = state.get("user_input", "")
    observation = state.get("observation", "")
    reflection = state.get("reflection", {})
    confidence_score = state.get("confidence_score", 0.0)
    pending_approval = state.get("pending_approval")
    tool_executions = state.get("tool_executions", [])

    # 대화 컨텍스트 구성
    context_parts = []
    for msg in state.get("messages", [])[-5:]:
        if hasattr(msg, "content"):
            context_parts.append(msg.content)
    context = "\n".join(context_parts) if context_parts else "없음"

    # 분석 결과 요약
    analysis_parts = []
    if observation:
        analysis_parts.append(f"관찰 결과:\n{observation}")
    if reflection:
        analysis_parts.append(f"신뢰도: {confidence_score:.2%}")
        if reflection.get("concerns"):
            analysis_parts.append(f"우려사항: {', '.join(reflection['concerns'])}")
    if tool_executions:
        executed_tools = [t.get("tool_name", "unknown") for t in tool_executions if t.get("success")]
        if executed_tools:
            analysis_parts.append(f"실행된 Tool: {', '.join(executed_tools)}")

    analysis = "\n".join(analysis_parts) if analysis_parts else "분석 결과 없음"

    # 응답 프롬프트 생성
    respond_prompt = prompts.respond_prompt.format(
        context=context,
        analysis=analysis,
    )

    # 승인 대기 중인 경우 특별 처리
    if pending_approval:
        response = _generate_approval_response(pending_approval, observation)
    else:
        try:
            response = llm_client.generate(
                prompt=respond_prompt,
                system_prompt=prompts.system_prompt,
                temperature=0.5,
                max_tokens=2048,
            )
        except Exception as e:
            logger.error(f"Respond node: LLM 호출 실패 - {e}")
            response = _generate_fallback_response(observation, confidence_score)

    # 메시지 추가
    new_message = AIMessage(content=response)

    logger.info("Respond node: 응답 생성 완료")

    return {
        "messages": [new_message],
        "phase": ChatPhase.RESPONDING.value,
        "response": response,
        "should_continue": False,
    }


def _generate_approval_response(pending_approval: Dict[str, Any], observation: str) -> str:
    """승인 요청 응답 생성."""
    action_type = pending_approval.get("action_type", "unknown")
    confidence = pending_approval.get("confidence", 0.0)
    description = pending_approval.get("description", "")
    expected_impact = pending_approval.get("expected_impact", "")

    response_parts = [
        "분석이 완료되었습니다.",
        "",
        f"**분석 결과:**",
        observation[:500] if observation else "상세 분석 결과 없음",
        "",
        f"**권장 조치:** {action_type}",
        f"**신뢰도:** {confidence:.2%}",
        f"**예상 영향:** {expected_impact}",
        "",
        "이 조치를 실행하시겠습니까?",
        "- [승인]: 권장 조치 실행",
        "- [수정 후 승인]: 파라미터 수정 후 실행",
        "- [거부]: 조치 취소",
        "- [추가 분석 요청]: 더 자세한 분석 수행",
    ]

    return "\n".join(response_parts)


def _generate_fallback_response(observation: str, confidence_score: float) -> str:
    """폴백 응답 생성."""
    if not observation:
        return "요청하신 정보를 조회했습니다. 추가로 궁금한 사항이 있으시면 말씀해 주세요."

    response_parts = [
        "분석 결과를 정리했습니다:",
        "",
        observation[:1000],
        "",
        f"분석 신뢰도: {confidence_score:.2%}",
    ]

    if confidence_score < 0.5:
        response_parts.append("\n신뢰도가 낮아 추가 분석을 권장합니다.")

    response_parts.append("\n추가로 궁금한 사항이 있으시면 말씀해 주세요.")

    return "\n".join(response_parts)


def create_respond_node(llm_client: LLMClient):
    """LLM 클라이언트를 주입한 respond_node 생성."""
    def _respond_node(state: ChatStateDict) -> Dict[str, Any]:
        return respond_node(state, llm_client)
    return _respond_node
