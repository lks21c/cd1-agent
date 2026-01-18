"""
Chat Agent - LangGraph 기반 대화형 에이전트.

ReAct + Reflect 패턴을 사용한 멀티턴 대화 에이전트.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langgraph.graph import StateGraph, END

from src.common.chat.state import (
    ChatState, ChatStateDict, ChatPhase, ChatMessage, MessageRole,
    ApprovalStatus, ApprovalRequest
)
from src.common.chat.config import ChatConfig, get_config, get_prompts
from src.common.chat.nodes.plan import create_plan_node
from src.common.chat.nodes.act import create_act_node
from src.common.chat.nodes.observe import create_observe_node
from src.common.chat.nodes.reflect import create_reflect_node
from src.common.chat.nodes.human_review import human_review_node, process_approval_response
from src.common.chat.nodes.respond import create_respond_node
from src.common.services.llm_client import LLMClient, LLMProvider
from src.common.services.aws_client import AWSClient, AWSProvider

logger = logging.getLogger(__name__)


class ChatAgent:
    """
    LangGraph 기반 대화형 에이전트.

    Features:
    - ReAct 패턴: Plan → Act → Observe → Reflect → Respond
    - 멀티턴 대화 지원
    - Human-in-the-loop 승인 프로세스
    - 자체 검증 및 재계획

    Usage:
        agent = ChatAgent()

        # 동기 실행
        response = agent.chat("현재 서비스 상태 알려줘")

        # 비동기 스트리밍
        async for event in agent.stream("spark 네임스페이스 분석해줘"):
            print(event)
    """

    def __init__(
        self,
        llm_provider: LLMProvider = LLMProvider.MOCK,
        aws_provider: AWSProvider = AWSProvider.MOCK,
        config: Optional[ChatConfig] = None,
        tools: Optional[Dict[str, Callable]] = None,
    ):
        """
        ChatAgent 초기화.

        Args:
            llm_provider: LLM 프로바이더
            aws_provider: AWS 프로바이더
            config: Chat 설정
            tools: 사용할 Tool 딕셔너리
        """
        self.config = config or get_config()
        self.prompts = get_prompts()

        # 클라이언트 초기화
        self.llm_client = LLMClient(provider=llm_provider)
        self.aws_client = AWSClient(provider=aws_provider)

        # Tool 등록
        self.tools = tools or self._create_default_tools()

        # 그래프 컴파일
        self.graph = self._build_graph()

        # 세션 상태
        self.session_id = str(uuid.uuid4())[:8]
        self.conversation_history: List[ChatMessage] = []
        self.current_state: Optional[ChatState] = None

        logger.info(f"ChatAgent 초기화 완료 - session: {self.session_id}")

    def _create_default_tools(self) -> Dict[str, Callable]:
        """기본 Tool 생성."""
        from src.common.chat.tools import create_chat_tools
        return create_chat_tools(self.aws_client)

    def _build_graph(self) -> StateGraph:
        """LangGraph StateGraph 구성."""
        graph = StateGraph(ChatStateDict)

        # 노드 생성 (의존성 주입)
        plan_node = create_plan_node(self.llm_client)
        act_node = create_act_node(self.tools)
        observe_node = create_observe_node(self.llm_client)
        reflect_node = create_reflect_node(self.llm_client)
        respond_node = create_respond_node(self.llm_client)

        # 노드 추가
        graph.add_node("plan", plan_node)
        graph.add_node("act", act_node)
        graph.add_node("observe", observe_node)
        graph.add_node("reflect", reflect_node)
        graph.add_node("human_review", human_review_node)
        graph.add_node("respond", respond_node)

        # 엣지 정의
        graph.set_entry_point("plan")
        graph.add_edge("plan", "act")
        graph.add_edge("act", "observe")
        graph.add_edge("observe", "reflect")

        # 조건부 엣지: Reflect 결과에 따라 분기
        graph.add_conditional_edges(
            "reflect",
            self._route_after_reflect,
            {
                "replan": "plan",
                "human_review": "human_review",
                "respond": "respond",
            }
        )

        graph.add_edge("human_review", "respond")
        graph.add_edge("respond", END)

        return graph.compile()

    def _route_after_reflect(self, state: ChatStateDict) -> str:
        """Reflect 후 라우팅 결정."""
        reflection = state.get("reflection", {})
        iteration_count = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", self.config.max_iterations)

        # 최대 반복 횟수 체크
        if iteration_count >= max_iterations:
            logger.info("최대 반복 횟수 도달, 응답으로 이동")
            return "respond"

        # 재계획 필요
        if reflection.get("needs_replan", False):
            logger.info("재계획 필요, plan으로 이동")
            return "replan"

        # 승인 필요
        if reflection.get("needs_human_review", False):
            logger.info("승인 필요, human_review로 이동")
            return "human_review"

        # 응답 가능
        logger.info("분석 완료, respond로 이동")
        return "respond"

    def chat(self, user_input: str) -> str:
        """
        동기 방식 채팅.

        Args:
            user_input: 사용자 입력

        Returns:
            에이전트 응답
        """
        logger.info(f"Chat 시작: {user_input[:50]}...")

        # 대화 히스토리에 추가
        self.conversation_history.append(ChatMessage(
            role=MessageRole.USER,
            content=user_input,
        ))

        # 초기 상태 생성
        initial_state = self._create_initial_state(user_input)

        try:
            # 그래프 실행
            final_state = self.graph.invoke(initial_state)

            # 응답 추출
            response = final_state.get("response", "응답을 생성하지 못했습니다.")

            # 대화 히스토리에 추가
            self.conversation_history.append(ChatMessage(
                role=MessageRole.ASSISTANT,
                content=response,
            ))

            # 현재 상태 저장
            self.current_state = self._state_dict_to_chat_state(final_state)

            logger.info(f"Chat 완료: {response[:50]}...")
            return response

        except Exception as e:
            logger.error(f"Chat 실행 오류: {e}")
            error_response = f"처리 중 오류가 발생했습니다: {str(e)}"
            self.conversation_history.append(ChatMessage(
                role=MessageRole.ASSISTANT,
                content=error_response,
            ))
            return error_response

    async def stream(self, user_input: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        비동기 스트리밍 채팅.

        Args:
            user_input: 사용자 입력

        Yields:
            실행 중 이벤트
        """
        logger.info(f"Stream 시작: {user_input[:50]}...")

        # 대화 히스토리에 추가
        self.conversation_history.append(ChatMessage(
            role=MessageRole.USER,
            content=user_input,
        ))

        # 초기 상태 생성
        initial_state = self._create_initial_state(user_input)

        try:
            # 그래프 스트리밍 실행
            for state_update in self.graph.stream(initial_state):
                # 노드 이름과 상태 추출
                for node_name, node_state in state_update.items():
                    phase = node_state.get("phase", "unknown")

                    event = {
                        "type": "state_update",
                        "node": node_name,
                        "phase": phase,
                        "data": {
                            "iteration": node_state.get("iteration_count", 0),
                            "confidence": node_state.get("confidence_score", 0.0),
                            "tool_executions": len(node_state.get("tool_executions", [])),
                        }
                    }

                    # 특수 이벤트 처리
                    if phase == ChatPhase.HUMAN_REVIEW.value:
                        event["type"] = "approval_request"
                        event["approval"] = node_state.get("pending_approval")
                    elif phase == ChatPhase.RESPONDING.value:
                        event["type"] = "response"
                        event["response"] = node_state.get("response")

                    yield event

                    # 현재 상태 저장
                    self.current_state = self._state_dict_to_chat_state(node_state)

            # 최종 응답 추가
            if self.current_state and self.current_state.response:
                self.conversation_history.append(ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=self.current_state.response,
                ))

        except Exception as e:
            logger.error(f"Stream 실행 오류: {e}")
            yield {
                "type": "error",
                "error": str(e),
            }

    def handle_approval(
        self,
        status: ApprovalStatus,
        user_feedback: Optional[str] = None,
        modified_parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Human-in-the-loop 승인 처리.

        Args:
            status: 승인 상태
            user_feedback: 사용자 피드백
            modified_parameters: 수정된 파라미터

        Returns:
            처리 결과 응답
        """
        if not self.current_state or not self.current_state.pending_approval:
            return "대기 중인 승인 요청이 없습니다."

        logger.info(f"승인 처리: {status.value}")

        # 현재 상태를 StateDict로 변환
        current_state_dict = self._chat_state_to_state_dict(self.current_state)

        # 승인 응답 처리
        updated_fields = process_approval_response(
            current_state_dict,
            status,
            user_feedback,
            modified_parameters,
        )

        # 상태 업데이트
        for key, value in updated_fields.items():
            if hasattr(self.current_state, key):
                setattr(self.current_state, key, value)

        # 승인된 경우 조치 실행
        if status in [ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED]:
            return self._execute_approved_action(modified_parameters)

        return "조치가 거부되었습니다. 추가로 필요한 사항이 있으시면 말씀해 주세요."

    def _execute_approved_action(self, modified_parameters: Optional[Dict[str, Any]] = None) -> str:
        """승인된 조치 실행."""
        # TODO: 실제 조치 실행 로직 구현
        return "조치가 승인되어 실행되었습니다. 결과를 모니터링 중입니다."

    def _create_initial_state(self, user_input: str) -> ChatStateDict:
        """초기 상태 생성."""
        # 대화 히스토리를 LangChain 메시지로 변환
        messages: List[BaseMessage] = [
            SystemMessage(content=self.prompts.system_prompt),
        ]

        # 최근 대화 추가 (컨텍스트 유지)
        for msg in self.conversation_history[-10:]:
            if msg.role == MessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                # AIMessage import 추가 필요
                from langchain_core.messages import AIMessage
                messages.append(AIMessage(content=msg.content))

        # 현재 입력 추가
        messages.append(HumanMessage(content=user_input))

        return {
            "messages": messages,
            "user_input": user_input,
            "phase": ChatPhase.IDLE.value,
            "current_plan": None,
            "tool_executions": [],
            "observation": None,
            "analysis_result": None,
            "reflection": None,
            "confidence_score": 0.0,
            "pending_approval": None,
            "iteration_count": 0,
            "max_iterations": self.config.max_iterations,
            "should_continue": True,
            "response": None,
            "session_id": self.session_id,
        }

    def _state_dict_to_chat_state(self, state_dict: ChatStateDict) -> ChatState:
        """StateDict를 ChatState로 변환."""
        state = ChatState()
        state.user_input = state_dict.get("user_input", "")
        state.phase = ChatPhase(state_dict.get("phase", "idle"))
        state.current_plan = state_dict.get("current_plan")
        state.observation = state_dict.get("observation")
        state.analysis_result = state_dict.get("analysis_result")
        state.confidence_score = state_dict.get("confidence_score", 0.0)
        state.iteration_count = state_dict.get("iteration_count", 0)
        state.max_iterations = state_dict.get("max_iterations", 5)
        state.should_continue = state_dict.get("should_continue", True)
        state.response = state_dict.get("response")
        state.session_id = state_dict.get("session_id", "")

        # tool_executions 변환
        for te in state_dict.get("tool_executions", []):
            from src.common.chat.state import ToolExecution
            state.tool_executions.append(ToolExecution(**te) if isinstance(te, dict) else te)

        # reflection 변환
        if state_dict.get("reflection"):
            from src.common.chat.state import ReflectionResult
            ref_data = state_dict["reflection"]
            state.reflection = ReflectionResult(**ref_data) if isinstance(ref_data, dict) else ref_data

        # pending_approval 변환
        if state_dict.get("pending_approval"):
            from src.common.chat.state import ApprovalRequest
            approval_data = state_dict["pending_approval"]
            if isinstance(approval_data, dict):
                state.pending_approval = ApprovalRequest(
                    request_id=approval_data.get("request_id", ""),
                    action_type=approval_data.get("action_type", ""),
                    description=approval_data.get("description", ""),
                    parameters=approval_data.get("parameters", {}),
                    confidence=approval_data.get("confidence", 0.0),
                    expected_impact=approval_data.get("expected_impact", ""),
                )

        return state

    def _chat_state_to_state_dict(self, state: ChatState) -> ChatStateDict:
        """ChatState를 StateDict로 변환."""
        return {
            "messages": state.langchain_messages,
            "user_input": state.user_input,
            "phase": state.phase.value,
            "current_plan": state.current_plan,
            "tool_executions": [te.to_dict() if hasattr(te, 'to_dict') else te for te in state.tool_executions],
            "observation": state.observation,
            "analysis_result": state.analysis_result,
            "reflection": state.reflection.to_dict() if state.reflection else None,
            "confidence_score": state.confidence_score,
            "pending_approval": state.pending_approval.to_dict() if state.pending_approval else None,
            "iteration_count": state.iteration_count,
            "max_iterations": state.max_iterations,
            "should_continue": state.should_continue,
            "response": state.response,
            "session_id": state.session_id,
        }

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """대화 히스토리 반환."""
        return [msg.to_dict() for msg in self.conversation_history]

    def clear_history(self):
        """대화 히스토리 초기화."""
        self.conversation_history.clear()
        self.current_state = None
        logger.info(f"대화 히스토리 초기화 - session: {self.session_id}")

    def get_status(self) -> Dict[str, Any]:
        """현재 상태 요약 반환."""
        return {
            "session_id": self.session_id,
            "conversation_length": len(self.conversation_history),
            "current_phase": self.current_state.phase.value if self.current_state else "idle",
            "has_pending_approval": bool(self.current_state and self.current_state.pending_approval),
            "last_confidence": self.current_state.confidence_score if self.current_state else 0.0,
        }
