"""
CD1 Agent Interactive Chat Module.

LangGraph 기반 대화형 에이전트 백엔드 라이브러리.

사용법:
    from src.common.chat import ChatAgent
    from src.common.services.llm_client import LLMProvider
    from src.common.services.aws_client import AWSProvider

    agent = ChatAgent(
        llm_provider=LLMProvider.GEMINI,
        aws_provider=AWSProvider.REAL,
    )

    response = agent.chat("현재 서비스 상태 알려줘")
"""

from src.common.chat.agent import ChatAgent
from src.common.chat.state import (
    ChatState,
    ChatStateDict,
    ChatMessage,
    MessageRole,
    ChatPhase,
    ToolExecution,
    ReflectionResult,
    ApprovalRequest,
    ApprovalStatus,
)
from src.common.chat.config import ChatConfig, get_config, get_prompts

__all__ = [
    # Agent
    "ChatAgent",
    # State
    "ChatState",
    "ChatStateDict",
    "ChatMessage",
    "MessageRole",
    "ChatPhase",
    "ToolExecution",
    "ReflectionResult",
    "ApprovalRequest",
    "ApprovalStatus",
    # Config
    "ChatConfig",
    "get_config",
    "get_prompts",
]
