"""
Drift Chart Generator using QuickChart.io.

드리프트 시각화 차트 생성기.
QuickChart.io API를 사용하여 URL 기반 차트 이미지 생성.

Features:
- 2포인트 라인 차트 (baseline → current)
- 베이스라인 참조선 (점선, 수평)
- 증가/감소에 따른 색상 변화
- HTML 리포트의 img 태그와 호환

Reference:
- https://quickchart.io/documentation/
- Chart.js 설정 기반
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


@dataclass
class DriftChartConfig:
    """드리프트 차트 생성 설정 (MD3 기반)."""

    width: int = 400
    height: int = 200  # 가로형 차트
    background_color: str = "white"
    # MD3 Color Palette
    baseline_color: str = "rgb(25, 118, 210)"  # MD3 Primary #1976D2
    increase_color: str = "rgb(211, 47, 47)"   # MD3 Error #D32F2F
    decrease_color: str = "rgb(56, 142, 60)"   # MD3 Success #388E3C
    neutral_color: str = "rgb(117, 117, 117)"  # MD3 on-surface-variant #757575
    font_family: str = "sans-serif"


class DriftChartGenerator:
    """
    QuickChart.io 기반 드리프트 시각화 차트 생성기.

    베이스라인과 현재 값 사이의 변화를 2포인트 라인 차트로 시각화.
    베이스라인 참조선(점선)을 함께 표시하여 변화량을 직관적으로 파악.

    Usage:
        generator = DriftChartGenerator()
        url = generator.generate_chart_url(
            baseline_value=100,
            current_value=150,
            baseline_date="2025-01-01",
            current_date="2025-01-26",
            field_name="memory_size",
        )
        # url을 img 태그의 src로 사용
    """

    QUICKCHART_BASE_URL = "https://quickchart.io/chart"

    def __init__(self, config: Optional[DriftChartConfig] = None):
        """차트 생성기 초기화.

        Args:
            config: 차트 설정 (없으면 기본값 사용)
        """
        self.config = config or DriftChartConfig()

    def generate_chart_url(
        self,
        baseline_value: Any,
        current_value: Any,
        baseline_date: str,
        current_date: str,
        field_name: str,
    ) -> Optional[str]:
        """2포인트 라인 차트 URL 생성.

        Args:
            baseline_value: 베이스라인 값
            current_value: 현재 값
            baseline_date: 베이스라인 날짜 (YYYY-MM-DD 또는 표시용 문자열)
            current_date: 현재 날짜 (YYYY-MM-DD 또는 표시용 문자열)
            field_name: 필드명 (차트 제목에 사용)

        Returns:
            QuickChart 이미지 URL, 생성 불가시 None
        """
        # 숫자 값만 차트로 표시 가능
        if not self._is_numeric(baseline_value) or not self._is_numeric(current_value):
            logger.debug(
                f"Non-numeric values for chart: {field_name} "
                f"(baseline={baseline_value}, current={current_value})"
            )
            return None

        baseline_num = float(baseline_value)
        current_num = float(current_value)

        # 차트 설정 생성
        chart_config = self._build_chart_config(
            baseline_num,
            current_num,
            baseline_date,
            current_date,
            field_name,
        )

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

        logger.debug(f"Generated drift chart URL for {field_name}")
        return url

    def _is_numeric(self, value: Any) -> bool:
        """값이 숫자인지 확인.

        Args:
            value: 확인할 값

        Returns:
            숫자 여부
        """
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value)
                return True
            except ValueError:
                return False
        return False

    def _build_chart_config(
        self,
        baseline_value: float,
        current_value: float,
        baseline_date: str,
        current_date: str,
        field_name: str,
    ) -> dict:
        """Chart.js 설정 객체 생성.

        Args:
            baseline_value: 베이스라인 값
            current_value: 현재 값
            baseline_date: 베이스라인 날짜
            current_date: 현재 날짜
            field_name: 필드명

        Returns:
            Chart.js 호환 설정 딕셔너리
        """
        # 증가/감소 판단
        is_increase = current_value > baseline_value
        is_decrease = current_value < baseline_value

        # 색상 결정
        if is_increase:
            line_color = self.config.increase_color
            bg_color = "rgba(255, 99, 132, 0.15)"
            change_pct = ((current_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 100
            change_text = f"+{change_pct:.1f}%"
        elif is_decrease:
            line_color = self.config.decrease_color
            bg_color = "rgba(40, 167, 69, 0.15)"
            change_pct = ((baseline_value - current_value) / baseline_value * 100) if baseline_value != 0 else 100
            change_text = f"-{change_pct:.1f}%"
        else:
            line_color = self.config.neutral_color
            bg_color = "rgba(108, 117, 125, 0.15)"
            change_text = "0%"

        # 날짜 포맷팅 (YYYY-MM-DD → MM/DD)
        baseline_label = self._format_date_label(baseline_date)
        current_label = self._format_date_label(current_date)

        # 값 포맷팅
        baseline_display = self._format_value(baseline_value)
        current_display = self._format_value(current_value)

        # 데이터셋 구성
        datasets = [
            # 메인 라인 (baseline → current)
            {
                "label": f"{field_name} ({change_text})",
                "data": [baseline_value, current_value],
                "borderColor": line_color,
                "backgroundColor": bg_color,
                "fill": True,
                "tension": 0.3,
                "pointRadius": 8,
                "pointBackgroundColor": [
                    self.config.baseline_color,  # baseline 점은 파랑
                    line_color,  # current 점은 증감색
                ],
                "pointBorderColor": [
                    self.config.baseline_color,
                    line_color,
                ],
                "pointBorderWidth": 2,
            },
            # 베이스라인 참조선 (점선, 수평)
            {
                "label": "Baseline",
                "data": [baseline_value, baseline_value],
                "borderColor": self.config.baseline_color,
                "borderDash": [5, 5],
                "fill": False,
                "pointRadius": 0,
                "borderWidth": 2,
            },
        ]

        return {
            "type": "line",
            "data": {
                "labels": [baseline_label, current_label],
                "datasets": datasets,
            },
            "options": {
                "responsive": False,
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "bottom",
                        "labels": {
                            "boxWidth": 12,
                            "padding": 8,
                            "font": {"size": 11},
                        },
                    },
                    "title": {
                        "display": True,
                        "text": f"{field_name} 변화",
                        "font": {"size": 13, "weight": "bold"},
                        "padding": {"bottom": 10},
                    },
                },
                "scales": {
                    "y": {
                        "beginAtZero": False,
                        "ticks": {
                            "font": {"size": 10},
                        },
                        "grid": {
                            "color": "rgba(0, 0, 0, 0.05)",
                        },
                    },
                    "x": {
                        "ticks": {
                            "font": {"size": 11, "weight": "bold"},
                        },
                        "grid": {
                            "display": False,
                        },
                    },
                },
            },
        }

    def _format_date_label(self, date_str: str) -> str:
        """날짜 문자열을 MM/DD 형식으로 변환.

        Args:
            date_str: YYYY-MM-DD 형식 또는 임의 문자열

        Returns:
            MM/DD 형식 레이블 또는 원본 문자열
        """
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            return f"{dt.month}/{dt.day}"
        except (ValueError, TypeError):
            # 파싱 실패시 원본 반환 (최대 10자)
            return date_str[:10] if len(date_str) > 10 else date_str

    def _format_value(self, value: float) -> str:
        """숫자 값 포맷팅.

        Args:
            value: 숫자 값

        Returns:
            포맷된 문자열
        """
        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:.1f}B"
        elif abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        elif abs(value) >= 1_000:
            return f"{value / 1_000:.1f}K"
        elif isinstance(value, float) and not value.is_integer():
            return f"{value:.2f}"
        else:
            return f"{int(value):,}"


def generate_drift_chart_url(
    baseline_value: Any,
    current_value: Any,
    baseline_date: str,
    current_date: str,
    field_name: str,
    config: Optional[DriftChartConfig] = None,
) -> Optional[str]:
    """편의 함수: 드리프트 차트 URL 생성.

    Args:
        baseline_value: 베이스라인 값
        current_value: 현재 값
        baseline_date: 베이스라인 날짜
        current_date: 현재 날짜
        field_name: 필드명
        config: 차트 설정 (선택)

    Returns:
        QuickChart 이미지 URL
    """
    generator = DriftChartGenerator(config=config)
    return generator.generate_chart_url(
        baseline_value=baseline_value,
        current_value=current_value,
        baseline_date=baseline_date,
        current_date=current_date,
        field_name=field_name,
    )
