"""
AgentState model for LangGraph workflow.

LangGraph 에이전트의 상태 정의 및 타입.
"""

from typing import TypedDict, Annotated, Sequence, Dict, Any, List, Optional
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """
    LangGraph Agent 상태 정의.

    Attributes:
        messages: LangChain 메시지 시퀀스 (ReAct 대화 히스토리)
        anomaly_data: 감지된 이상 현상 정보
        log_summary: 계층적 요약된 로그
        metrics_data: CloudWatch 메트릭 데이터
        knowledge_base_context: 지식 베이스 검색 결과
        analysis_result: 분석 결과
        confidence_score: 신뢰도 점수 (0.0-1.0)
        remediation_plan: 복구 계획
        iteration_count: 현재 반복 횟수
        max_iterations: 최대 반복 횟수
        tool_results: 도구 실행 결과 누적
        reflection_history: 리플렉션 히스토리
        should_continue: 계속 진행 여부
    """

    # LangChain messages for ReAct conversation
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # Input data
    anomaly_data: Dict[str, Any]
    log_summary: str

    # Collected information
    metrics_data: Optional[Dict[str, Any]]
    knowledge_base_context: Optional[List[Dict[str, Any]]]

    # Analysis results
    analysis_result: Optional[Dict[str, Any]]
    confidence_score: float
    remediation_plan: Optional[Dict[str, Any]]

    # Control flow
    iteration_count: int
    max_iterations: int
    should_continue: bool

    # Tool execution tracking
    tool_results: List[Dict[str, Any]]

    # Reflection tracking
    reflection_history: List[Dict[str, Any]]


class AgentExecutionResult(TypedDict):
    """
    최종 분석 결과 타입.

    Attributes:
        root_cause: 근본 원인 분석
        confidence_score: 신뢰도 점수
        remediation_plan: 복구 계획
        evidence: 근거 데이터
        reasoning: 추론 과정
        requires_human_review: 인간 검토 필요 여부
        review_reason: 검토 필요 이유
    """
    root_cause: str
    confidence_score: float
    remediation_plan: Dict[str, Any]
    evidence: List[str]
    reasoning: str
    requires_human_review: bool
    review_reason: Optional[str]


class ToolResult(TypedDict):
    """
    도구 실행 결과 타입.

    Attributes:
        tool_name: 실행된 도구 이름
        input_params: 입력 파라미터
        output: 실행 결과
        success: 성공 여부
        error_message: 오류 메시지 (실패 시)
    """
    tool_name: str
    input_params: Dict[str, Any]
    output: Any
    success: bool
    error_message: Optional[str]


class ReflectionResult(TypedDict):
    """
    리플렉션 결과 타입.

    Attributes:
        evidence_sufficiency: 근거 충분성 (0.0-1.0)
        logical_consistency: 논리적 일관성 (0.0-1.0)
        actionability: 실행 가능성 (0.0-1.0)
        risk_assessment: 위험 평가 (0.0-1.0)
        overall_confidence: 전체 신뢰도 (0.0-1.0)
        concerns: 우려사항 목록
        should_continue: 계속 진행 여부
        reason: 결정 이유
    """
    evidence_sufficiency: float
    logical_consistency: float
    actionability: float
    risk_assessment: float
    overall_confidence: float
    concerns: List[str]
    should_continue: bool
    reason: str
