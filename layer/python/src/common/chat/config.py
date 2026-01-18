"""
Chat Configuration.

대화형 에이전트 설정.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ChatConfig:
    """Chat 설정."""

    # 서버 설정
    streamlit_port: int = field(default_factory=lambda: int(os.getenv("STREAMLIT_PORT", "8501")))

    # 세션 설정
    session_timeout_minutes: int = field(default_factory=lambda: int(os.getenv("CHAT_SESSION_TIMEOUT", "30")))
    max_history_messages: int = field(default_factory=lambda: int(os.getenv("CHAT_MAX_HISTORY", "100")))

    # 에이전트 설정
    max_iterations: int = field(default_factory=lambda: int(os.getenv("CHAT_MAX_ITERATIONS", "5")))
    confidence_threshold: float = field(default_factory=lambda: float(os.getenv("CHAT_CONFIDENCE_THRESHOLD", "0.5")))

    # Human-in-the-loop 설정
    approval_timeout_minutes: int = field(default_factory=lambda: int(os.getenv("CHAT_APPROVAL_TIMEOUT", "10")))
    require_approval_for_actions: bool = True

    # UI 설정
    show_thinking_process: bool = True
    show_tool_executions: bool = True
    enable_quick_actions: bool = True

    # Quick Actions 목록
    quick_actions: List[str] = field(default_factory=lambda: [
        "자원 현황",
        "최근 이상 징후",
        "비용 분석",
        "설정 검사",
    ])


@dataclass
class PromptTemplates:
    """프롬프트 템플릿."""

    system_prompt: str = """당신은 AWS 및 Kubernetes 인프라 전문가입니다.
사용자의 질문에 정확하고 도움이 되는 답변을 제공합니다.

역할:
- 자원 현황 조회 및 설명
- 이상 징후 분석 및 근본 원인 파악
- 복구 조치 제안 및 실행 지원
- Human-in-the-loop 승인 프로세스 지원

원칙:
- 항상 증거에 기반한 분석을 제공합니다
- 불확실한 경우 명확히 밝힙니다
- 위험한 조치는 반드시 사용자 승인을 요청합니다
- 한국어로 응답합니다"""

    plan_prompt: str = """현재 대화 컨텍스트:
{context}

사용자 요청: {user_input}

다음을 수행하세요:
1. 사용자 요청 분석
2. 필요한 정보 수집 계획 수립
3. 사용할 도구 결정

계획을 JSON 형식으로 출력하세요:
{{
    "intent": "사용자 의도 요약",
    "steps": ["단계1", "단계2", ...],
    "tools_needed": ["tool1", "tool2", ...],
    "confidence": 0.0-1.0
}}"""

    reflect_prompt: str = """분석 결과를 검토하세요:

계획: {plan}
실행 결과: {observation}

다음을 평가하세요:
1. 분석이 충분한가? (정보 누락 여부)
2. 결론이 논리적인가? (인과관계 검증)
3. 추가 조사가 필요한가?
4. 사용자 승인이 필요한 조치인가?

응답 형식:
{{
    "confidence": 0.0-1.0,
    "needs_replan": true/false,
    "needs_human_review": true/false,
    "reasoning": "평가 근거",
    "concerns": ["우려사항1", ...]
}}"""

    respond_prompt: str = """대화 컨텍스트:
{context}

분석 결과:
{analysis}

사용자에게 친절하고 명확하게 응답하세요.
- 핵심 정보를 먼저 제공
- 필요시 추가 질문 유도
- 조치가 필요한 경우 승인 요청"""


def get_config() -> ChatConfig:
    """설정 객체 반환."""
    return ChatConfig()


def get_prompts() -> PromptTemplates:
    """프롬프트 템플릿 반환."""
    return PromptTemplates()
