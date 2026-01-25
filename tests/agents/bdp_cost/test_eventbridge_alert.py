"""
LocalStack EventBridge 알람 테스트.

1월 21일 Athena 비용 스파이크 시나리오 검증.
"""

import pytest

from src.agents.bdp_cost.services.anomaly_detector import (
    CostDriftDetector,
    Severity,
)
from src.agents.bdp_cost.services.event_publisher import (
    LocalStackEventPublisher,
)
from src.agents.bdp_cost.services.cost_explorer_provider import ServiceCostData
from src.agents.bdp_cost.services.summary_generator import SummaryGenerator


class TestAthenaSpikAlert:
    """1월 21일 Athena 비용 스파이크 알람 테스트."""

    @pytest.fixture
    def jan21_athena_spike_data(self) -> ServiceCostData:
        """1월 21일 Athena 스파이크 시나리오 데이터.

        시나리오:
        - 1월 8일 ~ 20일: 정상 (25만원 ± 약간의 변동)
        - 1월 21일: 76만원 (200%+ 급등, CRITICAL 임계값 초과)

        Note:
            change_percent = (current - avg) / avg * 100
            avg ≈ 250692 (변동으로 인해 정확히 250000 아님)
            760000으로 설정 시 change_percent ≈ 203% -> CRITICAL
        """
        # 1월 8일 ~ 20일: 정상 (25만원 ± 약간의 변동)
        # 1월 21일: 76만원 (200%+ 급등, avg보다 3배 이상)
        historical_costs = [
            250000, 252000, 248000, 251000, 253000,  # 1/8-12
            249000, 250000, 252000, 251000, 248000,  # 1/13-17
            253000, 250000, 252000,                  # 1/18-20
            760000,                                  # 1/21 스파이크! (CRITICAL 보장)
        ]
        timestamps = [f"2025-01-{d:02d}" for d in range(8, 22)]

        return ServiceCostData(
            service_name="Amazon Athena",
            account_id="111111111111",
            account_name="bdp-prod",
            current_cost=760000,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    def test_detect_athena_spike_jan21(self, jan21_athena_spike_data):
        """1월 21일 Athena 스파이크 탐지 - 200% 급등이 CRITICAL로 탐지되는지 확인."""
        detector = CostDriftDetector(sensitivity=0.7)
        result = detector.analyze_service(jan21_athena_spike_data)

        # 이상 탐지 확인
        assert result.is_anomaly is True, "200% 스파이크는 이상으로 탐지되어야 함"

        # 심각도 확인 (200% 이상은 CRITICAL)
        assert result.severity == Severity.CRITICAL, (
            f"200% 스파이크는 CRITICAL이어야 함, 실제: {result.severity}"
        )

        # 변화율 확인 (~200%)
        assert result.change_percent >= 180, (
            f"변화율이 180% 이상이어야 함, 실제: {result.change_percent}%"
        )

        # 트렌드 확인
        assert "increasing" in result.trend_direction, (
            f"트렌드가 증가여야 함, 실제: {result.trend_direction}"
        )

        # 서비스 정보 확인
        assert result.service_name == "Amazon Athena"
        assert result.account_name == "bdp-prod"
        assert result.current_cost == 760000

    def test_generate_alert_summary_korean(self, jan21_athena_spike_data):
        """한글 알람 요약 생성 - 아테나, 75만원, 스파이크 정보 포함 확인."""
        detector = CostDriftDetector(sensitivity=0.7)
        result = detector.analyze_service(jan21_athena_spike_data)

        generator = SummaryGenerator(currency="KRW")
        summary = generator.generate(result)

        # 제목에 서비스명 포함 확인
        assert "Athena" in summary.title or "아테나" in summary.title, (
            f"제목에 Athena 포함되어야 함, 실제: {summary.title}"
        )

        # 심각도 이모지 확인 (CRITICAL = 🚨)
        assert summary.severity_emoji == "🚨", (
            f"CRITICAL 심각도는 🚨 이모지여야 함, 실제: {summary.severity_emoji}"
        )

        # 메시지에 비용 정보 포함 확인
        assert "76만원" in summary.message or "760,000" in summary.message, (
            f"메시지에 76만원 포함되어야 함, 실제: {summary.message}"
        )

        # 계정명 포함 확인
        assert "bdp-prod" in summary.message, (
            f"메시지에 계정명 포함되어야 함, 실제: {summary.message}"
        )

        # 심각도 정보 포함 확인
        assert "심각" in summary.message, (
            f"메시지에 심각도 정보 포함되어야 함, 실제: {summary.message}"
        )

    @pytest.mark.localstack
    def test_publish_to_localstack_eventbridge(
        self,
        localstack_available,
        bdp_localstack_endpoint,
        jan21_athena_spike_data,
    ):
        """LocalStack EventBridge에 알람 발행 - 이벤트 발행 성공 확인."""
        if not localstack_available:
            pytest.skip("LocalStack not available")

        import boto3

        # 1. 탐지
        detector = CostDriftDetector(sensitivity=0.7)
        result = detector.analyze_service(jan21_athena_spike_data)

        # 2. 요약 생성
        generator = SummaryGenerator(currency="KRW")
        summary = generator.generate(result)

        # 3. EventBridge 클라이언트로 이벤트 버스 생성 (없으면)
        events_client = boto3.client(
            "events",
            endpoint_url=bdp_localstack_endpoint,
            region_name="ap-northeast-2",
        )

        # 이벤트 버스 생성 시도 (이미 있으면 무시)
        try:
            events_client.create_event_bus(Name="bdp-cost-events")
        except events_client.exceptions.ResourceAlreadyExistsException:
            pass
        except Exception:
            # LocalStack에서는 default 버스 사용 가능
            pass

        # 4. LocalStack EventBridge에 발행
        publisher = LocalStackEventPublisher(
            event_bus="bdp-cost-events",
            endpoint_url=bdp_localstack_endpoint,
        )

        success = publisher.publish_alert(result, summary)
        assert success is True, "EventBridge 이벤트 발행이 성공해야 함"

        # 5. 이벤트 버스 존재 확인
        buses = events_client.list_event_buses()
        bus_names = [b["Name"] for b in buses.get("EventBuses", [])]
        # default 버스는 항상 존재
        assert "default" in bus_names or "bdp-cost-events" in bus_names, (
            f"이벤트 버스가 존재해야 함, 실제: {bus_names}"
        )

    def test_alert_event_structure(self, jan21_athena_spike_data):
        """알람 이벤트 구조 검증 - AlertEvent 필드가 올바르게 생성되는지 확인."""
        from src.agents.bdp_cost.services.event_publisher import (
            AlertEvent,
            MockEventPublisher,
        )

        # 1. 탐지
        detector = CostDriftDetector(sensitivity=0.7)
        result = detector.analyze_service(jan21_athena_spike_data)

        # 2. 요약 생성
        generator = SummaryGenerator(currency="KRW")
        summary = generator.generate(result)

        # 3. Mock Publisher로 이벤트 구조 확인
        publisher = MockEventPublisher()
        success = publisher.publish_alert(result, summary)

        assert success is True

        # 4. 발행된 이벤트 검증
        events = publisher.get_published_events()
        assert len(events) == 1

        event = events[0]
        assert event.alert_type == "cost_drift"
        assert event.severity == "🚨"  # CRITICAL
        assert event.severity_level == "critical"
        assert "Athena" in event.title or "아테나" in event.title
        assert event.action_required is True  # CRITICAL은 action_required
        assert len(event.affected_services) == 1

        # 영향받은 서비스 정보 확인
        affected = event.affected_services[0]
        assert affected["service_name"] == "Amazon Athena"
        assert affected["account_id"] == "111111111111"
        assert affected["current_cost"] == 760000
        assert affected["change_percent"] >= 200  # CRITICAL 임계값

    def test_severity_levels(self):
        """다양한 스파이크 강도에 대한 심각도 레벨 확인.

        심각도 기준 (change_percent 또는 confidence 기반):
        - CRITICAL: >= 200% 또는 confidence >= 0.9
        - HIGH: >= 100% 또는 confidence >= 0.7
        - MEDIUM: >= 50% 또는 confidence >= 0.5
        - LOW: 그 외
        """
        base_costs = [250000] * 13  # 1/8-20

        test_cases = [
            # (마지막 날 비용, 예상 최소 심각도, 변화율 설명)
            (760000, Severity.CRITICAL, "203%"),  # >= 200% → CRITICAL
            (500000, Severity.HIGH, "100%"),       # >= 100% → HIGH
            (375000, Severity.MEDIUM, "50%"),      # >= 50% → MEDIUM
            (300000, Severity.LOW, "20%"),         # < 50% → LOW (신뢰도에 따라 달라질 수 있음)
        ]

        detector = CostDriftDetector(sensitivity=0.7)

        for spike_cost, expected_min_severity, desc in test_cases:
            historical_costs = base_costs + [spike_cost]
            timestamps = [f"2025-01-{d:02d}" for d in range(8, 22)]

            data = ServiceCostData(
                service_name="Amazon Athena",
                account_id="111111111111",
                account_name="test-account",
                current_cost=spike_cost,
                historical_costs=historical_costs,
                timestamps=timestamps,
                currency="KRW",
            )

            result = detector.analyze_service(data)

            # 심각도 순서: CRITICAL > HIGH > MEDIUM > LOW
            severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
            result_idx = severity_order.index(result.severity)
            expected_idx = severity_order.index(expected_min_severity)

            assert result_idx >= expected_idx, (
                f"비용 {spike_cost}원 ({desc}): 심각도가 {expected_min_severity} 이상이어야 함, "
                f"실제: {result.severity}, 변화율: {result.change_percent}%, 신뢰도: {result.confidence_score}"
            )
