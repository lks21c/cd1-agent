"""
Chat State definitions for Interactive Chat Interface.

대화형 에이전트의 상태 관리를 위한 모델 정의.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Annotated
from langchain_core.messages import BaseMessage
import operator


class MessageRole(str, Enum):
    """메시지 역할."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatPhase(str, Enum):
    """Chat 에이전트 실행 단계."""
    IDLE = "idle"
    PLANNING = "planning"
    ACTING = "acting"
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    HUMAN_REVIEW = "human_review"
    RESPONDING = "responding"


class ApprovalStatus(str, Enum):
    """승인 상태."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


@dataclass
class ChatMessage:
    """대화 메시지."""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ToolExecution:
    """Tool 실행 결과."""
    tool_name: str
    input_params: Dict[str, Any]
    output: Any
    success: bool
    error_message: Optional[str] = None
    execution_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "input_params": self.input_params,
            "output": self.output,
            "success": self.success,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class ReflectionResult:
    """자체 검증 결과."""
    confidence: float
    needs_replan: bool
    needs_human_review: bool
    reasoning: str
    concerns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidence": self.confidence,
            "needs_replan": self.needs_replan,
            "needs_human_review": self.needs_human_review,
            "reasoning": self.reasoning,
            "concerns": self.concerns,
        }


@dataclass
class ApprovalRequest:
    """Human-in-the-loop 승인 요청."""
    request_id: str
    action_type: str
    description: str
    parameters: Dict[str, Any]
    confidence: float
    expected_impact: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    user_feedback: Optional[str] = None
    modified_parameters: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action_type": self.action_type,
            "description": self.description,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "expected_impact": self.expected_impact,
            "status": self.status.value,
            "user_feedback": self.user_feedback,
            "modified_parameters": self.modified_parameters,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class ChatState:
    """
    Chat 에이전트 상태.

    LangGraph StateGraph에서 사용되는 상태 객체.
    """
    # 대화 히스토리
    messages: List[ChatMessage] = field(default_factory=list)
    langchain_messages: List[BaseMessage] = field(default_factory=list)

    # 현재 사용자 입력
    user_input: str = ""

    # 에이전트 실행 상태
    phase: ChatPhase = ChatPhase.IDLE
    current_plan: Optional[str] = None

    # Tool 실행 결과
    tool_executions: List[ToolExecution] = field(default_factory=list)

    # 분석 결과
    observation: Optional[str] = None
    analysis_result: Optional[Dict[str, Any]] = None

    # 자체 검증
    reflection: Optional[ReflectionResult] = None
    confidence_score: float = 0.0

    # Human-in-the-loop
    pending_approval: Optional[ApprovalRequest] = None
    approval_history: List[ApprovalRequest] = field(default_factory=list)

    # 제어 흐름
    iteration_count: int = 0
    max_iterations: int = 5
    should_continue: bool = True

    # 응답
    response: Optional[str] = None

    # 메타데이터
    session_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def add_message(self, role: MessageRole, content: str, metadata: Optional[Dict[str, Any]] = None):
        """메시지 추가."""
        msg = ChatMessage(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(msg)

    def add_tool_execution(self, execution: ToolExecution):
        """Tool 실행 결과 추가."""
        self.tool_executions.append(execution)

    def get_conversation_context(self, max_messages: int = 10) -> str:
        """대화 컨텍스트 문자열 생성."""
        recent_messages = self.messages[-max_messages:]
        context_parts = []
        for msg in recent_messages:
            role_label = {
                MessageRole.USER: "User",
                MessageRole.ASSISTANT: "Assistant",
                MessageRole.SYSTEM: "System",
                MessageRole.TOOL: "Tool",
            }.get(msg.role, "Unknown")
            context_parts.append(f"{role_label}: {msg.content}")
        return "\n".join(context_parts)

    def to_dict(self) -> Dict[str, Any]:
        """상태를 딕셔너리로 변환."""
        return {
            "messages": [m.to_dict() for m in self.messages],
            "user_input": self.user_input,
            "phase": self.phase.value,
            "current_plan": self.current_plan,
            "tool_executions": [t.to_dict() for t in self.tool_executions],
            "observation": self.observation,
            "analysis_result": self.analysis_result,
            "reflection": self.reflection.to_dict() if self.reflection else None,
            "confidence_score": self.confidence_score,
            "pending_approval": self.pending_approval.to_dict() if self.pending_approval else None,
            "iteration_count": self.iteration_count,
            "max_iterations": self.max_iterations,
            "should_continue": self.should_continue,
            "response": self.response,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
        }


# LangGraph TypedDict 형태 (기존 AgentState와 호환)
from typing import TypedDict


class ChatStateDict(TypedDict):
    """LangGraph용 TypedDict 상태."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_input: str
    phase: str
    current_plan: Optional[str]
    tool_executions: List[Dict[str, Any]]
    observation: Optional[str]
    analysis_result: Optional[Dict[str, Any]]
    reflection: Optional[Dict[str, Any]]
    confidence_score: float
    pending_approval: Optional[Dict[str, Any]]
    iteration_count: int
    max_iterations: int
    should_continue: bool
    response: Optional[str]
    session_id: str
