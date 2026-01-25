"""
EventBridge Publisher for KakaoTalk Alerts.

EventBridge를 통한 KakaoTalk 알람 발송을 위한 이벤트 발행기.
Production: 현대카드 커스텀 모듈 연동
Development: LocalStack 에뮬레이션
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from bdp_cost.services.anomaly_detector import CostDriftResult, Severity
from bdp_cost.services.summary_generator import AlertSummary

logger = logging.getLogger(__name__)


@dataclass
class AlertEvent:
    """EventBridge 알람 이벤트 구조."""

    alert_type: str  # cost_drift
    severity: str  # emoji
    severity_level: str  # critical, high, medium, low
    title: str
    message: str
    affected_services: List[Dict[str, Any]]
    action_required: bool
    hitl_request_id: Optional[str] = None
    detection_timestamp: str = ""
    account_names: List[str] = None

    def __post_init__(self):
        if not self.detection_timestamp:
            self.detection_timestamp = datetime.utcnow().isoformat()
        if self.account_names is None:
            self.account_names = []

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return asdict(self)


class EventPublisher:
    """
    EventBridge 이벤트 발행기.

    KakaoTalk 알람을 위한 EventBridge 이벤트 발행.

    Event Structure:
    {
        "alert_type": "cost_drift",
        "severity": "🚨",
        "severity_level": "critical",
        "title": "비용 드리프트: Amazon Athena",
        "message": "아테나 비용이...",
        "affected_services": [...],
        "action_required": true,
        "hitl_request_id": "uuid-if-triggered"
    }
    """

    SEVERITY_EMOJI = {
        Severity.CRITICAL: "🚨",
        Severity.HIGH: "⚠️",
        Severity.MEDIUM: "📊",
        Severity.LOW: "ℹ️",
    }

    def __init__(
        self,
        event_bus: Optional[str] = None,
        source: str = "cd1-agent.bdp-cost",
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        use_mock: bool = False,
    ):
        """EventPublisher 초기화.

        Args:
            event_bus: EventBridge bus 이름
            source: 이벤트 소스
            region: AWS region
            endpoint_url: LocalStack endpoint (테스트용)
            use_mock: Mock 모드 사용 여부
        """
        self.event_bus = event_bus or os.getenv("EVENT_BUS", "cd1-agent-events")
        self.source = source
        self.region = region or os.getenv("AWS_REGION", "ap-northeast-2")
        self.endpoint_url = endpoint_url or os.getenv("LOCALSTACK_ENDPOINT")
        self.use_mock = use_mock or os.getenv("EVENT_PROVIDER", "").lower() == "mock"

        self._client = None
        self.published_events: List[AlertEvent] = []  # Mock 모드용

        logger.info(
            f"EventPublisher initialized: bus={self.event_bus}, "
            f"mock={self.use_mock}"
        )

    @property
    def client(self):
        """Lazy boto3 client 초기화."""
        if self._client is None and not self.use_mock:
            import boto3

            client_kwargs = {"region_name": self.region}
            if self.endpoint_url:
                client_kwargs["endpoint_url"] = self.endpoint_url

            self._client = boto3.client("events", **client_kwargs)

        return self._client

    def publish_alert(
        self,
        result: CostDriftResult,
        summary: AlertSummary,
        hitl_request_id: Optional[str] = None,
    ) -> bool:
        """단일 알람 이벤트 발행.

        Args:
            result: 비용 드리프트 탐지 결과
            summary: 알람 요약
            hitl_request_id: HITL 요청 ID (있는 경우)

        Returns:
            발행 성공 여부
        """
        event = AlertEvent(
            alert_type="cost_drift",
            severity=summary.severity_emoji,
            severity_level=result.severity.value,
            title=summary.title,
            message=summary.message,
            affected_services=[
                {
                    "service_name": result.service_name,
                    "account_id": result.account_id,
                    "account_name": result.account_name,
                    "current_cost": result.current_cost,
                    "historical_average": result.historical_average,
                    "change_percent": result.change_percent,
                    "confidence_score": result.confidence_score,
                    "spike_duration_days": result.spike_duration_days,
                    "trend_direction": result.trend_direction,
                }
            ],
            action_required=result.severity in (Severity.CRITICAL, Severity.HIGH),
            hitl_request_id=hitl_request_id,
            account_names=[result.account_name],
        )

        return self._publish_event(event, "Cost Drift Detected")

    def publish_batch_alert(
        self,
        results: List[CostDriftResult],
        summary: AlertSummary,
        hitl_request_id: Optional[str] = None,
    ) -> bool:
        """일괄 알람 이벤트 발행.

        Args:
            results: 비용 드리프트 탐지 결과 목록
            summary: 통합 알람 요약
            hitl_request_id: HITL 요청 ID (있는 경우)

        Returns:
            발행 성공 여부
        """
        # 이상 탐지된 결과만
        anomalies = [r for r in results if r.is_anomaly]

        if not anomalies:
            logger.info("No anomalies to publish")
            return True

        # 가장 높은 심각도 찾기
        highest_severity = max(anomalies, key=lambda r: r.confidence_score).severity

        affected_services = [
            {
                "service_name": r.service_name,
                "account_id": r.account_id,
                "account_name": r.account_name,
                "current_cost": r.current_cost,
                "historical_average": r.historical_average,
                "change_percent": r.change_percent,
                "confidence_score": r.confidence_score,
                "spike_duration_days": r.spike_duration_days,
                "trend_direction": r.trend_direction,
                "severity": r.severity.value,
            }
            for r in anomalies
        ]

        account_names = list(set(r.account_name for r in anomalies))

        event = AlertEvent(
            alert_type="cost_drift_batch",
            severity=summary.severity_emoji,
            severity_level=highest_severity.value,
            title=summary.title,
            message=summary.message,
            affected_services=affected_services,
            action_required=highest_severity in (Severity.CRITICAL, Severity.HIGH),
            hitl_request_id=hitl_request_id,
            account_names=account_names,
        )

        return self._publish_event(event, "Cost Drift Batch Detected")

    def _publish_event(self, event: AlertEvent, detail_type: str) -> bool:
        """EventBridge에 이벤트 발행.

        Args:
            event: 알람 이벤트
            detail_type: 이벤트 상세 타입

        Returns:
            발행 성공 여부
        """
        if self.use_mock:
            self.published_events.append(event)
            logger.info(f"[MOCK] Event published: {event.title}")
            return True

        try:
            response = self.client.put_events(
                Entries=[
                    {
                        "EventBusName": self.event_bus,
                        "Source": self.source,
                        "DetailType": detail_type,
                        "Detail": json.dumps(event.to_dict()),
                    }
                ]
            )

            failed_count = response.get("FailedEntryCount", 0)
            if failed_count > 0:
                logger.error(f"Failed to publish {failed_count} events")
                return False

            logger.info(f"Event published successfully: {event.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            return False

    def get_published_events(self) -> List[AlertEvent]:
        """Mock 모드에서 발행된 이벤트 목록 조회."""
        return self.published_events.copy()

    def clear_published_events(self) -> None:
        """Mock 모드에서 발행된 이벤트 목록 초기화."""
        self.published_events.clear()


class LocalStackEventPublisher(EventPublisher):
    """LocalStack용 EventPublisher."""

    def __init__(
        self,
        event_bus: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        super().__init__(
            event_bus=event_bus or "bdp-cost-events",
            endpoint_url=endpoint_url or os.getenv(
                "LOCALSTACK_ENDPOINT", "http://localhost:4566"
            ),
            use_mock=False,
        )


class MockEventPublisher(EventPublisher):
    """테스트용 Mock EventPublisher."""

    def __init__(self):
        super().__init__(use_mock=True)
