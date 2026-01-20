"""
CostDriftDetector 테스트.

PyOD ECOD 기반 비용 드리프트 탐지기 단위 테스트.
"""

import pytest

from src.agents.bdp_compact.services.anomaly_detector import (
    CostDriftDetector,
    CostDriftResult,
    Severity,
)
from src.agents.bdp_compact.services.multi_account_provider import ServiceCostData


class TestCostDriftDetector:
    """CostDriftDetector 테스트."""

    @pytest.fixture
    def detector(self):
        """기본 탐지기."""
        return CostDriftDetector(sensitivity=0.7)

    @pytest.fixture
    def normal_service_data(self):
        """정상 패턴 서비스 데이터."""
        return ServiceCostData(
            service_name="Amazon Athena",
            account_id="111111111111",
            account_name="test-account",
            current_cost=255000,
            historical_costs=[250000, 252000, 248000, 251000, 253000, 249000, 250000,
                            252000, 251000, 248000, 253000, 250000, 252000, 255000],
            timestamps=[f"2025-01-{i:02d}" for i in range(1, 15)],
            currency="KRW",
        )

    @pytest.fixture
    def spike_service_data(self):
        """스파이크 패턴 서비스 데이터."""
        return ServiceCostData(
            service_name="Amazon Athena",
            account_id="111111111111",
            account_name="test-account",
            current_cost=580000,  # 132% 상승
            historical_costs=[250000, 250000, 250000, 250000, 250000, 250000, 250000,
                            250000, 250000, 250000, 250000, 350000, 450000, 580000],
            timestamps=[f"2025-01-{i:02d}" for i in range(1, 15)],
            currency="KRW",
        )

    @pytest.fixture
    def insufficient_data(self):
        """데이터 부족 서비스."""
        return ServiceCostData(
            service_name="Amazon Athena",
            account_id="111111111111",
            account_name="test-account",
            current_cost=250000,
            historical_costs=[250000, 252000, 248000],  # 3일 데이터
            timestamps=["2025-01-01", "2025-01-02", "2025-01-03"],
            currency="KRW",
        )

    def test_normal_pattern_no_anomaly(self, detector, normal_service_data):
        """정상 패턴에서는 이상 탐지되지 않음."""
        result = detector.analyze_service(normal_service_data)

        assert isinstance(result, CostDriftResult)
        assert result.is_anomaly is False
        assert result.confidence_score < 0.5
        assert result.severity in (Severity.LOW, Severity.MEDIUM)

    def test_spike_pattern_detected(self, detector, spike_service_data):
        """스파이크 패턴에서 이상 탐지됨."""
        result = detector.analyze_service(spike_service_data)

        assert result.is_anomaly is True
        assert result.confidence_score >= 0.5
        assert result.severity in (Severity.HIGH, Severity.CRITICAL)
        assert result.change_percent > 100  # 132% 상승

    def test_spike_duration_calculated(self, detector, spike_service_data):
        """스파이크 지속 기간 계산."""
        result = detector.analyze_service(spike_service_data)

        # 마지막 3일이 스파이크
        assert result.spike_duration_days >= 1
        assert result.trend_direction == "increasing"

    def test_insufficient_data_handled(self, detector, insufficient_data):
        """데이터 부족 시 정상 처리."""
        result = detector.analyze_service(insufficient_data)

        assert result.is_anomaly is False
        assert result.confidence_score == 0.0
        assert result.detection_method == "insufficient_data"

    def test_batch_analysis(self, detector, normal_service_data, spike_service_data):
        """일괄 분석 테스트."""
        cost_data = {
            "account1": [normal_service_data],
            "account2": [spike_service_data],
        }

        results = detector.analyze_batch(cost_data)

        assert len(results) == 2
        # 신뢰도 내림차순 정렬
        assert results[0].confidence_score >= results[1].confidence_score

    def test_sensitivity_affects_detection(self, spike_service_data):
        """민감도가 탐지에 영향."""
        low_sens_detector = CostDriftDetector(sensitivity=0.3)
        high_sens_detector = CostDriftDetector(sensitivity=0.9)

        low_result = low_sens_detector.analyze_service(spike_service_data)
        high_result = high_sens_detector.analyze_service(spike_service_data)

        # 높은 민감도 = 더 높은 신뢰도
        assert high_result.confidence_score >= low_result.confidence_score

    def test_severity_levels(self, detector):
        """심각도 레벨 테스트."""
        # 200% 이상 상승 = CRITICAL
        critical_data = ServiceCostData(
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=750000,  # 200% 상승
            historical_costs=[250000] * 14,
            timestamps=[f"2025-01-{i:02d}" for i in range(1, 15)],
        )
        result = detector.analyze_service(critical_data)
        assert result.severity == Severity.CRITICAL

        # 100% 상승 = HIGH
        high_data = ServiceCostData(
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=500000,  # 100% 상승
            historical_costs=[250000] * 14,
            timestamps=[f"2025-01-{i:02d}" for i in range(1, 15)],
        )
        result = detector.analyze_service(high_data)
        assert result.severity in (Severity.HIGH, Severity.CRITICAL)

    def test_trend_analysis(self, detector):
        """트렌드 분석 테스트."""
        # 상승 트렌드
        increasing_data = ServiceCostData(
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=300000,
            historical_costs=[200000 + i * 7000 for i in range(14)],
            timestamps=[f"2025-01-{i:02d}" for i in range(1, 15)],
        )
        result = detector.analyze_service(increasing_data)
        assert result.trend_direction == "increasing"

        # 하락 트렌드
        decreasing_data = ServiceCostData(
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=100000,
            historical_costs=[300000 - i * 14000 for i in range(14)],
            timestamps=[f"2025-01-{i:02d}" for i in range(1, 15)],
        )
        result = detector.analyze_service(decreasing_data)
        assert result.trend_direction == "decreasing"

    def test_result_contains_all_fields(self, detector, spike_service_data):
        """결과에 모든 필드 포함."""
        result = detector.analyze_service(spike_service_data)

        assert result.service_name == "Amazon Athena"
        assert result.account_id == "111111111111"
        assert result.account_name == "test-account"
        assert result.current_cost == 580000
        assert result.historical_average > 0
        assert result.detection_method in ("ecod", "ratio", "ensemble", "insufficient_data")
