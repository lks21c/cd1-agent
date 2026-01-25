"""
Chart Generator using QuickChart.io (Common).

QuickChart.io API를 사용하여 URL 기반 차트 이미지 생성.
bdp_cost, bdp_drift 등 여러 에이전트에서 공유.

Features:
- 라인 그래프, 바 차트 생성
- 평균선 표시
- 강조 구간 시각화
- 카카오톡 피드 메시지 호환

Reference:
- https://quickchart.io/documentation/
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

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
    highlight_color: str = "rgb(255, 99, 132)"
    highlight_bg_color: str = "rgba(255, 99, 132, 0.2)"
    warning_color: str = "rgb(255, 159, 64)"
    font_family: str = "sans-serif"
    locale: str = "ko-KR"


class ChartGenerator:
    """
    QuickChart.io 기반 차트 생성기 (Common).

    Generic 인터페이스로 다양한 데이터 시각화 지원.

    Usage:
        generator = ChartGenerator()
        url = generator.generate_line_chart(
            labels=["1/1", "1/2", "1/3"],
            datasets=[
                {"label": "비용", "data": [100, 150, 200]},
            ],
            title="비용 추이"
        )
    """

    QUICKCHART_BASE_URL = "https://quickchart.io/chart"

    def __init__(self, config: Optional[ChartConfig] = None):
        """차트 생성기 초기화.

        Args:
            config: 차트 설정 (없으면 기본값 사용)
        """
        self.config = config or ChartConfig()

    def generate_line_chart(
        self,
        labels: List[str],
        datasets: List[Dict[str, Any]],
        title: Optional[str] = None,
        y_axis_label: Optional[str] = None,
        x_axis_label: Optional[str] = None,
        average_line: Optional[float] = None,
        average_label: str = "평균",
    ) -> Optional[str]:
        """라인 차트 URL 생성.

        Args:
            labels: X축 레이블
            datasets: 데이터셋 목록 [{"label": "...", "data": [...], ...}, ...]
            title: 차트 제목
            y_axis_label: Y축 레이블
            x_axis_label: X축 레이블
            average_line: 평균선 값 (None이면 표시 안함)
            average_label: 평균선 레이블

        Returns:
            QuickChart 이미지 URL
        """
        if not labels or not datasets:
            logger.warning("No data for chart generation")
            return None

        # 데이터셋 구성
        chart_datasets = []

        for i, ds in enumerate(datasets):
            chart_ds = {
                "label": ds.get("label", f"Dataset {i+1}"),
                "data": ds.get("data", []),
                "borderColor": ds.get("color", self.config.line_color),
                "backgroundColor": ds.get("bg_color", "rgba(54, 162, 235, 0.1)"),
                "fill": ds.get("fill", True),
                "tension": ds.get("tension", 0.3),
                "pointRadius": ds.get("point_radius", 4),
            }

            if "point_colors" in ds:
                chart_ds["pointBackgroundColor"] = ds["point_colors"]

            chart_datasets.append(chart_ds)

        # 평균선 추가
        if average_line is not None:
            chart_datasets.append({
                "label": average_label,
                "data": [average_line] * len(labels),
                "borderColor": self.config.highlight_color,
                "borderDash": [5, 5],
                "fill": False,
                "pointRadius": 0,
            })

        # Chart.js 설정
        chart_config = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": chart_datasets,
            },
            "options": {
                "responsive": False,
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "bottom",
                        "labels": {"boxWidth": 12, "padding": 8},
                    },
                },
                "scales": {
                    "y": {
                        "beginAtZero": False,
                    },
                    "x": {},
                },
            },
        }

        # 제목 추가
        if title:
            chart_config["options"]["plugins"]["title"] = {
                "display": True,
                "text": title,
                "font": {"size": 12},
                "padding": {"bottom": 8},
            }

        # 축 레이블 추가
        if y_axis_label:
            chart_config["options"]["scales"]["y"]["title"] = {
                "display": True,
                "text": y_axis_label,
            }

        if x_axis_label:
            chart_config["options"]["scales"]["x"]["title"] = {
                "display": True,
                "text": x_axis_label,
            }

        return self._build_url(chart_config)

    def generate_bar_chart(
        self,
        labels: List[str],
        datasets: List[Dict[str, Any]],
        title: Optional[str] = None,
        y_axis_label: Optional[str] = None,
        horizontal: bool = False,
    ) -> Optional[str]:
        """바 차트 URL 생성.

        Args:
            labels: 레이블
            datasets: 데이터셋 목록
            title: 차트 제목
            y_axis_label: Y축 레이블
            horizontal: 가로 바 차트 여부

        Returns:
            QuickChart 이미지 URL
        """
        if not labels or not datasets:
            logger.warning("No data for chart generation")
            return None

        chart_datasets = []

        for i, ds in enumerate(datasets):
            chart_ds = {
                "label": ds.get("label", f"Dataset {i+1}"),
                "data": ds.get("data", []),
                "backgroundColor": ds.get("colors", self._generate_colors(len(labels))),
            }
            chart_datasets.append(chart_ds)

        chart_config = {
            "type": "horizontalBar" if horizontal else "bar",
            "data": {
                "labels": labels,
                "datasets": chart_datasets,
            },
            "options": {
                "responsive": False,
                "plugins": {
                    "legend": {
                        "display": len(datasets) > 1,
                        "position": "bottom",
                    },
                },
            },
        }

        if title:
            chart_config["options"]["plugins"]["title"] = {
                "display": True,
                "text": title,
            }

        if y_axis_label:
            chart_config["options"]["scales"] = {
                "y": {"title": {"display": True, "text": y_axis_label}},
            }

        return self._build_url(chart_config)

    def generate_doughnut_chart(
        self,
        labels: List[str],
        data: List[float],
        title: Optional[str] = None,
        colors: Optional[List[str]] = None,
    ) -> Optional[str]:
        """도넛 차트 URL 생성.

        Args:
            labels: 레이블
            data: 데이터 값
            title: 차트 제목
            colors: 색상 목록

        Returns:
            QuickChart 이미지 URL
        """
        if not labels or not data:
            logger.warning("No data for chart generation")
            return None

        chart_config = {
            "type": "doughnut",
            "data": {
                "labels": labels,
                "datasets": [{
                    "data": data,
                    "backgroundColor": colors or self._generate_colors(len(labels)),
                }],
            },
            "options": {
                "responsive": False,
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "bottom",
                    },
                },
            },
        }

        if title:
            chart_config["options"]["plugins"]["title"] = {
                "display": True,
                "text": title,
            }

        return self._build_url(chart_config)

    def _build_url(self, chart_config: Dict[str, Any]) -> str:
        """QuickChart URL 생성.

        Args:
            chart_config: Chart.js 설정

        Returns:
            QuickChart 이미지 URL
        """
        chart_json = json.dumps(chart_config, ensure_ascii=False)
        encoded_config = quote(chart_json)

        url = (
            f"{self.QUICKCHART_BASE_URL}"
            f"?c={encoded_config}"
            f"&w={self.config.width}"
            f"&h={self.config.height}"
            f"&bkg={self.config.background_color}"
        )

        logger.debug(f"Generated chart URL: {url[:100]}...")
        return url

    def _generate_colors(self, count: int) -> List[str]:
        """차트용 색상 생성.

        Args:
            count: 필요한 색상 수

        Returns:
            색상 목록
        """
        base_colors = [
            "rgba(54, 162, 235, 0.8)",
            "rgba(255, 99, 132, 0.8)",
            "rgba(255, 206, 86, 0.8)",
            "rgba(75, 192, 192, 0.8)",
            "rgba(153, 102, 255, 0.8)",
            "rgba(255, 159, 64, 0.8)",
            "rgba(199, 199, 199, 0.8)",
            "rgba(83, 102, 255, 0.8)",
            "rgba(255, 99, 255, 0.8)",
            "rgba(99, 255, 132, 0.8)",
        ]

        # 색상 반복
        colors = []
        for i in range(count):
            colors.append(base_colors[i % len(base_colors)])
        return colors

    @staticmethod
    def format_date_labels(
        timestamps: List[str],
        show_every_n: int = 3,
    ) -> List[str]:
        """타임스탬프를 MM/DD 형식 레이블로 변환.

        Args:
            timestamps: YYYY-MM-DD 형식 날짜 목록
            show_every_n: 레이블 표시 간격

        Returns:
            MM/DD 형식 레이블 목록
        """
        labels = []
        for idx, ts in enumerate(timestamps):
            try:
                dt = datetime.strptime(ts[:10], "%Y-%m-%d")
                if idx % show_every_n == 0 or idx == len(timestamps) - 1:
                    labels.append(f"{dt.month}/{dt.day}")
                else:
                    labels.append("")
            except (ValueError, TypeError):
                labels.append("")
        return labels
