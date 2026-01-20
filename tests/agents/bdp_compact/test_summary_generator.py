"""
SummaryGenerator 테스트.

한글 Rich Summary 생성기 단위 테스트.
"""

import pytest

from src.agents.bdp_compact.services.anomaly_detector import CostDriftResult, Severity
from src.agents.bdp_compact.services.summary_generator import AlertSummary, SummaryGenerator


class TestSummaryGenerator:
    """SummaryGenerator 테스트."""

    @pytest.fixture
    def generator_krw(self):
        """KRW 기본 생성기."""
        return SummaryGenerator(currency="KRW")

    @pytest.fixture
    def generator_usd(self):
        """USD 생성기."""
        return SummaryGenerator(currency="USD")

    @pytest.fixture
    def critical_result(self):
        """Critical 심각도 탐지 결과."""
        return CostDriftResult(
            is_anomaly=True,
            confidence_score=0.92,
            severity=Severity.CRITICAL,
            service_name="Amazon Athena",
            account_id="111111111111",
            account_name="hyundaicard-payer",
            current_cost=580000,
            historical_average=250000,
            change_percent=132.0,
            spike_duration_days=3,
            trend_direction="increasing",
            spike_start_date="2025-01-12",
            detection_method="ensemble",
        )

    @pytest.fixture
    def high_result(self):
        """High 심각도 탐지 결과."""
        return CostDriftResult(
            is_anomaly=True,
            confidence_score=0.75,
            severity=Severity.HIGH,
            service_name="AWS Lambda",
            account_id="222222222222",
            account_name="hyundaicard-member",
            current_cost=400000,
            historical_average=80000,
            change_percent=400.0,
            spike_duration_days=1,
            trend_direction="increasing",
            spike_start_date="2025-01-14",
            detection_method="ratio",
        )

    @pytest.fixture
    def low_result(self):
        """Low 심각도 탐지 결과."""
        return CostDriftResult(
            is_anomaly=True,
            confidence_score=0.45,
            severity=Severity.LOW,
            service_name="Amazon S3",
            account_id="111111111111",
            account_name="hyundaicard-payer",
            current_cost=130000,
            historical_average=120000,
            change_percent=8.3,
            spike_duration_days=0,
            trend_direction="stable",
            spike_start_date=None,
            detection_method="ecod",
        )

    def test_generate_korean_summary(self, generator_krw, critical_result):
        """한글 요약 생성."""
        summary = generator_krw.generate(critical_result)

        assert isinstance(summary, AlertSummary)
        assert "아테나" in summary.message or "Athena" in summary.message
        assert "hyundaicard-payer" in summary.message
        assert "132%" in summary.message or "132" in summary.message
        assert "심각" in summary.message or "CRITICAL" in summary.message.upper()

    def test_summary_contains_korean_cost_format(self, generator_krw, critical_result):
        """한글 비용 포맷 확인."""
        summary = generator_krw.generate(critical_result)

        # 58만원 또는 580,000원 형식
        assert "만원" in summary.message or "원" in summary.message

    def test_summary_emoji_by_severity(self, generator_krw, critical_result, high_result, low_result):
        """심각도별 이모지 확인."""
        critical_summary = generator_krw.generate(critical_result)
        high_summary = generator_krw.generate(high_result)
        low_summary = generator_krw.generate(low_result)

        assert critical_summary.severity_emoji == "🚨"
        assert high_summary.severity_emoji == "⚠️"
        assert low_summary.severity_emoji == "ℹ️"

    def test_spike_duration_in_message(self, generator_krw, critical_result):
        """스파이크 지속 기간 메시지 포함."""
        summary = generator_krw.generate(critical_result)

        # "3일 지속" 같은 메시지
        assert "3일" in summary.message or "지속" in summary.message

    def test_batch_summary_generation(self, generator_krw, critical_result, high_result, low_result):
        """일괄 요약 생성."""
        results = [critical_result, high_result, low_result]
        summary = generator_krw.generate_batch_summary(results)

        assert "3건" in summary.message or "3" in summary.message
        assert summary.severity_emoji == "🚨"  # 가장 높은 심각도

    def test_batch_summary_no_anomalies(self, generator_krw):
        """이상 없을 때 일괄 요약."""
        no_anomaly = CostDriftResult(
            is_anomaly=False,
            confidence_score=0.2,
            severity=Severity.LOW,
            service_name="Test",
            account_id="111",
            account_name="test",
            current_cost=100000,
            historical_average=100000,
            change_percent=0,
            spike_duration_days=0,
            trend_direction="stable",
            detection_method="ecod",
        )

        summary = generator_krw.generate_batch_summary([no_anomaly])

        assert "정상" in summary.message
        assert summary.severity_emoji == "✅"

    def test_usd_currency_format(self, generator_usd, critical_result):
        """USD 통화 포맷."""
        summary = generator_usd.generate(critical_result)

        # $ 기호 포함
        assert "$" in summary.message

    def test_title_format(self, generator_krw, critical_result):
        """제목 형식 확인."""
        summary = generator_krw.generate(critical_result)

        assert "비용 드리프트" in summary.title
        assert "Athena" in summary.title or "아테나" in summary.title
        assert "hyundaicard-payer" in summary.title

    def test_service_name_cleaning(self, generator_krw):
        """서비스명 정리 확인."""
        # "Amazon " 접두사 제거
        assert generator_krw._clean_service_name("Amazon Athena") == "Athena"
        assert generator_krw._clean_service_name("AWS Lambda") == "Lambda"
        assert generator_krw._clean_service_name("Amazon S3") == "S3"

    def test_cost_formatting_krw(self, generator_krw):
        """KRW 비용 포맷팅."""
        assert "만원" in generator_krw._format_cost(250000)
        assert "억원" in generator_krw._format_cost(150000000)
        assert "원" in generator_krw._format_cost(5000)

    def test_cost_formatting_usd(self, generator_usd):
        """USD 비용 포맷팅."""
        assert "$" in generator_usd._format_cost(250)
        assert "K" in generator_usd._format_cost(2500)
        assert "M" in generator_usd._format_cost(2500000)

    def test_date_formatting(self, generator_krw):
        """날짜 포맷팅."""
        assert "1월 12일" == generator_krw._format_date("2025-01-12")
        assert "12월 25일" == generator_krw._format_date("2024-12-25")

    def test_trend_direction_in_korean(self, generator_krw, critical_result):
        """트렌드 방향 한글 표시."""
        summary = generator_krw.generate(critical_result)

        # "상승" 또는 "하락" 또는 "안정"
        assert any(word in summary.message for word in ["상승", "하락", "안정"])
