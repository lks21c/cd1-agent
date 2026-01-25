"""
Notification Router for Multi-Backend Support.

환경에 따라 적절한 알림 백엔드를 자동 선택.

Architecture:
- 내부망 (현대카드): EventBridge → 현대카드 커스텀 모듈
- Public 테스트: KakaoTalk 나에게 보내기
- Mock 테스트: 메모리 저장

Usage:
    router = NotificationRouter.from_env()
    router.send_alert(result, summary)
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from src.agents.bdp_cost.services.anomaly_detector import CostDriftResult
from src.agents.bdp_cost.services.summary_generator import AlertSummary

logger = logging.getLogger(__name__)


class NotificationBackend(str, Enum):
    """알림 백엔드 종류."""

    EVENTBRIDGE = "eventbridge"  # 내부망 - EventBridge
    KAKAO = "kakao"  # Public - 카카오톡 나에게 보내기
    SLACK = "slack"  # Public - Slack Webhook (향후)
    MOCK = "mock"  # 테스트용


@dataclass
class NotificationResult:
    """알림 발송 결과."""

    success: bool
    backend: NotificationBackend
    message: Optional[str] = None
    error: Optional[str] = None


class BaseNotifier(ABC):
    """알림 발송기 베이스 클래스."""

    @abstractmethod
    def send_alert(
        self,
        result: CostDriftResult,
        summary: AlertSummary,
        hitl_request_id: Optional[str] = None,
    ) -> bool:
        """알람 발송.

        Args:
            result: 비용 드리프트 탐지 결과
            summary: 알람 요약
            hitl_request_id: HITL 요청 ID (있는 경우)

        Returns:
            발송 성공 여부
        """
        pass


class NotificationRouter:
    """
    알림 라우터.

    환경 변수에 따라 적절한 알림 백엔드를 선택하여 발송.

    Environment Variables:
        NOTIFICATION_BACKEND: eventbridge | kakao | slack | mock
        - 미설정 시 자동 감지 (내부망/Public)

    Examples:
        # 환경변수로 자동 선택
        router = NotificationRouter.from_env()
        router.send_alert(result, summary)

        # 명시적 백엔드 지정
        router = NotificationRouter(backend=NotificationBackend.KAKAO)
        router.send_alert(result, summary)
    """

    def __init__(
        self,
        backend: Optional[NotificationBackend] = None,
        fallback_backend: Optional[NotificationBackend] = None,
    ):
        """NotificationRouter 초기화.

        Args:
            backend: 주 알림 백엔드 (None이면 자동 감지)
            fallback_backend: 실패 시 대체 백엔드
        """
        self.backend = backend or self._detect_backend()
        self.fallback_backend = fallback_backend
        self._notifier: Optional[BaseNotifier] = None
        self._fallback_notifier: Optional[BaseNotifier] = None

        logger.info(
            f"NotificationRouter initialized: backend={self.backend.value}, "
            f"fallback={self.fallback_backend.value if self.fallback_backend else 'None'}"
        )

    @classmethod
    def from_env(cls) -> "NotificationRouter":
        """환경변수에서 설정을 읽어 라우터 생성.

        Returns:
            NotificationRouter 인스턴스
        """
        backend_str = os.getenv("NOTIFICATION_BACKEND", "").lower()
        fallback_str = os.getenv("NOTIFICATION_FALLBACK", "").lower()

        backend = None
        if backend_str:
            try:
                backend = NotificationBackend(backend_str)
            except ValueError:
                logger.warning(f"Unknown backend: {backend_str}, using auto-detect")

        fallback = None
        if fallback_str:
            try:
                fallback = NotificationBackend(fallback_str)
            except ValueError:
                logger.warning(f"Unknown fallback: {fallback_str}")

        return cls(backend=backend, fallback_backend=fallback)

    def _detect_backend(self) -> NotificationBackend:
        """환경에 따라 적절한 백엔드 자동 감지.

        Returns:
            감지된 NotificationBackend
        """
        # Mock 모드 확인
        if os.getenv("NOTIFICATION_BACKEND", "").lower() == "mock":
            return NotificationBackend.MOCK

        # EventBridge 설정 확인 (내부망)
        event_bus = os.getenv("EVENT_BUS")
        if event_bus or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
            return NotificationBackend.EVENTBRIDGE

        # 카카오톡 토큰 확인 (Public)
        kakao_key = os.getenv("KAKAO_REST_API_KEY")
        if kakao_key:
            return NotificationBackend.KAKAO

        # 기본값: Mock
        logger.warning("No notification backend configured, using mock")
        return NotificationBackend.MOCK

    @property
    def notifier(self) -> BaseNotifier:
        """주 알림 발송기 (lazy initialization)."""
        if self._notifier is None:
            self._notifier = self._create_notifier(self.backend)
        return self._notifier

    @property
    def fallback_notifier(self) -> Optional[BaseNotifier]:
        """대체 알림 발송기 (lazy initialization)."""
        if self.fallback_backend and self._fallback_notifier is None:
            self._fallback_notifier = self._create_notifier(self.fallback_backend)
        return self._fallback_notifier

    def _create_notifier(self, backend: NotificationBackend) -> BaseNotifier:
        """백엔드에 맞는 알림 발송기 생성.

        Args:
            backend: 알림 백엔드 종류

        Returns:
            BaseNotifier 구현체
        """
        if backend == NotificationBackend.EVENTBRIDGE:
            return EventBridgeNotifier()
        elif backend == NotificationBackend.KAKAO:
            return KakaoTalkNotifier()
        elif backend == NotificationBackend.SLACK:
            return SlackNotifier()
        elif backend == NotificationBackend.MOCK:
            return MockNotifier()
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def send_alert(
        self,
        result: CostDriftResult,
        summary: AlertSummary,
        hitl_request_id: Optional[str] = None,
    ) -> NotificationResult:
        """알람 발송.

        주 백엔드로 발송 시도, 실패 시 fallback 백엔드로 재시도.

        Args:
            result: 비용 드리프트 탐지 결과
            summary: 알람 요약
            hitl_request_id: HITL 요청 ID

        Returns:
            NotificationResult 발송 결과
        """
        # 주 백엔드 시도
        try:
            success = self.notifier.send_alert(result, summary, hitl_request_id)
            if success:
                return NotificationResult(
                    success=True,
                    backend=self.backend,
                    message=f"Alert sent via {self.backend.value}",
                )
        except Exception as e:
            logger.error(f"Primary notification failed ({self.backend.value}): {e}")

        # Fallback 시도
        if self.fallback_notifier:
            try:
                success = self.fallback_notifier.send_alert(
                    result, summary, hitl_request_id
                )
                if success:
                    return NotificationResult(
                        success=True,
                        backend=self.fallback_backend,
                        message=f"Alert sent via fallback {self.fallback_backend.value}",
                    )
            except Exception as e:
                logger.error(
                    f"Fallback notification failed ({self.fallback_backend.value}): {e}"
                )

        return NotificationResult(
            success=False,
            backend=self.backend,
            error="All notification backends failed",
        )

    def send_batch_alert(
        self,
        results: List[CostDriftResult],
        summary: AlertSummary,
        hitl_request_id: Optional[str] = None,
    ) -> NotificationResult:
        """일괄 알람 발송.

        Args:
            results: 비용 드리프트 탐지 결과 목록
            summary: 통합 알람 요약
            hitl_request_id: HITL 요청 ID

        Returns:
            NotificationResult 발송 결과
        """
        # EventBridge는 batch 지원
        if self.backend == NotificationBackend.EVENTBRIDGE:
            from src.agents.bdp_cost.services.event_publisher import EventPublisher

            publisher = EventPublisher()
            success = publisher.publish_batch_alert(results, summary, hitl_request_id)
            return NotificationResult(
                success=success,
                backend=self.backend,
                message="Batch alert sent" if success else "Batch alert failed",
            )

        # 다른 백엔드는 개별 발송
        anomalies = [r for r in results if r.is_anomaly]
        if not anomalies:
            return NotificationResult(
                success=True,
                backend=self.backend,
                message="No anomalies to send",
            )

        # 가장 심각한 것만 발송 (또는 summary 사용)
        top_result = max(anomalies, key=lambda r: r.confidence_score)
        return self.send_alert(top_result, summary, hitl_request_id)


# =============================================================================
# Backend Implementations
# =============================================================================


class EventBridgeNotifier(BaseNotifier):
    """EventBridge 알림 발송기."""

    def __init__(self):
        from src.agents.bdp_cost.services.event_publisher import EventPublisher

        self._publisher = EventPublisher()

    def send_alert(
        self,
        result: CostDriftResult,
        summary: AlertSummary,
        hitl_request_id: Optional[str] = None,
    ) -> bool:
        return self._publisher.publish_alert(result, summary, hitl_request_id)


class KakaoTalkNotifier(BaseNotifier):
    """카카오톡 나에게 보내기 알림 발송기."""

    def __init__(self):
        from src.agents.bdp_cost.services.kakao_notifier import KakaoNotifier

        self._notifier = KakaoNotifier()
        if not self._notifier.load_tokens():
            logger.warning(
                "Kakao tokens not found. "
                "Run 'python -m src.agents.bdp_cost.services.kakao_notifier' to set up."
            )

    def send_alert(
        self,
        result: CostDriftResult,
        summary: AlertSummary,
        hitl_request_id: Optional[str] = None,
    ) -> bool:
        return self._notifier.send_alert(result, summary)


class SlackNotifier(BaseNotifier):
    """Slack Webhook 알림 발송기 (향후 구현)."""

    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not set")

    def send_alert(
        self,
        result: CostDriftResult,
        summary: AlertSummary,
        hitl_request_id: Optional[str] = None,
    ) -> bool:
        if not self.webhook_url:
            return False

        import requests

        severity_emoji = {
            "critical": "🚨",
            "high": "⚠️",
            "medium": "📊",
            "low": "ℹ️",
        }
        emoji = severity_emoji.get(result.severity.value, "📊")

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {summary.title}",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": summary.message,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*현재 비용:*\n{result.current_cost:,.0f}원",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*변화율:*\n{result.change_percent:+.1f}%",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*신뢰도:*\n{result.confidence_score:.1%}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*심각도:*\n{result.severity.value.upper()}",
                        },
                    ],
                },
            ],
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
            return False


class MockNotifier(BaseNotifier):
    """테스트용 Mock 알림 발송기."""

    def __init__(self):
        self.sent_alerts: List[dict] = []

    def send_alert(
        self,
        result: CostDriftResult,
        summary: AlertSummary,
        hitl_request_id: Optional[str] = None,
    ) -> bool:
        self.sent_alerts.append(
            {
                "result": result,
                "summary": summary,
                "hitl_request_id": hitl_request_id,
            }
        )
        logger.info(f"[MOCK] Alert sent: {summary.title}")
        return True

    def get_sent_alerts(self) -> List[dict]:
        """발송된 알람 목록 조회."""
        return self.sent_alerts.copy()

    def clear(self) -> None:
        """발송 기록 초기화."""
        self.sent_alerts.clear()
