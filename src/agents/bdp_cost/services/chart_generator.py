"""
Cost Trend Chart Generator using QuickChart.io.

비용 트렌드 라인 그래프 생성기.
QuickChart.io API를 사용하여 URL 기반 차트 이미지 생성.

Features:
- 14일간 비용 트렌드 라인 그래프
- 평균선 (점선) 표시
- 스파이크 구간 시각적 강조
- 카카오톡 피드 메시지의 image_url과 호환

Reference:
- https://quickchart.io/documentation/
- Chart.js 설정 기반
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote

from src.agents.bdp_cost.services.anomaly_detector import CostDriftResult

logger = logging.getLogger(__name__)


@dataclass
class ChartConfig:
    """차트 생성 설정.

    Note:
        카카오톡 피드 메시지에서 이미지가 잘리지 않도록
        정사각형(1:1) 비율 사용. 모바일에서 전체 표시 보장.
    """

    width: int = 400  # 카카오톡 최적화 (정사각형)
    height: int = 400
    background_color: str = "white"
    line_color: str = "rgb(54, 162, 235)"
    average_line_color: str = "rgb(255, 99, 132)"
    spike_color: str = "rgba(255, 99, 132, 0.2)"
    font_family: str = "sans-serif"
    locale: str = "ko-KR"


class CostTrendChartGenerator:
    """
    QuickChart.io 기반 비용 트렌드 차트 생성기.

    14일간 비용 추이를 라인 그래프로 시각화.
    평균선과 스파이크 구간을 시각적으로 강조.

    Usage:
        generator = CostTrendChartGenerator()
        url = generator.generate_chart_url(result)
        # url을 카카오톡 피드 메시지의 image_url로 사용
    """

    QUICKCHART_BASE_URL = "https://quickchart.io/chart"

    def __init__(self, config: Optional[ChartConfig] = None):
        """차트 생성기 초기화.

        Args:
            config: 차트 설정 (없으면 기본값 사용)
        """
        self.config = config or ChartConfig()

    def generate_chart_url(self, result: CostDriftResult) -> Optional[str]:
        """비용 드리프트 결과에서 차트 URL 생성.

        Args:
            result: 비용 드리프트 탐지 결과 (historical_costs, timestamps 필요)

        Returns:
            QuickChart 이미지 URL, 데이터 부족시 None
        """
        if not result.historical_costs or not result.timestamps:
            logger.warning(
                f"No historical data for chart generation: {result.service_name}"
            )
            return None

        if len(result.historical_costs) < 2:
            logger.warning(
                f"Insufficient data points for chart: {result.service_name}"
            )
            return None

        # 차트 설정 생성
        chart_config = self._build_chart_config(result)

        # URL 생성
        chart_json = json.dumps(chart_config, ensure_ascii=False)
        encoded_config = quote(chart_json)

        url = (
            f"{self.QUICKCHART_BASE_URL}"
            f"?c={encoded_config}"
            f"&w={self.config.width}"
            f"&h={self.config.height}"
            f"&bkg={self.config.background_color}"
        )

        logger.debug(f"Generated chart URL for {result.service_name}")
        return url

    def _build_chart_config(self, result: CostDriftResult) -> Dict:
        """Chart.js 설정 객체 생성.

        Args:
            result: 비용 드리프트 탐지 결과

        Returns:
            Chart.js 호환 설정 딕셔너리
        """
        costs = result.historical_costs
        timestamps = result.timestamps

        # 날짜 레이블 포맷팅 (MM/DD)
        labels = self._format_date_labels(timestamps)

        # 평균값 (마지막 값 제외)
        avg_cost = result.historical_average

        # 스파이크 시작 인덱스 계산
        spike_start_idx = self._find_spike_start_index(
            costs, result.spike_start_date, timestamps
        )

        # 데이터셋 구성
        datasets = [
            # 메인 비용 라인
            {
                "label": self._clean_service_name(result.service_name),
                "data": costs,
                "borderColor": self.config.line_color,
                "backgroundColor": "rgba(54, 162, 235, 0.1)",
                "fill": True,
                "tension": 0.3,
                "pointRadius": 4,
                "pointBackgroundColor": self._get_point_colors(
                    costs, avg_cost, spike_start_idx
                ),
            },
            # 평균선 (점선)
            {
                "label": "평균",
                "data": [avg_cost] * len(costs),
                "borderColor": self.config.average_line_color,
                "borderDash": [5, 5],
                "fill": False,
                "pointRadius": 0,
            },
        ]

        # 스파이크 구간 배경 (annotation 플러그인 대신 별도 데이터셋)
        if spike_start_idx is not None and spike_start_idx < len(costs) - 1:
            spike_zone = self._create_spike_zone_data(
                costs, spike_start_idx, avg_cost
            )
            if spike_zone:
                datasets.append(spike_zone)

        return {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": datasets,
            },
            "options": {
                "responsive": False,
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "bottom",  # 정사각형 레이아웃에 최적화
                        "labels": {"boxWidth": 12, "padding": 8},
                    },
                    "title": {
                        "display": True,
                        "text": f"{self._clean_service_name(result.service_name)} 비용 추이",
                        "font": {"size": 12},  # 축소하여 차트 영역 확보
                        "padding": {"bottom": 8},
                    },
                },
                "scales": {
                    "y": {
                        "beginAtZero": False,
                        "title": {
                            "display": True,
                            "text": "비용 (원)",
                        },
                        "ticks": {
                            "callback": "function(value) { return value.toLocaleString() + '원'; }",
                        },
                    },
                    "x": {
                        "title": {
                            "display": True,
                            "text": "날짜",
                        },
                    },
                },
            },
        }

    def _format_date_labels(
        self, timestamps: List[str], show_every_n: int = 3
    ) -> List[str]:
        """타임스탬프를 MM/DD 형식 레이블로 변환 (간격 적용).

        카카오톡 정사각형 차트에서 가독성 확보를 위해
        N일 간격으로만 레이블 표시 (나머지는 빈 문자열).

        Args:
            timestamps: YYYY-MM-DD 형식 날짜 목록
            show_every_n: 레이블 표시 간격 (기본 3일)

        Returns:
            MM/DD 형식 레이블 목록 (간격 적용)
        """
        labels = []
        for idx, ts in enumerate(timestamps):
            try:
                dt = datetime.strptime(ts[:10], "%Y-%m-%d")
                # N일 간격 또는 첫/마지막 날짜만 표시
                if idx % show_every_n == 0 or idx == len(timestamps) - 1:
                    labels.append(f"{dt.month}/{dt.day}")
                else:
                    labels.append("")
            except (ValueError, TypeError):
                labels.append("")
        return labels

    def _find_spike_start_index(
        self,
        costs: List[float],
        spike_start_date: Optional[str],
        timestamps: List[str],
    ) -> Optional[int]:
        """스파이크 시작 인덱스 찾기.

        Args:
            costs: 비용 목록
            spike_start_date: 스파이크 시작 날짜
            timestamps: 타임스탬프 목록

        Returns:
            스파이크 시작 인덱스, 없으면 None
        """
        if not spike_start_date:
            return None

        spike_date_str = spike_start_date[:10]
        for idx, ts in enumerate(timestamps):
            if ts[:10] == spike_date_str:
                return idx

        return None

    def _get_point_colors(
        self,
        costs: List[float],
        avg_cost: float,
        spike_start_idx: Optional[int],
    ) -> List[str]:
        """각 포인트의 색상 결정 (스파이크 강조).

        Args:
            costs: 비용 목록
            avg_cost: 평균 비용
            spike_start_idx: 스파이크 시작 인덱스

        Returns:
            포인트 색상 목록
        """
        colors = []
        threshold = avg_cost * 1.5  # 평균의 150% 초과시 강조

        for idx, cost in enumerate(costs):
            if spike_start_idx is not None and idx >= spike_start_idx:
                # 스파이크 구간은 빨간색
                colors.append("rgb(255, 99, 132)")
            elif cost > threshold:
                # 임계값 초과는 주황색
                colors.append("rgb(255, 159, 64)")
            else:
                # 정상은 파란색
                colors.append(self.config.line_color)

        return colors

    def _create_spike_zone_data(
        self,
        costs: List[float],
        spike_start_idx: int,
        avg_cost: float,
    ) -> Optional[Dict]:
        """스파이크 구간 시각화용 데이터셋 생성.

        Args:
            costs: 비용 목록
            spike_start_idx: 스파이크 시작 인덱스
            avg_cost: 평균 비용

        Returns:
            스파이크 구간 데이터셋, 필요 없으면 None
        """
        # 스파이크 구간의 비용만 표시하는 별도 라인
        spike_data = [None] * len(costs)
        for idx in range(spike_start_idx, len(costs)):
            spike_data[idx] = costs[idx]

        return {
            "label": "스파이크",
            "data": spike_data,
            "borderColor": "rgba(255, 99, 132, 0.8)",
            "backgroundColor": self.config.spike_color,
            "fill": True,
            "tension": 0.3,
            "pointRadius": 6,
            "pointBackgroundColor": "rgb(255, 99, 132)",
        }

    def _clean_service_name(self, service_name: str) -> str:
        """서비스명 정리 (Amazon, AWS 접두사 제거).

        Args:
            service_name: 원본 서비스명

        Returns:
            정리된 서비스명
        """
        name = service_name
        prefixes = ["Amazon ", "AWS ", "Amazon"]
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]
        return name.strip()


def generate_cost_trend_chart_url(
    result: CostDriftResult,
    config: Optional[ChartConfig] = None,
) -> Optional[str]:
    """편의 함수: 비용 드리프트 결과에서 차트 URL 생성.

    Args:
        result: 비용 드리프트 탐지 결과
        config: 차트 설정 (선택)

    Returns:
        QuickChart 이미지 URL
    """
    generator = CostTrendChartGenerator(config=config)
    return generator.generate_chart_url(result)
