"""
Pattern Recognizers 테스트.

요일 패턴, 추세 패턴 인식기 단위 테스트.
False Positive 감소 전략 검증.
"""

from datetime import datetime, timedelta

import pytest

from src.agents.bdp_cost.services.cost_explorer_provider import ServiceCostData
from src.agents.bdp_cost.services.pattern_recognizers import (
    DayOfWeekRecognizer,
    MonthCycleRecognizer,
    PatternChain,
    PatternContext,
    PatternType,
    ServiceProfileRecognizer,
    TrendRecognizer,
    create_default_pattern_chain,
)


class TestDayOfWeekRecognizer:
    """DayOfWeekRecognizer 테스트."""

    @pytest.fixture
    def recognizer(self):
        """요일 패턴 인식기."""
        return DayOfWeekRecognizer()

    @pytest.fixture
    def weekday_normal_data(self):
        """평일 정상 패턴 데이터 (월요일 비용이 평일 평균 범위 내)."""
        # 2025-01-06 is Monday, 2025-01-04 and 2025-01-05 are weekend
        # Generate 14 days of data ending on a Monday
        end_date = datetime(2025, 1, 13)  # Monday

        historical_costs = []
        timestamps = []

        for i in range(14):
            date = end_date - timedelta(days=13 - i)
            is_weekend = date.weekday() >= 5

            # Weekday: ~100000, Weekend: ~60000
            if is_weekend:
                cost = 60000 + (i % 3) * 2000
            else:
                cost = 100000 + (i % 5) * 3000

            historical_costs.append(cost)
            timestamps.append(date.strftime("%Y-%m-%d"))

        # Current cost (Monday) is within weekday average range
        current_cost = 105000  # Within ±30% of weekday avg ~103000

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=current_cost,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    @pytest.fixture
    def weekday_spike_data(self):
        """평일 스파이크 패턴 데이터 (월요일 비용이 평일 평균 대비 급증)."""
        end_date = datetime(2025, 1, 13)  # Monday

        historical_costs = []
        timestamps = []

        for i in range(14):
            date = end_date - timedelta(days=13 - i)
            is_weekend = date.weekday() >= 5

            if is_weekend:
                cost = 60000
            else:
                cost = 100000

            historical_costs.append(cost)
            timestamps.append(date.strftime("%Y-%m-%d"))

        # Current cost (Monday) is 200% of weekday average - clear spike
        current_cost = 200000

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=current_cost,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    @pytest.fixture
    def weekend_normal_data(self):
        """주말 정상 패턴 데이터."""
        end_date = datetime(2025, 1, 12)  # Sunday

        historical_costs = []
        timestamps = []

        for i in range(14):
            date = end_date - timedelta(days=13 - i)
            is_weekend = date.weekday() >= 5

            if is_weekend:
                cost = 60000 + (i % 3) * 2000
            else:
                cost = 100000

            historical_costs.append(cost)
            timestamps.append(date.strftime("%Y-%m-%d"))

        # Current cost (Sunday) is within weekend average range
        current_cost = 62000

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=current_cost,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    def test_weekday_pattern_reduces_confidence(self, recognizer, weekday_normal_data):
        """평일 비용이 평일 평균 범위 내면 confidence 하향."""
        result = recognizer.recognize(weekday_normal_data)

        assert result is not None
        assert result.pattern_type == PatternType.DAY_OF_WEEK
        assert result.confidence_adjustment == DayOfWeekRecognizer.WEEKDAY_ADJUSTMENT
        assert "평일" in result.explanation

    def test_weekend_pattern_reduces_confidence(self, recognizer, weekend_normal_data):
        """주말 비용이 주말 평균 범위 내면 confidence 하향."""
        result = recognizer.recognize(weekend_normal_data)

        assert result is not None
        assert result.pattern_type == PatternType.DAY_OF_WEEK
        assert result.confidence_adjustment == DayOfWeekRecognizer.WEEKDAY_ADJUSTMENT
        assert "주말" in result.explanation

    def test_no_pattern_for_spike(self, recognizer, weekday_spike_data):
        """평일 평균 범위 벗어나면 패턴 미인식."""
        result = recognizer.recognize(weekday_spike_data)

        assert result is None

    def test_insufficient_data_returns_none(self, recognizer):
        """데이터 부족 시 None 반환."""
        data = ServiceCostData(
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=100000,
            historical_costs=[100000, 100000, 100000],  # 3일만
            timestamps=["2025-01-01", "2025-01-02", "2025-01-03"],
        )

        result = recognizer.recognize(data)
        assert result is None


