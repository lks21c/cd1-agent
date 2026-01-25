"""
CostTrendChartGenerator 테스트.

QuickChart.io 기반 비용 트렌드 차트 생성기 단위 테스트.
"""

from datetime import datetime, timedelta

import pytest

from src.agents.bdp_cost.services.anomaly_detector import CostDriftResult, Severity
from src.agents.bdp_cost.services.chart_generator import (
    ChartConfig,
    CostTrendChartGenerator,
    generate_cost_trend_chart_url,
)


class TestCostTrendChartGenerator:
    """CostTrendChartGenerator 테스트."""

    @pytest.fixture
    def generator(self):
        """기본 차트 생성기."""
        return CostTrendChartGenerator()

    @pytest.fixture
    def custom_config(self):
        """커스텀 차트 설정."""
        return ChartConfig(
            width=800,
            height=400,
            background_color="transparent",
            line_color="rgb(0, 128, 0)",
        )

    @pytest.fixture
    def result_with_data(self):
        """14일 데이터가 포함된 탐지 결과."""
        end_date = datetime.utcnow()
        days = 14
        timestamps = [
            (end_date - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
            for i in range(days)
        ]

        # 마지막 3일 스파이크
        historical_costs = [250000.0] * 11 + [350000.0, 450000.0, 750000.0]

        return CostDriftResult(
            is_anomaly=True,
            confidence_score=0.95,
            severity=Severity.CRITICAL,
            service_name="Amazon Athena",
            account_id="111111111111",
            account_name="bdp-prod",
            current_cost=750000.0,
            historical_average=250000.0,
            change_percent=200.0,
            spike_duration_days=3,
            trend_direction="increasing",
            spike_start_date=timestamps[11],
            detection_method="ensemble",
            historical_costs=historical_costs,
            timestamps=timestamps,
        )

    @pytest.fixture
    def result_without_data(self):
        """historical_costs 없는 탐지 결과."""
        return CostDriftResult(
            is_anomaly=True,
            confidence_score=0.95,
            severity=Severity.CRITICAL,
            service_name="Amazon Athena",
            account_id="111111111111",
            account_name="bdp-prod",
            current_cost=750000.0,
            historical_average=250000.0,
            change_percent=200.0,
            spike_duration_days=3,
            trend_direction="increasing",
            spike_start_date="2025-01-12",
            detection_method="ensemble",
            historical_costs=None,
            timestamps=None,
        )

    @pytest.fixture
    def result_insufficient_data(self):
        """데이터 포인트가 부족한 탐지 결과."""
        return CostDriftResult(
            is_anomaly=False,
            confidence_score=0.0,
            severity=Severity.LOW,
            service_name="Amazon S3",
            account_id="111111111111",
            account_name="bdp-prod",
            current_cost=100000.0,
            historical_average=0.0,
            change_percent=0.0,
            spike_duration_days=0,
            trend_direction="stable",
            detection_method="insufficient_data",
            historical_costs=[100000.0],  # 1개 포인트만
            timestamps=["2025-01-14"],
        )

    # =========================================================================
    # URL 생성 테스트
    # =========================================================================

    def test_generate_chart_url_success(self, generator, result_with_data):
        """정상 데이터로 차트 URL 생성 성공."""
        url = generator.generate_chart_url(result_with_data)

        assert url is not None
        assert url.startswith("https://quickchart.io/chart")
        assert "w=400" in url  # 카카오톡 최적화: 정사각형
        assert "h=400" in url
        assert "bkg=white" in url

    def test_generate_chart_url_contains_encoded_config(
        self, generator, result_with_data
    ):
        """생성된 URL에 인코딩된 차트 설정이 포함되어야 함."""
        url = generator.generate_chart_url(result_with_data)

        assert url is not None
        # URL에 인코딩된 차트 데이터가 포함되어야 함
        assert "c=" in url
        # 라인 차트 타입
        assert "line" in url or "%22line%22" in url

    def test_generate_chart_url_no_data(self, generator, result_without_data):
        """historical_costs 없으면 None 반환."""
        url = generator.generate_chart_url(result_without_data)

        assert url is None

    def test_generate_chart_url_insufficient_data(
        self, generator, result_insufficient_data
    ):
        """데이터 포인트 부족시 None 반환."""
        url = generator.generate_chart_url(result_insufficient_data)

        assert url is None

    # =========================================================================
    # 커스텀 설정 테스트
    # =========================================================================

    def test_custom_config(self, custom_config, result_with_data):
        """커스텀 설정으로 차트 생성."""
        generator = CostTrendChartGenerator(config=custom_config)
        url = generator.generate_chart_url(result_with_data)

        assert url is not None
        assert "w=800" in url
        assert "h=400" in url
        assert "bkg=transparent" in url

    def test_default_config(self, generator):
        """기본 설정 확인 - 카카오톡 최적화 정사각형."""
        assert generator.config.width == 400  # 카카오톡 최적화
        assert generator.config.height == 400  # 정사각형 (1:1)
        assert generator.config.background_color == "white"

    # =========================================================================
    # 날짜 포맷팅 테스트
    # =========================================================================

    def test_format_date_labels(self, generator):
        """날짜 레이블 포맷팅 - show_every_n=1로 모든 날짜 표시."""
        timestamps = ["2025-01-08", "2025-01-09", "2025-01-10"]
        # show_every_n=1로 모든 날짜 표시
        labels = generator._format_date_labels(timestamps, show_every_n=1)

        assert labels == ["1/8", "1/9", "1/10"]

    def test_format_date_labels_invalid_format(self, generator):
        """잘못된 날짜 형식 처리."""
        timestamps = ["invalid", "2025-01-09", ""]
        labels = generator._format_date_labels(timestamps, show_every_n=1)

        assert len(labels) == 3
        # 파싱 실패 시 빈 문자열 반환
        assert labels[0] == ""  # invalid -> ""
        assert labels[1] == "1/9"  # 정상 파싱
        assert labels[2] == ""  # 빈 문자열 -> ""

    # =========================================================================
    # 서비스명 처리 테스트
    # =========================================================================

    def test_clean_service_name_amazon(self, generator):
        """Amazon 접두사 제거."""
        assert generator._clean_service_name("Amazon Athena") == "Athena"
        assert generator._clean_service_name("Amazon S3") == "S3"

    def test_clean_service_name_aws(self, generator):
        """AWS 접두사 제거."""
        assert generator._clean_service_name("AWS Lambda") == "Lambda"
        assert generator._clean_service_name("AWS CloudWatch") == "CloudWatch"

    def test_clean_service_name_no_prefix(self, generator):
        """접두사 없는 서비스명."""
        assert generator._clean_service_name("EC2") == "EC2"
        assert generator._clean_service_name("RDS") == "RDS"

    # =========================================================================
    # 스파이크 처리 테스트
    # =========================================================================

    def test_find_spike_start_index_found(self, generator, result_with_data):
        """스파이크 시작 인덱스 찾기."""
        idx = generator._find_spike_start_index(
            result_with_data.historical_costs,
            result_with_data.spike_start_date,
            result_with_data.timestamps,
        )

        assert idx == 11  # 12번째 데이터 (인덱스 11)

    def test_find_spike_start_index_not_found(self, generator, result_with_data):
        """스파이크 날짜가 없는 경우."""
        idx = generator._find_spike_start_index(
            result_with_data.historical_costs,
            "2099-12-31",  # 존재하지 않는 날짜
            result_with_data.timestamps,
        )

        assert idx is None

    def test_find_spike_start_index_no_date(self, generator, result_with_data):
        """스파이크 날짜가 None인 경우."""
        idx = generator._find_spike_start_index(
            result_with_data.historical_costs,
            None,
            result_with_data.timestamps,
        )

        assert idx is None

    def test_get_point_colors_spike(self, generator):
        """스파이크 구간 포인트 색상."""
        costs = [100.0, 100.0, 100.0, 200.0, 300.0]
        avg_cost = 100.0
        spike_start_idx = 3

        colors = generator._get_point_colors(costs, avg_cost, spike_start_idx)

        # 처음 3개는 파란색 (정상)
        assert colors[0] == generator.config.line_color
        assert colors[1] == generator.config.line_color
        assert colors[2] == generator.config.line_color
        # 스파이크 구간은 빨간색
        assert colors[3] == "rgb(255, 99, 132)"
        assert colors[4] == "rgb(255, 99, 132)"

    def test_get_point_colors_threshold(self, generator):
        """임계값 초과 포인트 색상."""
        costs = [100.0, 100.0, 200.0]  # 200은 평균의 200%
        avg_cost = 100.0
        spike_start_idx = None

        colors = generator._get_point_colors(costs, avg_cost, spike_start_idx)

        # 처음 2개는 파란색
        assert colors[0] == generator.config.line_color
        assert colors[1] == generator.config.line_color
        # 임계값(150%) 초과는 주황색
        assert colors[2] == "rgb(255, 159, 64)"

    # =========================================================================
    # 편의 함수 테스트
    # =========================================================================

    def test_convenience_function(self, result_with_data):
        """generate_cost_trend_chart_url 편의 함수 테스트."""
        url = generate_cost_trend_chart_url(result_with_data)

        assert url is not None
        assert url.startswith("https://quickchart.io/chart")

    def test_convenience_function_with_config(self, result_with_data, custom_config):
        """커스텀 설정으로 편의 함수 사용."""
        url = generate_cost_trend_chart_url(result_with_data, config=custom_config)

        assert url is not None
        assert "w=800" in url

    # =========================================================================
    # 차트 설정 빌드 테스트
    # =========================================================================

    def test_build_chart_config_structure(self, generator, result_with_data):
        """차트 설정 구조 검증."""
        config = generator._build_chart_config(result_with_data)

        assert config["type"] == "line"
        assert "data" in config
        assert "options" in config
        assert "labels" in config["data"]
        assert "datasets" in config["data"]

        # 최소 2개 데이터셋 (메인 라인 + 평균선)
        assert len(config["data"]["datasets"]) >= 2

    def test_build_chart_config_labels_count(self, generator, result_with_data):
        """레이블 개수가 데이터 포인트 개수와 일치."""
        config = generator._build_chart_config(result_with_data)

        labels = config["data"]["labels"]
        data_points = config["data"]["datasets"][0]["data"]

        assert len(labels) == len(data_points)
        assert len(labels) == 14

    def test_build_chart_config_average_line(self, generator, result_with_data):
        """평균선 데이터셋 검증."""
        config = generator._build_chart_config(result_with_data)

        avg_dataset = config["data"]["datasets"][1]
        assert avg_dataset["label"] == "평균"
        assert avg_dataset["borderDash"] == [5, 5]
        # 평균선은 모든 값이 동일
        assert all(v == result_with_data.historical_average for v in avg_dataset["data"])
