"""
EventBridge Publisher (Common).

EventBridge를 통한 이벤트 발행 공통 모듈.
bdp_cost, bdp_drift 등 여러 에이전트에서 공유.

Production: 현대카드 커스텀 모듈 연동
Development: LocalStack 에뮬레이션
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AlertEvent:
    """EventBridge 알람 이벤트 구조 (Generic)."""

    alert_type: str  # cost_drift, config_drift, etc.
    severity: str  # emoji
    severity_level: str  # critical, high, medium, low
    title: str
    message: str
    affected_resources: List[Dict[str, Any]]  # Generic (services/resources)
    action_required: bool
    hitl_request_id: Optional[str] = None
    detection_timestamp: str = ""
    account_names: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.detection_timestamp:
            self.detection_timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return asdict(self)


class EventPublisher:
    """
    EventBridge 이벤트 발행기 (Common).

    공통 모듈로 여러 에이전트에서 재사용.
    source 파라미터로 각 에이전트 구분.

    Usage:
        # bdp_cost
        publisher = EventPublisher(source="cd1-agent.bdp-cost")

        # bdp_drift
        publisher = EventPublisher(source="cd1-agent.bdp-drift")
    """

    def __init__(
        self,
        event_bus: Optional[str] = None,
        source: str = "cd1-agent",
        detail_type: Optional[str] = None,
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        use_mock: bool = False,
        config_path: Optional[str] = None,
    ):
        """EventPublisher 초기화.

        Args:
            event_bus: EventBridge bus 이름
            source: 이벤트 소스 (각 에이전트별 고유)
            detail_type: 이벤트 상세 타입
            region: AWS region
            endpoint_url: LocalStack endpoint (테스트용)
            use_mock: Mock 모드 사용 여부
            config_path: EventBridge 설정 JSON 파일 경로
        """
        # 설정 파일 로드
        self._config = self._load_config(config_path)

        self.event_bus = (
            event_bus
            or self._config.get("EventBusName")
            or os.getenv("EVENT_BUS", "cd1-agent-events")
        )
        self.source = source or self._config.get("Source", "cd1-agent")
        self.detail_type = detail_type or self._config.get("DetailType")
        self.region = region or os.getenv("AWS_REGION", "ap-northeast-2")
        self.endpoint_url = endpoint_url or os.getenv("LOCALSTACK_ENDPOINT")
        self.use_mock = use_mock or os.getenv("EVENT_PROVIDER", "").lower() == "mock"

        self._client = None
        self.published_events: List[AlertEvent] = []  # Mock 모드용

        logger.info(
            f"EventPublisher initialized: bus={self.event_bus}, "
            f"source={self.source}, mock={self.use_mock}"
        )

    def _load_config(self, config_path: Optional[str]) -> dict:
        """JSON 설정 파일 로드.

        Args:
            config_path: 설정 파일 경로. None이면 기본 경로 사용.

        Returns:
            설정 딕셔너리. 파일이 없으면 빈 딕셔너리.
        """
        if config_path is None:
            return {}

        default_path = Path(config_path)

        if default_path.exists():
            try:
                with open(default_path, encoding="utf-8") as f:
                    config = json.load(f)
                    logger.info(f"EventBridge config loaded from: {default_path}")
                    return config
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load config from {default_path}: {e}")
                return {}

        return {}

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

    def publish_event(
        self,
        event: AlertEvent,
        detail_type: Optional[str] = None,
    ) -> bool:
        """EventBridge에 이벤트 발행.

        Args:
            event: 알람 이벤트
            detail_type: 이벤트 상세 타입 (인스턴스 설정이 우선)

        Returns:
            발행 성공 여부
        """
        effective_detail_type = self.detail_type or detail_type or "Alert Detected"

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
                        "DetailType": effective_detail_type,
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

    def publish_batch_events(
        self,
        events: List[AlertEvent],
        detail_type: Optional[str] = None,
    ) -> bool:
        """여러 이벤트 일괄 발행.

        Args:
            events: 알람 이벤트 목록
            detail_type: 이벤트 상세 타입

        Returns:
            발행 성공 여부
        """
        if not events:
            logger.info("No events to publish")
            return True

        effective_detail_type = self.detail_type or detail_type or "Alert Detected"

        if self.use_mock:
            self.published_events.extend(events)
            logger.info(f"[MOCK] {len(events)} events published")
            return True

        try:
            entries = [
                {
                    "EventBusName": self.event_bus,
                    "Source": self.source,
                    "DetailType": effective_detail_type,
                    "Detail": json.dumps(event.to_dict()),
                }
                for event in events
            ]

            response = self.client.put_events(Entries=entries)

            failed_count = response.get("FailedEntryCount", 0)
            if failed_count > 0:
                logger.error(f"Failed to publish {failed_count} events")
                return False

            logger.info(f"{len(events)} events published successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to publish events: {e}")
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
        source: str = "cd1-agent",
        endpoint_url: Optional[str] = None,
    ):
        super().__init__(
            event_bus=event_bus or "cd1-agent-events",
            source=source,
            endpoint_url=endpoint_url or os.getenv(
                "LOCALSTACK_ENDPOINT", "http://localhost:4566"
            ),
            use_mock=False,
        )


class MockEventPublisher(EventPublisher):
    """테스트용 Mock EventPublisher."""

    def __init__(self, source: str = "cd1-agent"):
        super().__init__(source=source, use_mock=True)
