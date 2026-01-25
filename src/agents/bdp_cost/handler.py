"""
BDP Compact Handler for Cost Drift Detection.

Lambda/FastAPI 핸들러 - Cost Explorer 기반 비용 드리프트 탐지
및 KakaoTalk 알람 발송.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.handlers.base_handler import BaseHandler
from src.common.hitl.schemas import (
    HITLAgentType,
    HITLRequestCreate,
    HITLRequestType,
)
from src.common.hitl.store import HITLStore

from src.agents.bdp_cost.services.anomaly_detector import (
    CostDriftDetector,
    CostDriftResult,
    Severity,
)
from src.agents.bdp_cost.services.event_publisher import EventPublisher
from src.agents.bdp_cost.services.cost_explorer_provider import (
    create_provider,
    BaseCostExplorerProvider,
)
from src.agents.bdp_cost.services.summary_generator import SummaryGenerator


class BDPCostHandler(BaseHandler):
    """
    BDP Compact 비용 드리프트 탐지 핸들러.

    Cost Explorer 데이터를 분석하여 비용 드리프트를 탐지하고,
    EventBridge를 통해 KakaoTalk 알람을 발송합니다.

    Features:
    - Cost Explorer 접근 (Lambda 실행 역할 권한 사용)
    - PyOD ECOD 기반 이상 탐지
    - 한글 Rich Summary 생성
    - EventBridge → KakaoTalk 알람
    - 확장된 HITL (PROMPT_INPUT 지원)
    """

    def __init__(self):
        super().__init__("BDPCostHandler")
        self._init_services()

    def _init_services(self) -> None:
        """서비스 컴포넌트 초기화."""
        # Provider 설정
        provider_type = os.getenv("BDP_PROVIDER", "mock")
        self.provider: BaseCostExplorerProvider = create_provider(
            provider_type=provider_type
        )

        # Detector 설정
        sensitivity = float(os.getenv("BDP_SENSITIVITY", "0.7"))
        self.detector = CostDriftDetector(sensitivity=sensitivity)

        # Summary Generator 설정
        currency = os.getenv("BDP_CURRENCY", "KRW")
        self.summary_generator = SummaryGenerator(currency=currency)

        # Event Publisher 설정
        event_provider = os.getenv("EVENT_PROVIDER", "mock")
        self.event_publisher = EventPublisher(
            event_bus=os.getenv("EVENT_BUS", "cd1-agent-events"),
            use_mock=event_provider == "mock",
        )

        # HITL Store 설정
        hitl_provider = os.getenv("RDS_PROVIDER", "mock")
        self.hitl_store = HITLStore(use_mock=hitl_provider == "mock")

        # 설정값
        self.min_cost_threshold = float(os.getenv("BDP_MIN_COST_THRESHOLD", "10000"))
        self.hitl_on_critical = os.getenv("BDP_HITL_ON_CRITICAL", "true").lower() == "true"

        self.logger.info(
            f"BDPCostHandler initialized: provider={provider_type}, "
            f"sensitivity={sensitivity}, currency={currency}"
        )

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """입력 검증."""
        # 기본 파라미터는 선택적이므로 검증 불필요
        return None

    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """비용 드리프트 탐지 실행.

        Args:
            event: Lambda 이벤트 또는 API 요청
            context: Lambda context

        Returns:
            탐지 결과
        """
        body = self._parse_body(event)

        # 파라미터 추출
        days = int(body.get("days", event.get("days", 14)))
        min_cost = float(
            body.get("min_cost_threshold", event.get("min_cost_threshold", self.min_cost_threshold))
        )
        publish_alerts = body.get("publish_alerts", event.get("publish_alerts", True))

        self.logger.info(
            f"비용 드리프트 탐지 시작: days={days}, min_cost={min_cost}"
        )

        # 1. 비용 데이터 조회
        cost_data_list = self.provider.get_cost_data(days=days)
        total_services = len(cost_data_list)
        self.logger.info(f"조회된 서비스: {total_services}개")

        # 2. 비용 드리프트 탐지
        # Detector expects Dict[str, List] format for backward compatibility
        account_info = self.provider.get_account_info()
        cost_data = {account_info["account_id"]: cost_data_list}
        all_results = self.detector.analyze_batch(cost_data)

        # 3. 최소 비용 임계값 필터링
        filtered_results = [
            r for r in all_results
            if r.current_cost >= min_cost or r.historical_average >= min_cost
        ]

        # 4. 이상 탐지된 결과만 추출
        anomalies = [r for r in filtered_results if r.is_anomaly]
        severity_breakdown = self._count_by_severity(anomalies)

        self.logger.info(
            f"탐지 완료: {len(anomalies)}건 이상 발견 "
            f"(심각: {severity_breakdown['critical']}, "
            f"높음: {severity_breakdown['high']})"
        )

        # 5. 알람 발송 (이상 탐지된 경우)
        hitl_request_id = None
        if anomalies and publish_alerts:
            # Summary 생성
            summary = self.summary_generator.generate_batch_summary(anomalies)

            # Critical 이상인 경우 HITL 요청 생성
            if self.hitl_on_critical and severity_breakdown["critical"] > 0:
                hitl_request_id = self._create_hitl_request(anomalies, summary)

            # EventBridge 발행
            self.event_publisher.publish_batch_alert(
                results=anomalies,
                summary=summary,
                hitl_request_id=hitl_request_id,
            )

        # 6. 결과 반환
        return {
            "detection_type": "cost_drift",
            "period_days": days,
            "accounts_analyzed": 1,  # Single account architecture
            "services_analyzed": len(filtered_results),
            "anomalies_detected": len(anomalies) > 0,
            "total_anomalies": len(anomalies),
            "severity_breakdown": severity_breakdown,
            "summary": self._generate_result_summary(anomalies),
            "results": [self._result_to_dict(r) for r in anomalies[:20]],
            "hitl_request_id": hitl_request_id,
            "detection_timestamp": datetime.utcnow().isoformat(),
        }

    def _count_by_severity(self, results: List[CostDriftResult]) -> Dict[str, int]:
        """심각도별 카운트."""
        return {
            "critical": sum(1 for r in results if r.severity == Severity.CRITICAL),
            "high": sum(1 for r in results if r.severity == Severity.HIGH),
            "medium": sum(1 for r in results if r.severity == Severity.MEDIUM),
            "low": sum(1 for r in results if r.severity == Severity.LOW),
        }

    def _generate_result_summary(self, anomalies: List[CostDriftResult]) -> str:
        """결과 요약 문자열 생성."""
        if not anomalies:
            return "비용 이상이 탐지되지 않았습니다."

        severity_counts = self._count_by_severity(anomalies)
        services = [r.service_name for r in anomalies[:5]]
        accounts = list(set(r.account_name for r in anomalies))

        return (
            f"총 {len(anomalies)}건의 비용 이상이 탐지되었습니다. "
            f"[심각: {severity_counts['critical']}, "
            f"높음: {severity_counts['high']}, "
            f"보통: {severity_counts['medium']}, "
            f"낮음: {severity_counts['low']}] "
            f"영향 서비스: {', '.join(services)} | "
            f"영향 계정: {', '.join(accounts)}"
        )

    def _result_to_dict(self, result: CostDriftResult) -> Dict[str, Any]:
        """CostDriftResult를 딕셔너리로 변환."""
        # 개별 summary 생성
        summary = self.summary_generator.generate(result)

        return {
            "service_name": result.service_name,
            "account_id": result.account_id,
            "account_name": result.account_name,
            "severity": result.severity.value,
            "confidence_score": result.confidence_score,
            "current_cost": result.current_cost,
            "historical_average": result.historical_average,
            "change_percent": result.change_percent,
            "spike_duration_days": result.spike_duration_days,
            "trend_direction": result.trend_direction,
            "spike_start_date": result.spike_start_date,
            "detection_method": result.detection_method,
            "summary": summary.message,  # 한글 summary
        }

    def _create_hitl_request(
        self,
        anomalies: List[CostDriftResult],
        summary,
    ) -> Optional[str]:
        """Critical 이상 탐지시 HITL 요청 생성.

        PROMPT_INPUT 타입으로 사용자에게 추가 질문 가능.

        Args:
            anomalies: 이상 탐지 결과 목록
            summary: 알람 요약

        Returns:
            생성된 HITL 요청 ID 또는 None
        """
        try:
            critical_services = [
                r.service_name for r in anomalies
                if r.severity == Severity.CRITICAL
            ]

            request = HITLRequestCreate(
                agent_type=HITLAgentType.BDP,
                request_type=HITLRequestType.PROMPT_INPUT,
                title=f"비용 드리프트 확인 필요: {', '.join(critical_services[:3])}",
                description=(
                    "Critical 수준의 비용 이상이 탐지되었습니다. "
                    "이 비용 급증이 예상된 것인지 확인이 필요합니다.\n\n"
                    f"{summary.message}"
                ),
                payload={
                    "anomaly_count": len(anomalies),
                    "critical_count": len(critical_services),
                    "affected_services": critical_services[:10],
                    "detection_timestamp": datetime.utcnow().isoformat(),
                    "question": (
                        "이 비용 급증이 예상된 것인가요? "
                        "(예: 배치 작업, 마케팅 캠페인, 신규 서비스 런칭 등)"
                    ),
                },
                expires_in_minutes=120,  # 2시간
                created_by="bdp-cost-agent",
            )

            hitl_request = self.hitl_store.create(request)
            self.logger.info(f"HITL 요청 생성됨: {hitl_request.id}")
            return hitl_request.id

        except Exception as e:
            self.logger.error(f"HITL 요청 생성 실패: {e}")
            return None


# Lambda entry point
handler_instance = BDPCostHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)
