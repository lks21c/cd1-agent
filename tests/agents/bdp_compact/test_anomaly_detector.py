"""
CostDriftDetector 테스트.

ECOD 기반 비용 드리프트 탐지기 단위 테스트.
PyOD ECOD 또는 경량 LightweightECOD 알고리즘 테스트 포함.
"""

import numpy as np
import pytest

from src.agents.bdp_compact.services.anomaly_detector import (
    CostDriftDetector,
    CostDriftResult,
    LightweightECOD,
    Severity,
    _numpy_skew,
)
from src.agents.bdp_compact.services.cost_explorer_provider import ServiceCostData


class TestCostDriftDetector:
    """CostDriftDetector 테스트."""

    @pytest.fixture
    def detector(self):
        """기본 탐지기."""
        return CostDriftDetector(sensitivity=0.7)

    @pytest.fixture
    def normal_service_data(self):
        """정상 패턴 서비스 데이터 (current is clearly within normal range)."""
        # Current cost (251000) is clearly within the middle of the distribution
        return ServiceCostData(
            service_name="Amazon Athena",
            account_id="111111111111",
            account_name="test-account",
            current_cost=251000,
            historical_costs=[250000, 252000, 248000, 251000, 253000, 249000, 250000,
                            252000, 251000, 248000, 253000, 250000, 252000, 251000],
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
        # Use == for comparison as numpy booleans work with ==
        assert result.is_anomaly == False  # noqa: E712
        assert result.confidence_score < 0.5
        assert result.severity in (Severity.LOW, Severity.MEDIUM)

    def test_spike_pattern_detected(self, detector, spike_service_data):
        """스파이크 패턴에서 이상 탐지됨."""
        result = detector.analyze_service(spike_service_data)

        assert result.is_anomaly == True  # noqa: E712
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

        assert result.is_anomaly == False  # noqa: E712
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
        # 상승 트렌드 (slope_ratio > 0.05 needed, so slope needs to be > avg * 0.05 per step)
        # With avg ~200000, need slope > 10000 per step
        increasing_data = ServiceCostData(
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=450000,
            historical_costs=[100000 + i * 25000 for i in range(14)],  # 25000 per step
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
            historical_costs=[400000 - i * 20000 for i in range(14)],  # 20000 per step
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
        assert result.detection_method in (
            "ecod", "ecod_lite", "ratio", "ensemble", "ensemble_lite", "insufficient_data"
        )


class TestNumpySkew:
    """_numpy_skew 함수 테스트."""

    def test_symmetric_distribution_skew_near_zero(self):
        """대칭 분포는 왜도가 0에 가까움."""
        # Normal-like symmetric data
        data = np.array([1, 2, 3, 4, 5, 4, 3, 2, 1])
        skew = _numpy_skew(data)
        assert abs(skew) < 0.5

    def test_right_skewed_distribution(self):
        """오른쪽 꼬리가 긴 분포는 양의 왜도."""
        # Right-skewed: most values are low, few high outliers
        data = np.array([1, 1, 1, 2, 2, 3, 10, 15, 20])
        skew = _numpy_skew(data)
        assert skew > 0

    def test_left_skewed_distribution(self):
        """왼쪽 꼬리가 긴 분포는 음의 왜도."""
        # Left-skewed: most values are high, few low outliers
        data = np.array([1, 5, 10, 18, 19, 19, 20, 20, 20])
        skew = _numpy_skew(data)
        assert skew < 0

    def test_insufficient_data_returns_zero(self):
        """데이터 부족 시 0 반환."""
        assert _numpy_skew(np.array([1])) == 0.0
        assert _numpy_skew(np.array([1, 2])) == 0.0

    def test_constant_data_returns_zero(self):
        """모든 값이 같으면 0 반환."""
        data = np.array([5, 5, 5, 5, 5])
        assert _numpy_skew(data) == 0.0


class TestLightweightECOD:
    """LightweightECOD 클래스 테스트."""

    def test_detects_single_outlier(self):
        """단일 이상치 탐지."""
        # Normal values with one clear outlier
        data = np.array([100, 105, 98, 103, 102, 101, 500]).reshape(-1, 1)

        clf = LightweightECOD(contamination=0.15)
        clf.fit(data)

        assert clf.labels_ is not None
        assert clf.decision_scores_ is not None
        # Last value (500) should be detected as outlier
        assert clf.labels_[-1] == 1

    def test_normal_data_no_outliers(self):
        """정상 데이터에서 이상치 최소화."""
        # Uniform normal data
        data = np.array([100, 102, 98, 101, 99, 100, 103]).reshape(-1, 1)

        clf = LightweightECOD(contamination=0.1)
        clf.fit(data)

        # Most should be normal
        outlier_ratio = np.mean(clf.labels_)
        assert outlier_ratio <= 0.3

    def test_contamination_affects_threshold(self):
        """contamination 값이 임계값에 영향."""
        data = np.array([100, 105, 98, 103, 102, 101, 200, 500]).reshape(-1, 1)

        clf_low = LightweightECOD(contamination=0.1)
        clf_high = LightweightECOD(contamination=0.3)

        clf_low.fit(data)
        clf_high.fit(data)

        # Higher contamination = lower threshold = more outliers
        assert np.sum(clf_high.labels_) >= np.sum(clf_low.labels_)

    def test_invalid_contamination_raises_error(self):
        """유효하지 않은 contamination 값은 에러."""
        with pytest.raises(ValueError):
            LightweightECOD(contamination=0.0)
        with pytest.raises(ValueError):
            LightweightECOD(contamination=0.6)

    def test_handles_1d_input(self):
        """1D 입력 처리."""
        data = np.array([100, 105, 98, 500])

        clf = LightweightECOD(contamination=0.25)
        clf.fit(data)

        assert clf.labels_ is not None
        assert len(clf.labels_) == 4

    def test_decision_function_returns_scores(self):
        """decision_function이 점수 반환."""
        data = np.array([100, 105, 98, 500]).reshape(-1, 1)

        clf = LightweightECOD(contamination=0.25)
        clf.fit(data)
        scores = clf.decision_function(data)

        assert len(scores) == 4
        # Outlier should have highest score
        assert np.argmax(scores) == 3

    def test_decision_function_without_fit_raises_error(self):
        """fit 없이 decision_function 호출 시 에러."""
        clf = LightweightECOD(contamination=0.1)
        with pytest.raises(RuntimeError):
            clf.decision_function(np.array([[100]]))

    def test_multivariate_detection(self):
        """다변량 이상 탐지."""
        # 2D data with one outlier
        data = np.array([
            [100, 50],
            [102, 51],
            [98, 49],
            [101, 50],
            [500, 200],  # Outlier in both dimensions
        ])

        clf = LightweightECOD(contamination=0.2)
        clf.fit(data)

        # Last row should be outlier
        assert clf.labels_[-1] == 1

    def test_cost_drift_scenario(self):
        """비용 드리프트 시나리오 테스트."""
        # Simulating 14 days of cost data with spike at the end
        costs = [250000, 252000, 248000, 251000, 253000, 249000, 250000,
                 252000, 251000, 248000, 253000, 350000, 450000, 580000]

        clf = LightweightECOD(contamination=0.1)
        clf.fit(np.array(costs).reshape(-1, 1))

        # Last value (580000) should be outlier
        assert clf.labels_[-1] == 1
        # Second to last (450000) might also be outlier
        # At least one of the last 3 values should be detected
        assert np.sum(clf.labels_[-3:]) >= 1


class TestStddevDetection:
    """Stddev (Z-Score) 탐지 테스트."""

    @pytest.fixture
    def detector(self):
        """기본 탐지기."""
        return CostDriftDetector(sensitivity=0.7)

    def test_detects_high_z_score(self, detector):
        """높은 Z-score를 가진 데이터 탐지."""
        # 정상 데이터 + 명확한 이상치
        costs = [100, 102, 98, 101, 99, 103, 100, 101, 99, 102, 100, 101, 98, 200]

        result = detector._detect_stddev(costs)

        assert result is not None
        assert result["is_anomaly"] == True
        assert result["z_score"] > 2.0
        assert result["confidence"] > 0.5

    def test_normal_data_no_anomaly(self, detector):
        """정상 데이터에서 이상 탐지 안됨."""
        costs = [100, 102, 98, 101, 99, 103, 100, 101, 99, 102, 100, 101, 98, 101]

        result = detector._detect_stddev(costs)

        assert result is not None
        assert result["is_anomaly"] == False

    def test_returns_none_for_insufficient_data(self, detector):
        """데이터 부족 시 None 반환."""
        costs = [100, 102, 98]

        result = detector._detect_stddev(costs)

        assert result is None

    def test_returns_none_for_zero_std(self, detector):
        """표준편차가 0일 때 None 반환."""
        costs = [100, 100, 100, 100, 100, 100, 100, 100]

        result = detector._detect_stddev(costs)

        assert result is None

    def test_sensitivity_affects_threshold(self):
        """민감도가 임계값에 영향."""
        costs = [100, 102, 98, 101, 99, 103, 100, 101, 99, 102, 100, 101, 98, 130]

        low_sens = CostDriftDetector(sensitivity=0.3)
        high_sens = CostDriftDetector(sensitivity=0.9)

        low_result = low_sens._detect_stddev(costs)
        high_result = high_sens._detect_stddev(costs)

        # 높은 민감도 = 더 많은 탐지
        if low_result and high_result:
            assert high_result["confidence"] >= low_result["confidence"]


class TestEnsembleScoring:
    """앙상블 스코어 계산 테스트."""

    @pytest.fixture
    def detector(self):
        """기본 탐지기."""
        return CostDriftDetector(sensitivity=0.7)

    def test_all_methods_agree_anomaly(self, detector):
        """모든 방법이 이상으로 동의 시 높은 신뢰도."""
        ecod_result = {"is_anomaly": True, "confidence": 0.8, "raw_score": 5.0, "method_suffix": ""}
        ratio_result = {"is_anomaly": True, "confidence": 0.7, "ratio": 2.0}
        stddev_result = {"is_anomaly": True, "confidence": 0.9, "z_score": 3.5}

        result = detector._calculate_ensemble_score(ecod_result, ratio_result, stddev_result)

        assert result["is_anomaly"] == True
        assert result["confidence"] > 0.7
        assert result["method"] == "ensemble"

    def test_majority_determines_anomaly(self, detector):
        """다수결로 이상 판정."""
        ecod_result = {"is_anomaly": True, "confidence": 0.8, "raw_score": 5.0, "method_suffix": ""}
        ratio_result = {"is_anomaly": True, "confidence": 0.7, "ratio": 2.0}
        stddev_result = {"is_anomaly": False, "confidence": 0.3, "z_score": 1.5}

        result = detector._calculate_ensemble_score(ecod_result, ratio_result, stddev_result)

        # ECOD 0.4 + Ratio 0.3 = 0.7 > 0.5, so anomaly
        assert result["is_anomaly"] == True

    def test_ecod_failure_redistributes_weights(self, detector):
        """ECOD 실패 시 가중치 재분배."""
        ecod_result = None  # ECOD 실패
        ratio_result = {"is_anomaly": True, "confidence": 0.7, "ratio": 2.0}
        stddev_result = {"is_anomaly": True, "confidence": 0.8, "z_score": 3.0}

        result = detector._calculate_ensemble_score(ecod_result, ratio_result, stddev_result)

        assert result["is_anomaly"] == True
        assert result["confidence"] > 0.7

    def test_all_methods_agree_normal(self, detector):
        """모든 방법이 정상으로 동의 시."""
        ecod_result = {"is_anomaly": False, "confidence": 0.2, "raw_score": 1.0, "method_suffix": ""}
        ratio_result = {"is_anomaly": False, "confidence": 0.1, "ratio": 1.1}
        stddev_result = {"is_anomaly": False, "confidence": 0.15, "z_score": 0.5}

        result = detector._calculate_ensemble_score(ecod_result, ratio_result, stddev_result)

        assert result["is_anomaly"] == False

    def test_lite_suffix_preserved(self, detector):
        """경량 버전 suffix 보존."""
        ecod_result = {"is_anomaly": True, "confidence": 0.8, "raw_score": 5.0, "method_suffix": "_lite"}
        ratio_result = {"is_anomaly": True, "confidence": 0.7, "ratio": 2.0}
        stddev_result = {"is_anomaly": True, "confidence": 0.9, "z_score": 3.5}

        result = detector._calculate_ensemble_score(ecod_result, ratio_result, stddev_result)

        assert result["method_suffix"] == "_lite"
        assert result["method"] == "ensemble"


class TestDetectionMethodInResult:
    """탐지 방법이 결과에 포함되는지 테스트."""

    @pytest.fixture
    def detector(self):
        """기본 탐지기."""
        return CostDriftDetector(sensitivity=0.7)

    @pytest.fixture
    def spike_data(self):
        """스파이크 패턴 서비스 데이터."""
        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=580000,
            historical_costs=[250000] * 11 + [350000, 450000, 580000],
            timestamps=[f"2025-01-{i:02d}" for i in range(1, 15)],
            currency="KRW",
        )

    def test_detection_method_in_result(self, detector, spike_data):
        """탐지 방법이 결과에 포함."""
        result = detector.analyze_service(spike_data)

        assert result.detection_method in (
            "ecod", "ecod_lite", "ratio", "stddev",
            "ensemble", "ensemble_lite", "insufficient_data"
        )