class TestTrendRecognizer:
    """TrendRecognizer 테스트."""

    @pytest.fixture
    def recognizer(self):
        """추세 패턴 인식기."""
        return TrendRecognizer()

    @pytest.fixture
    def trend_normal_data(self):
        """추세선 내 정상 패턴 데이터."""
        # Linear growth: 100000 + 5000 * day
        base = 100000
        growth = 5000

        historical_costs = [base + growth * i for i in range(14)]
        timestamps = [
            (datetime(2025, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(14)
        ]

        # Current cost follows the trend (expected ~170000)
        current_cost = 168000  # Within 15% of expected

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=current_cost,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    @pytest.fixture
    def trend_spike_data(self):
        """추세선 벗어난 스파이크 데이터."""
        base = 100000
        growth = 5000

        historical_costs = [base + growth * i for i in range(14)]
        timestamps = [
            (datetime(2025, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(14)
        ]

        # Current cost is way above trend (expected ~170000)
        current_cost = 300000  # 76% above expected

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=current_cost,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    def test_trend_pattern_reduces_confidence(self, recognizer, trend_normal_data):
        """추세선 범위 내면 confidence 하향."""
        result = recognizer.recognize(trend_normal_data)

        assert result is not None
        assert result.pattern_type == PatternType.TREND
        assert result.confidence_adjustment == TrendRecognizer.TREND_ADJUSTMENT
        assert "추세선" in result.explanation

    def test_no_pattern_for_spike(self, recognizer, trend_spike_data):
        """추세선 벗어나면 패턴 미인식."""
        result = recognizer.recognize(trend_spike_data)

        assert result is None

    def test_insufficient_data_returns_none(self, recognizer):
        """데이터 부족 시 None 반환."""
        data = ServiceCostData(
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=100000,
            historical_costs=[100000, 105000, 110000],  # 3일만
            timestamps=["2025-01-01", "2025-01-02", "2025-01-03"],
        )

        result = recognizer.recognize(data)
        assert result is None


class TestPatternChain:
    """PatternChain 테스트."""

    @pytest.fixture
    def chain(self):
        """기본 패턴 체인."""
        return PatternChain(
            recognizers=[
                DayOfWeekRecognizer(),
                TrendRecognizer(),
            ],
            max_adjustment=-0.4,
        )

    @pytest.fixture
    def multi_pattern_data(self):
        """여러 패턴이 동시에 적용되는 데이터 (추세선 패턴)."""
        # 순수 추세선 데이터 - 추세 패턴 확실히 인식되도록
        base = 100000
        growth = 5000

        historical_costs = [base + growth * i for i in range(14)]
        timestamps = [
            (datetime(2025, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(14)
        ]

        # Current cost follows the trend (expected ~170000)
        current_cost = 168000  # Within 15% of expected

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=current_cost,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    def test_recognize_all_returns_all_patterns(self, chain, multi_pattern_data):
        """모든 인식된 패턴 반환."""
        contexts = chain.recognize_all(multi_pattern_data)

        # At least one pattern should be recognized
        assert len(contexts) >= 1

    def test_get_total_adjustment_respects_max(self, chain, multi_pattern_data):
        """조정값 합산 시 최대값 제한."""
        adjustment = chain.get_total_adjustment(multi_pattern_data)

        # Should not exceed max_adjustment
        assert adjustment >= -0.4
        assert adjustment <= 0

    def test_get_explanations(self, chain, multi_pattern_data):
        """설명 문자열 리스트 반환."""
        explanations = chain.get_explanations(multi_pattern_data)

        assert isinstance(explanations, list)
        for exp in explanations:
            assert isinstance(exp, str)

    def test_empty_chain_returns_zero(self):
        """빈 체인은 0 반환."""
        chain = PatternChain(recognizers=[])
        data = ServiceCostData(
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=100000,
            historical_costs=[100000] * 14,
            timestamps=[f"2025-01-{i:02d}" for i in range(1, 15)],
        )

        adjustment = chain.get_total_adjustment(data)
        assert adjustment == 0.0


class TestPatternChainFactory:
    """create_default_pattern_chain 테스트."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """테스트 전후 설정 캐시 초기화."""
        from src.agents.bdp_cost.services.config_loader import reset_config_cache
        reset_config_cache()
        yield
        reset_config_cache()

    def test_enabled_returns_chain(self, monkeypatch):
        """활성화 시 체인 반환."""
        monkeypatch.setenv("BDP_PATTERN_RECOGNITION", "true")
        chain = create_default_pattern_chain()

        assert chain is not None
        assert len(chain.recognizers) >= 2

    def test_disabled_returns_none(self, monkeypatch):
        """비활성화 시 None 반환."""
        monkeypatch.setenv("BDP_PATTERN_RECOGNITION", "false")
        chain = create_default_pattern_chain()

        assert chain is None

    def test_explicit_enabled_overrides_env(self, monkeypatch):
        """명시적 enabled가 환경 변수 우선."""
        monkeypatch.setenv("BDP_PATTERN_RECOGNITION", "false")
        chain = create_default_pattern_chain(enabled=True)

        assert chain is not None

    def test_explicit_disabled_overrides_env(self, monkeypatch):
        """명시적 disabled가 환경 변수 우선."""
        monkeypatch.setenv("BDP_PATTERN_RECOGNITION", "true")
        chain = create_default_pattern_chain(enabled=False)

        assert chain is None

    def test_max_adjustment_from_env(self, monkeypatch):
        """환경 변수에서 max_adjustment 읽기."""
        monkeypatch.setenv("BDP_PATTERN_RECOGNITION", "true")
        monkeypatch.setenv("BDP_PATTERN_MAX_ADJUSTMENT", "0.3")
        chain = create_default_pattern_chain()

        assert chain is not None
        assert chain.max_adjustment == -0.3


class TestIntegrationWithDetector:
    """CostDriftDetector와의 통합 테스트."""

    @pytest.fixture
    def detector_with_patterns(self, monkeypatch):
        """패턴 인식 활성화된 탐지기."""
        monkeypatch.setenv("BDP_PATTERN_RECOGNITION", "true")
        monkeypatch.setenv("BDP_PATTERN_MODE", "active")

        from src.agents.bdp_cost.services.anomaly_detector import CostDriftDetector
        return CostDriftDetector(sensitivity=0.7, pattern_recognition_enabled=True)

    @pytest.fixture
    def detector_without_patterns(self, monkeypatch):
        """패턴 인식 비활성화된 탐지기."""
        monkeypatch.setenv("BDP_PATTERN_RECOGNITION", "false")

        from src.agents.bdp_cost.services.anomaly_detector import CostDriftDetector
        return CostDriftDetector(sensitivity=0.7, pattern_recognition_enabled=False)

    @pytest.fixture
    def pattern_applicable_data(self):
        """패턴 적용 가능한 데이터 (추세선 내 정상 증가)."""
        base = 100000
        growth = 5000

        historical_costs = [base + growth * i for i in range(14)]
        timestamps = [
            (datetime(2025, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(14)
        ]

        # Current cost follows the trend
        current_cost = 168000

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=current_cost,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    def test_pattern_reduces_confidence(
        self, detector_with_patterns, detector_without_patterns, pattern_applicable_data
    ):
        """패턴 인식이 confidence를 낮춤."""
        result_with = detector_with_patterns.analyze_service(pattern_applicable_data)
        result_without = detector_without_patterns.analyze_service(pattern_applicable_data)

        # Pattern recognition should reduce confidence
        assert result_with.confidence_score <= result_without.confidence_score

        # raw_confidence should be preserved
        if result_with.raw_confidence_score is not None:
            assert result_with.raw_confidence_score >= result_with.confidence_score

    def test_result_includes_pattern_contexts(
        self, detector_with_patterns, pattern_applicable_data
    ):
        """결과에 패턴 컨텍스트 포함."""
        result = detector_with_patterns.analyze_service(pattern_applicable_data)

        assert hasattr(result, "pattern_contexts")
        assert isinstance(result.pattern_contexts, list)

    def test_result_includes_raw_confidence(
        self, detector_with_patterns, pattern_applicable_data
    ):
        """결과에 원본 신뢰도 포함."""
        result = detector_with_patterns.analyze_service(pattern_applicable_data)

        assert hasattr(result, "raw_confidence_score")
        assert result.raw_confidence_score is not None


class TestMonthCycleRecognizer:
    """MonthCycleRecognizer 테스트."""

    @pytest.fixture
    def recognizer(self):
        """월초/월말 패턴 인식기."""
        return MonthCycleRecognizer()

    @pytest.fixture
    def month_start_normal_data(self):
        """월초 정상 패턴 데이터 (3일은 월초)."""
        # 2025-01-03 is month start (day 3)
        end_date = datetime(2025, 1, 3)

        historical_costs = []
        timestamps = []

        for i in range(21):  # 3주 데이터
            date = end_date - timedelta(days=20 - i)
            day = date.day

            # 월초(1-5일): ~150000, 다른 날: ~100000
            if day in [1, 2, 3, 4, 5]:
                cost = 150000 + (i % 3) * 5000
            else:
                cost = 100000 + (i % 5) * 2000

            historical_costs.append(cost)
            timestamps.append(date.strftime("%Y-%m-%d"))

        # Current cost (day 3) is within month-start average range
        current_cost = 155000  # Within ±30% of month-start avg ~152500

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=current_cost,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    @pytest.fixture
    def month_start_spike_data(self):
        """월초 스파이크 패턴 데이터."""
        end_date = datetime(2025, 1, 3)

        historical_costs = []
        timestamps = []

        for i in range(21):
            date = end_date - timedelta(days=20 - i)
            day = date.day

            if day in [1, 2, 3, 4, 5]:
                cost = 150000
            else:
                cost = 100000

            historical_costs.append(cost)
            timestamps.append(date.strftime("%Y-%m-%d"))

        # Current cost (day 3) is way above month-start average
        current_cost = 300000  # 100% above expected

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=current_cost,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    @pytest.fixture
    def mid_month_data(self):
        """월 중간 데이터 (패턴 미적용)."""
        end_date = datetime(2025, 1, 15)  # day 15 - not month start/end

        historical_costs = []
        timestamps = []

        for i in range(14):
            date = end_date - timedelta(days=13 - i)
            historical_costs.append(100000 + i * 1000)
            timestamps.append(date.strftime("%Y-%m-%d"))

        return ServiceCostData(
            service_name="Test Service",
            account_id="111111111111",
            account_name="test-account",
            current_cost=113000,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    def test_month_start_pattern_reduces_confidence(self, recognizer, month_start_normal_data):
        """월초 비용이 월초 평균 범위 내면 confidence 하향."""
        result = recognizer.recognize(month_start_normal_data)

        assert result is not None
        assert result.pattern_type == PatternType.MONTH_CYCLE
        assert result.confidence_adjustment == MonthCycleRecognizer.MONTH_CYCLE_ADJUSTMENT
        assert "월초" in result.explanation

    def test_no_pattern_for_spike(self, recognizer, month_start_spike_data):
        """월초 평균 범위 벗어나면 패턴 미인식."""
        result = recognizer.recognize(month_start_spike_data)

        assert result is None

    def test_no_pattern_for_mid_month(self, recognizer, mid_month_data):
        """월 중간에는 패턴 미인식."""
        result = recognizer.recognize(mid_month_data)

        assert result is None

    def test_insufficient_data_returns_none(self, recognizer):
        """데이터 부족 시 None 반환."""
        data = ServiceCostData(
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=100000,
            historical_costs=[100000, 100000, 100000],  # 3일만
            timestamps=["2025-01-01", "2025-01-02", "2025-01-03"],
        )

        result = recognizer.recognize(data)
        assert result is None

    def test_custom_days_config(self):
        """커스텀 월초/월말 일자 설정."""
        recognizer = MonthCycleRecognizer(
            month_start_days=[1, 2, 3],
            month_end_days=[28, 29, 30, 31],
        )

        assert recognizer.month_start_days == [1, 2, 3]
        assert recognizer.month_end_days == [28, 29, 30, 31]


class TestServiceProfileRecognizer:
    """ServiceProfileRecognizer 테스트."""

    @pytest.fixture
    def recognizer(self):
        """서비스 프로파일 패턴 인식기."""
        return ServiceProfileRecognizer()

    @pytest.fixture
    def lambda_spike_data(self):
        """Lambda 스파이크 패턴 데이터."""
        # Lambda는 스파이크 정상 서비스
        end_date = datetime(2025, 1, 14)

        # 변동이 큰 비용 패턴 (CV >= 0.3)
        historical_costs = [50000, 150000, 80000, 200000, 60000, 180000, 90000,
                          220000, 70000, 160000, 100000, 190000, 85000, 250000]
        timestamps = [
            (end_date - timedelta(days=13 - i)).strftime("%Y-%m-%d")
            for i in range(14)
        ]

        return ServiceCostData(
            service_name="AWS Lambda",
            account_id="111111111111",
            account_name="test-account",
            current_cost=250000,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    @pytest.fixture
    def stable_lambda_data(self):
        """Lambda 안정 패턴 데이터 (스파이크 아님)."""
        end_date = datetime(2025, 1, 14)

        # 변동이 적은 비용 패턴 (CV < 0.3)
        historical_costs = [100000 + (i % 3) * 2000 for i in range(14)]
        timestamps = [
            (end_date - timedelta(days=13 - i)).strftime("%Y-%m-%d")
            for i in range(14)
        ]

        return ServiceCostData(
            service_name="AWS Lambda",
            account_id="111111111111",
            account_name="test-account",
            current_cost=104000,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    @pytest.fixture
    def non_spike_service_data(self):
        """스파이크 정상 서비스가 아닌 서비스 데이터."""
        end_date = datetime(2025, 1, 14)

        # 변동이 큰 비용 패턴이지만 스파이크 정상 서비스 아님
        historical_costs = [50000, 150000, 80000, 200000, 60000, 180000, 90000,
                          220000, 70000, 160000, 100000, 190000, 85000, 250000]
        timestamps = [
            (end_date - timedelta(days=13 - i)).strftime("%Y-%m-%d")
            for i in range(14)
        ]

        return ServiceCostData(
            service_name="Amazon EC2",  # EC2는 스파이크 정상 서비스 아님
            account_id="111111111111",
            account_name="test-account",
            current_cost=250000,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

    def test_spike_service_pattern_reduces_confidence(self, recognizer, lambda_spike_data):
        """스파이크 정상 서비스는 confidence 하향."""
        result = recognizer.recognize(lambda_spike_data)

        assert result is not None
        assert result.pattern_type == PatternType.SERVICE_PROFILE
        assert result.confidence_adjustment == ServiceProfileRecognizer.SERVICE_PROFILE_ADJUSTMENT
        assert "Lambda" in result.explanation

    def test_stable_spike_service_no_pattern(self, recognizer, stable_lambda_data):
        """안정 패턴의 스파이크 서비스는 패턴 미인식."""
        result = recognizer.recognize(stable_lambda_data)

        # Lambda지만 실제로 스파이크 패턴이 아니므로 None
        assert result is None

    def test_non_spike_service_no_pattern(self, recognizer, non_spike_service_data):
        """스파이크 정상 서비스가 아니면 패턴 미인식."""
        result = recognizer.recognize(non_spike_service_data)

        assert result is None

    def test_custom_services_config(self):
        """커스텀 스파이크 정상 서비스 설정."""
        recognizer = ServiceProfileRecognizer(
            spike_normal_services=["Custom Service A", "Custom Service B"]
        )

        assert "Custom Service A" in recognizer.spike_normal_services
        assert "Custom Service B" in recognizer.spike_normal_services
        assert "AWS Lambda" not in recognizer.spike_normal_services

    def test_env_var_services_config(self, monkeypatch):
        """환경 변수에서 스파이크 정상 서비스 설정."""
        monkeypatch.setenv("BDP_SPIKE_NORMAL_SERVICES", "ServiceX, ServiceY, ServiceZ")

        recognizer = ServiceProfileRecognizer()

        assert "ServiceX" in recognizer.spike_normal_services
        assert "ServiceY" in recognizer.spike_normal_services
        assert "ServiceZ" in recognizer.spike_normal_services

    def test_partial_service_name_match(self, recognizer):
        """서비스명 부분 일치 테스트."""
        end_date = datetime(2025, 1, 14)
        historical_costs = [50000, 150000, 80000, 200000, 60000, 180000, 90000,
                          220000, 70000, 160000, 100000, 190000, 85000, 250000]
        timestamps = [
            (end_date - timedelta(days=13 - i)).strftime("%Y-%m-%d")
            for i in range(14)
        ]

        # "AWS Lambda" matches partial "lambda"
        data = ServiceCostData(
            service_name="AWS Lambda Functions",
            account_id="111111111111",
            account_name="test-account",
            current_cost=250000,
            historical_costs=historical_costs,
            timestamps=timestamps,
            currency="KRW",
        )

        result = recognizer.recognize(data)
        assert result is not None


class TestConfigBasedPatternChain:
    """설정 파일 기반 패턴 체인 테스트."""

    def test_creates_chain_with_config(self, monkeypatch, tmp_path):
        """설정 파일로 패턴 체인 생성."""
        import json

        # 설정 파일 생성
        config = {
            "ensemble": {"weights": {"ecod": 0.4, "ratio": 0.3, "stddev": 0.3}},
            "patterns": {
                "enabled": True,
                "mode": "active",
                "max_adjustment": 0.5,
                "day_of_week": {"enabled": True},
                "trend": {"enabled": True},
                "month_cycle": {"enabled": True, "adjustment": -0.15},
                "service_profile": {
                    "enabled": True,
                    "spike_normal_services": ["Test Service"]
                }
            }
        }

        config_file = tmp_path / "detection_config.json"
        config_file.write_text(json.dumps(config))

        monkeypatch.setenv("BDP_DETECTION_CONFIG_PATH", str(config_file))

        # 캐시 초기화
        from src.agents.bdp_cost.services.config_loader import reset_config_cache
        reset_config_cache()

        chain = create_default_pattern_chain()

        assert chain is not None
        # 4개 인식기: DayOfWeek, Trend, MonthCycle, ServiceProfile
        assert len(chain.recognizers) == 4

        # 캐시 초기화 복원
        reset_config_cache()

    def test_disabled_recognizers_not_included(self, monkeypatch, tmp_path):
        """비활성화된 인식기는 체인에 포함 안됨."""
        import json

        config = {
            "patterns": {
                "enabled": True,
                "mode": "active",
                "max_adjustment": 0.4,
                "day_of_week": {"enabled": True},
                "trend": {"enabled": False},  # 비활성화
                "month_cycle": {"enabled": False},  # 비활성화
                "service_profile": {"enabled": False}  # 비활성화
            }
        }

        config_file = tmp_path / "detection_config.json"
        config_file.write_text(json.dumps(config))

        monkeypatch.setenv("BDP_DETECTION_CONFIG_PATH", str(config_file))

        from src.agents.bdp_cost.services.config_loader import reset_config_cache
        reset_config_cache()

        chain = create_default_pattern_chain()

        assert chain is not None
        # DayOfWeek만 활성화
        assert len(chain.recognizers) == 1

        reset_config_cache()
