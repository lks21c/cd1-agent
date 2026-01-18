"""
Human Review Node - Human-in-the-loop 승인 처리.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage

from src.common.chat.state import ChatStateDict, ChatPhase, ApprovalStatus

logger = logging.getLogger(__name__)


def human_review_node(state: ChatStateDict) -> Dict[str, Any]:
    """
    Human-in-the-loop 승인 요청을 생성합니다.

    Args:
        state: 현재 상태

    Returns:
        업데이트된 상태 필드
    """
    logger.info("Human Review node: 승인 요청 생성 중...")

    reflection = state.get("reflection", {})
    observation = state.get("observation", "")
    confidence_score = state.get("confidence_score", 0.0)
    current_plan = state.get("current_plan", "")

    # 승인 요청 생성
    request_id = str(uuid.uuid4())[:8]

    # 분석 결과에서 조치 추출
    action_type = _extract_action_type(observation, current_plan)
    parameters = _extract_action_parameters(observation, current_plan)

    pending_approval = {
        "request_id": request_id,
        "action_type": action_type,
        "description": _generate_approval_description(observation, reflection),
        "parameters": parameters,
        "confidence": confidence_score,
        "expected_impact": _estimate_impact(action_type, parameters),
        "status": ApprovalStatus.PENDING.value,
        "user_feedback": None,
        "modified_parameters": None,
        "created_at": datetime.utcnow().isoformat(),
        "resolved_at": None,
    }

    # 메시지 추가
    new_message = AIMessage(
        content=f"[승인 요청] {action_type} 조치에 대한 승인이 필요합니다.\n"
                f"신뢰도: {confidence_score:.2%}\n"
                f"설명: {pending_approval['description'][:200]}..."
    )

    logger.info(f"Human Review node: 승인 요청 생성 완료 - {request_id}")

    return {
        "messages": [new_message],
        "phase": ChatPhase.HUMAN_REVIEW.value,
        "pending_approval": pending_approval,
        "should_continue": False,  # 승인 대기 중 일시 정지
    }


def process_approval_response(
    state: ChatStateDict,
    status: ApprovalStatus,
    user_feedback: Optional[str] = None,
    modified_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    사용자 승인 응답을 처리합니다.

    Args:
        state: 현재 상태
        status: 승인 상태
        user_feedback: 사용자 피드백
        modified_parameters: 수정된 파라미터

    Returns:
        업데이트된 상태 필드
    """
    logger.info(f"Human Review: 승인 응답 처리 - {status.value}")

    pending_approval = state.get("pending_approval", {})

    if not pending_approval:
        logger.warning("Human Review: 대기 중인 승인 요청 없음")
        return {"should_continue": True}

    # 승인 상태 업데이트
    pending_approval["status"] = status.value
    pending_approval["user_feedback"] = user_feedback
    pending_approval["modified_parameters"] = modified_parameters
    pending_approval["resolved_at"] = datetime.utcnow().isoformat()

    # 승인 히스토리에 추가
    approval_history = list(state.get("approval_history", []))
    approval_history.append(pending_approval)

    # 응답에 따른 처리
    if status == ApprovalStatus.APPROVED:
        message_content = f"[승인 완료] 조치가 승인되었습니다."
        should_continue = True
    elif status == ApprovalStatus.MODIFIED:
        message_content = f"[수정 승인] 조치가 수정 후 승인되었습니다.\n피드백: {user_feedback}"
        should_continue = True
    else:  # REJECTED
        message_content = f"[거부됨] 조치가 거부되었습니다.\n피드백: {user_feedback}"
        should_continue = False

    new_message = AIMessage(content=message_content)

    return {
        "messages": [new_message],
        "pending_approval": None,  # 처리 완료
        "approval_history": approval_history,
        "should_continue": should_continue,
    }


def _extract_action_type(observation: str, plan: str) -> str:
    """관찰 결과에서 조치 유형 추출."""
    observation_lower = observation.lower()

    if "restart" in observation_lower or "재시작" in observation:
        return "pod_restart"
    elif "memory" in observation_lower or "메모리" in observation:
        return "resource_adjustment"
    elif "scaling" in observation_lower or "스케일" in observation:
        return "auto_scaling"
    elif "error" in observation_lower or "오류" in observation:
        return "investigate"
    else:
        return "notify"


def _extract_action_parameters(observation: str, plan: str) -> Dict[str, Any]:
    """관찰 결과에서 조치 파라미터 추출."""
    # 기본 파라미터
    return {
        "target": "unknown",
        "action": "investigate",
        "reason": observation[:200] if observation else "분석 결과 기반",
    }


def _generate_approval_description(observation: str, reflection: Dict[str, Any]) -> str:
    """승인 요청 설명 생성."""
    concerns = reflection.get("concerns", [])
    reasoning = reflection.get("reasoning", "")

    parts = []
    if observation:
        parts.append(f"분석 결과: {observation[:200]}")
    if reasoning:
        parts.append(f"근거: {reasoning[:200]}")
    if concerns:
        parts.append(f"우려사항: {', '.join(concerns)}")

    return "\n".join(parts) if parts else "추가 조치 필요"


def _estimate_impact(action_type: str, parameters: Dict[str, Any]) -> str:
    """조치의 예상 영향 추정."""
    impact_map = {
        "pod_restart": "Pod 재시작 시 일시적 서비스 중단 가능",
        "resource_adjustment": "리소스 조정 후 Pod 재시작 필요",
        "auto_scaling": "인스턴스 수 변경에 따른 비용 영향",
        "investigate": "영향 없음 - 조사만 수행",
        "notify": "영향 없음 - 알림만 발송",
    }
    return impact_map.get(action_type, "영향도 평가 필요")
