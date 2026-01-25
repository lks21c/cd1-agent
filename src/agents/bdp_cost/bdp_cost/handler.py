"""
BDP Compact Handler for Multi-Account Cost Drift Detection.

Lambda/FastAPI 핸들러 - Multi-Account Cost Explorer 기반 비용 드리프트 탐지
및 KakaoTalk 알람 발송.

Standalone version - no dependency on src.common
"""

import json
import logging
import os
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from bdp_cost.services.anomaly_detector import (
    CostDriftDetector,
    CostDriftResult,
    Severity,
)
from bdp_cost.services.event_publisher import EventPublisher
from bdp_cost.services.multi_account_provider import (
    create_provider,
    BaseMultiAccountProvider,
)
from bdp_cost.services.summary_generator import SummaryGenerator

logger = logging.getLogger(__name__)


class BDPCostHandler:
    """
    BDP Compact 비용 드리프트 탐지 핸들러.

    Multi-Account Cost Explorer 데이터를 분석하여 비용 드리프트를 탐지하고,
    EventBridge를 통해 KakaoTalk 알람을 발송합니다.

    Features:
    - Multi-Account Cost Explorer 접근 (STS AssumeRole)
    - PyOD ECOD 기반 이상 탐지
    - 한글 Rich Summary 생성
    - EventBridge → KakaoTalk 알람
    """

    def __init__(self):
        """핸들러 초기화."""
        self.name = "BDPCostHandler"
        self.logger = logging.getLogger(self.name)
        self._init_services()

    def _init_services(self) -> None:
        """서비스 컴포넌트 초기화."""
        # Provider 설정
        provider_type = os.getenv("BDP_PROVIDER", "mock")
        self.provider: BaseMultiAccountProvider = create_provider(
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

        # 설정값
        self.min_cost_threshold = float(os.getenv("BDP_MIN_COST_THRESHOLD", "10000"))

        self.logger.info(
            f"BDPCostHandler initialized: provider={provider_type}, "
            f"sensitivity={sensitivity}, currency={currency}"
        )

    def handle(self, event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        """Lambda 핸들러 진입점.

        Args:
            event: Lambda 이벤트 또는 API 요청
            context: Lambda context

        Returns:
            응답 딕셔너리
        """
        try:
            result = self.process(event, context)
            return {
                "success": True,
                "data": result,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            self.logger.error(f"Handler error: {e}\n{traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    def _parse_body(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """이벤트 바디 파싱.

        Args:
            event: Lambda 이벤트

        Returns:
            파싱된 바디 딕셔너리
        """
        body = event.get("body", {})
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}
        return body or {}

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
        cost_data = self.provider.get_cost_data(days=days)
        total_services = sum(len(services) for services in cost_data.values())
        self.logger.info(f"조회된 서비스: {total_services}개")

        # 2. 비용 드리프트 탐지
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
        if anomalies and publish_alerts:
            # Summary 생성
            summary = self.summary_generator.generate_batch_summary(anomalies)

            # EventBridge 발행
            self.event_publisher.publish_batch_alert(
                results=anomalies,
                summary=summary,
            )

        # 6. 결과 반환
        return {
            "detection_type": "cost_drift",
            "period_days": days,
            "accounts_analyzed": len(cost_data),
            "services_analyzed": len(filtered_results),
            "anomalies_detected": len(anomalies) > 0,
            "total_anomalies": len(anomalies),
            "severity_breakdown": severity_breakdown,
            "summary": self._generate_result_summary(anomalies),
            "results": [self._result_to_dict(r) for r in anomalies[:20]],
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


# Lambda entry point
handler_instance = BDPCostHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)
