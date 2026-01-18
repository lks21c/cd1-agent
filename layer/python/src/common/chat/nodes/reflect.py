"""
Reflect Node - 자체 검증 및 신뢰도 평가.
"""

import json
import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.common.chat.state import ChatStateDict, ChatPhase, ReflectionResult
from src.common.chat.config import get_prompts, get_config
from src.common.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def reflect_node(state: ChatStateDict, llm_client: LLMClient) -> Dict[str, Any]:
    """
    분석 결과를 자체 검증하고 신뢰도를 평가합니다.

    Args:
        state: 현재 상태
        llm_client: LLM 클라이언트

    Returns:
        업데이트된 상태 필드
    """
    logger.info("Reflect node: 자체 검증 중...")

    prompts = get_prompts()
    config = get_config()

    current_plan = state.get("current_plan", "")
    observation = state.get("observation", "")
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", config.max_iterations)

    # Reflection 프롬프트 생성
    reflect_prompt = prompts.reflect_prompt.format(
        plan=current_plan,
        observation=observation,
    )

    try:
        response = llm_client.generate(
            prompt=reflect_prompt,
            temperature=0.3,
            max_tokens=1024,
        )

        # JSON 파싱
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            reflection_data = json.loads(json_str)

        except json.JSONDecodeError:
            logger.warning("Reflect node: JSON 파싱 실패, 기본값 사용")
            reflection_data = {
                "confidence": 0.6,
                "needs_replan": False,
                "needs_human_review": False,
                "reasoning": response,
                "concerns": [],
            }

    except Exception as e:
        logger.error(f"Reflect node: LLM 호출 실패 - {e}")
        reflection_data = {
            "confidence": 0.5,
            "needs_replan": False,
            "needs_human_review": True,
            "reasoning": f"검증 실패: {str(e)}",
            "concerns": ["LLM 호출 오류"],
        }

    # 반복 횟수 초과 체크
    if iteration_count >= max_iterations:
        reflection_data["needs_replan"] = False
        reflection_data["concerns"].append("최대 반복 횟수 도달")
        logger.warning(f"Reflect node: 최대 반복 횟수 도달 ({iteration_count}/{max_iterations})")

    # 신뢰도 임계값 체크
    confidence = reflection_data.get("confidence", 0.5)
    if confidence < config.confidence_threshold:
        reflection_data["needs_human_review"] = True
        reflection_data["concerns"].append(f"신뢰도 낮음 ({confidence:.2f} < {config.confidence_threshold})")

    # Reflection 결과 저장
    reflection = {
        "confidence": confidence,
        "needs_replan": reflection_data.get("needs_replan", False),
        "needs_human_review": reflection_data.get("needs_human_review", False),
        "reasoning": reflection_data.get("reasoning", ""),
        "concerns": reflection_data.get("concerns", []),
    }

    # 계속 진행 여부 결정
    should_continue = not (
        reflection["needs_replan"] or
        reflection["needs_human_review"] or
        iteration_count >= max_iterations
    )

    # 메시지 추가
    concerns_str = ", ".join(reflection["concerns"]) if reflection["concerns"] else "없음"
    new_message = AIMessage(
        content=f"[검증] 신뢰도: {confidence:.2%}, 재계획 필요: {reflection['needs_replan']}, "
                f"승인 필요: {reflection['needs_human_review']}, 우려사항: {concerns_str}"
    )

    logger.info(f"Reflect node: 검증 완료 - 신뢰도 {confidence:.2%}")

    return {
        "messages": [new_message],
        "phase": ChatPhase.REFLECTING.value,
        "reflection": reflection,
        "confidence_score": confidence,
        "should_continue": should_continue,
    }


def create_reflect_node(llm_client: LLMClient):
    """LLM 클라이언트를 주입한 reflect_node 생성."""
    def _reflect_node(state: ChatStateDict) -> Dict[str, Any]:
        return reflect_node(state, llm_client)
    return _reflect_node
