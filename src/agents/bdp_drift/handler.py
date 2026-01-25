"""
BDP Drift Agent - Lambda Handler.

데이터레이크 어플리케이션 레이어의 설정 drift 탐지.

Supported Resources:
- Primary: Glue, Athena, EMR, SageMaker
- Secondary: S3, MWAA, MSK, Lambda
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.handlers import BaseHandler
from src.common.hitl.models import HITLAgentType, HITLRequest, HITLStatus
from src.common.hitl.store import HITLStore

from src.agents.bdp_drift.bdp_drift.services.baseline_store import BaselineStore
from src.agents.bdp_drift.bdp_drift.services.config_fetcher import ConfigFetcher
from src.agents.bdp_drift.bdp_drift.services.drift_detector import DriftDetector
from src.agents.bdp_drift.bdp_drift.services.summary_generator import (
    DriftSummaryGenerator,
    DriftAlertSummary,
)
from src.agents.bdp_drift.bdp_drift.services.models import DriftResult, DriftSeverity

from src.agents.bdp_common.eventbridge.publisher import EventPublisher, AlertEvent
from src.agents.bdp_common.kakao.notifier import KakaoNotifier

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class BDPDriftHandler(BaseHandler):
    """
    BDP Drift Agent Handler.

    베이스라인과 현재 설정을 비교하여 드리프트 탐지.
    CRITICAL 드리프트 발생 시 HITL 요청 생성.
    """

    def __init__(self):
        """핸들러 초기화."""
        super().__init__()

        # 환경 변수
        self.provider = os.getenv("DRIFT_PROVIDER", "mock")
        self.baseline_provider = os.getenv("BASELINE_DB_PROVIDER", "mock")
        self.hitl_on_critical = os.getenv("DRIFT_HITL_ON_CRITICAL", "true").lower() == "true"
        self.event_provider = os.getenv("EVENT_PROVIDER", "mock")
        self.rds_provider = os.getenv("RDS_PROVIDER", "mock")

        # 서비스 초기화
        self.baseline_store = BaselineStore(provider=self.baseline_provider)
        self.baseline_store.ensure_tables()

        self.config_fetcher = ConfigFetcher(
            use_mock=(self.provider == "mock")
        )

        self.detector = DriftDetector(
            baseline_store=self.baseline_store,
            config_fetcher=self.config_fetcher,
        )

        self.summary_generator = DriftSummaryGenerator()

        self.event_publisher = EventPublisher(
            source="cd1-agent.bdp-drift",
            use_mock=(self.event_provider == "mock"),
        )

        self.hitl_store = HITLStore(provider=self.rds_provider)

        # 카카오 알림 (선택)
        self.kakao_notifier: Optional[KakaoNotifier] = None
        if os.getenv("KAKAO_REST_API_KEY"):
            self.kakao_notifier = KakaoNotifier()
            self.kakao_notifier.load_tokens()

        logger.info(
            f"BDPDriftHandler initialized: "
            f"provider={self.provider}, "
            f"baseline_db={self.baseline_provider}, "
            f"hitl_on_critical={self.hitl_on_critical}"
        )

    def process(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """드리프트 탐지 실행.

        Args:
            event: 이벤트 페이로드
                - resource_types: 대상 리소스 타입 목록 (선택)
                - resource_ids: 특정 리소스 ID 목록 (선택)
                - publish_alerts: EventBridge 발행 여부 (기본 True)
                - send_kakao: 카카오톡 발송 여부 (기본 False)

        Returns:
            탐지 결과
        """
        # 입력 검증
        resource_types = event.get("resource_types")
        resource_ids = event.get("resource_ids")
        publish_alerts = event.get("publish_alerts", True)
        send_kakao = event.get("send_kakao", False)

        logger.info(
            f"Starting drift detection: "
            f"types={resource_types}, ids={resource_ids}"
        )

        # 드리프트 탐지
        if resource_ids:
            # 특정 리소스만 탐지
            results = []
            for resource_id in resource_ids:
                # resource_id format: type/id
                parts = resource_id.split("/", 1)
                if len(parts) == 2:
                    result = self.detector.detect(parts[0], parts[1])
                    if result:
                        results.append(result)
        else:
            # 전체 탐지
            results = self.detector.detect_all(resource_types=resource_types)

        # 드리프트 필터링
        drifts = [r for r in results if r.has_drift]

        logger.info(
            f"Detection complete: {len(results)} checked, "
            f"{len(drifts)} drifts found"
        )

        # 결과가 없으면 조기 반환
        if not drifts:
            return self._build_response(results, [], None)

        # 요약 생성
        summary = self.summary_generator.generate_batch_summary(drifts)

        # HITL 요청 (CRITICAL인 경우)
        hitl_request_id = None
        if self.hitl_on_critical and self._has_critical(drifts):
            hitl_request_id = self._create_hitl_request(drifts, summary)

        # EventBridge 발행
        if publish_alerts:
            self._publish_events(drifts, summary, hitl_request_id)

        # 카카오톡 발송
        if send_kakao and self.kakao_notifier:
            self._send_kakao_alert(drifts, summary)

        return self._build_response(results, drifts, hitl_request_id)

    def _has_critical(self, results: List[DriftResult]) -> bool:
        """CRITICAL 드리프트 존재 여부."""
        return any(r.severity == DriftSeverity.CRITICAL for r in results)

    def _create_hitl_request(
        self,
        results: List[DriftResult],
        summary: DriftAlertSummary,
    ) -> Optional[str]:
        """HITL 요청 생성."""
        try:
            critical_results = [
                r for r in results if r.severity == DriftSeverity.CRITICAL
            ]

            request = HITLRequest(
                agent_type=HITLAgentType.DRIFT,
                request_type="drift_review",
                title=summary.title,
                description=summary.message,
                payload={
                    "drift_count": summary.drift_count,
                    "critical_count": summary.critical_count,
                    "high_count": summary.high_count,
                    "affected_resources": [
                        {
                            "resource_type": r.resource_type,
                            "resource_id": r.resource_id,
                            "severity": r.severity.value,
                            "drift_fields": [f.field_name for f in r.drift_fields],
                        }
                        for r in critical_results
                    ],
                    "options": [
                        {"action": "accept_changes", "label": "의도적 변경으로 베이스라인 업데이트"},
                        {"action": "investigate", "label": "조사 필요"},
                        {"action": "rollback", "label": "즉시 롤백"},
                    ],
                },
                created_by="bdp-drift-agent",
            )

            created = self.hitl_store.create_request(request)
            logger.info(f"HITL request created: {created.id}")
            return created.id

        except Exception as e:
            logger.error(f"Failed to create HITL request: {e}")
            return None

    def _publish_events(
        self,
        results: List[DriftResult],
        summary: DriftAlertSummary,
        hitl_request_id: Optional[str],
    ) -> None:
        """EventBridge에 이벤트 발행."""
        try:
            event = AlertEvent(
                alert_type="config_drift_batch",
                severity=summary.severity_emoji,
                severity_level=self._get_highest_severity(results).value,
                title=summary.title,
                message=summary.message,
                affected_resources=[
                    {
                        "resource_type": r.resource_type,
                        "resource_id": r.resource_id,
                        "severity": r.severity.value,
                        "drift_count": r.drift_count,
                    }
                    for r in results
                ],
                action_required=self._has_critical(results) or any(
                    r.severity == DriftSeverity.HIGH for r in results
                ),
                hitl_request_id=hitl_request_id,
                metadata={
                    "total_drifts": summary.drift_count,
                    "critical_count": summary.critical_count,
                    "high_count": summary.high_count,
                },
            )

            self.event_publisher.publish_event(event, "Config Drift Detected")
            logger.info("EventBridge event published")

        except Exception as e:
            logger.error(f"Failed to publish EventBridge event: {e}")

    def _send_kakao_alert(
        self,
        results: List[DriftResult],
        summary: DriftAlertSummary,
    ) -> None:
        """카카오톡 알림 발송."""
        if not self.kakao_notifier:
            return

        try:
            self.kakao_notifier.send_text_message(
                f"{summary.title}\n\n{summary.message}"
            )
            logger.info("KakaoTalk alert sent")

        except Exception as e:
            logger.error(f"Failed to send KakaoTalk alert: {e}")

    def _get_highest_severity(self, results: List[DriftResult]) -> DriftSeverity:
        """가장 높은 심각도 반환."""
        for severity in [DriftSeverity.CRITICAL, DriftSeverity.HIGH, DriftSeverity.MEDIUM]:
            if any(r.severity == severity for r in results):
                return severity
        return DriftSeverity.LOW

    def _count_by_severity(
        self, results: List[DriftResult]
    ) -> Dict[str, int]:
        """심각도별 카운트."""
        counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        for r in results:
            counts[r.severity.value] += 1
        return counts

    def _build_response(
        self,
        all_results: List[DriftResult],
        drifts: List[DriftResult],
        hitl_request_id: Optional[str],
    ) -> Dict[str, Any]:
        """응답 생성."""
        severity_counts = self._count_by_severity(drifts)

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_checked": len(all_results),
                "total_drifts": len(drifts),
                "by_severity": severity_counts,
            },
            "drifts": [r.to_dict() for r in drifts],
            "hitl_request_id": hitl_request_id,
        }


# Lambda 핸들러
_handler_instance: Optional[BDPDriftHandler] = None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda 핸들러 함수.

    Args:
        event: Lambda 이벤트
        context: Lambda 컨텍스트

    Returns:
        탐지 결과
    """
    global _handler_instance

    if _handler_instance is None:
        _handler_instance = BDPDriftHandler()

    return _handler_instance.process(event)


if __name__ == "__main__":
    # 로컬 테스트
    result = handler(
        {
            "resource_types": ["glue", "athena", "s3", "lambda"],
            "publish_alerts": False,
        },
        None,
    )
    print(result)
