#!/usr/bin/env python3
"""
카카오톡 차트 테스트 발송 스크립트.
400x400 정사각형 차트가 카카오톡에서 잘 보이는지 확인.

의존성 최소화를 위해 필요한 클래스 직접 정의.
"""
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

import requests


# ============================================================================
# Minimal Data Classes (의존성 없이)
# ============================================================================

class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CostDriftResult:
    service_name: str
    current_cost: float
    historical_average: float
    change_percent: float
    severity: Severity
    confidence_score: float
    anomaly_type: str
    historical_costs: List[float]
    timestamps: List[str]
    spike_start_date: Optional[str] = None
    spike_duration_days: int = 0
    detection_method: str = "ecod"


@dataclass
class AlertSummary:
    title: str
    message: str
    chart_url: Optional[str] = None
    detection_time: Optional[str] = None


@dataclass
class ChartConfig:
    """차트 생성 설정 (400x400 정사각형)."""
    width: int = 400
    height: int = 400
    background_color: str = "white"
    line_color: str = "rgb(54, 162, 235)"
    average_line_color: str = "rgb(255, 99, 132)"
    spike_color: str = "rgba(255, 99, 132, 0.2)"


# ============================================================================
# Chart Generator (간소화)
# ============================================================================

class CostTrendChartGenerator:
    QUICKCHART_BASE_URL = "https://quickchart.io/chart"

    def __init__(self, config: Optional[ChartConfig] = None):
        self.config = config or ChartConfig()

    def generate_chart_url(self, result: CostDriftResult) -> Optional[str]:
        if not result.historical_costs or not result.timestamps:
            return None

        chart_config = self._build_chart_config(result)
        chart_json = json.dumps(chart_config, ensure_ascii=False)
        encoded_config = quote(chart_json)

        return (
            f"{self.QUICKCHART_BASE_URL}"
            f"?c={encoded_config}"
            f"&w={self.config.width}"
            f"&h={self.config.height}"
            f"&bkg={self.config.background_color}"
        )

    def _build_chart_config(self, result: CostDriftResult) -> dict:
        costs = result.historical_costs
        labels = self._format_date_labels(result.timestamps)
        avg_cost = result.historical_average

        datasets = [
            {
                "label": result.service_name.replace("Amazon ", ""),
                "data": costs,
                "borderColor": self.config.line_color,
                "backgroundColor": "rgba(54, 162, 235, 0.1)",
                "fill": True,
                "tension": 0.3,
                "pointRadius": 4,
            },
            {
                "label": "평균",
                "data": [avg_cost] * len(costs),
                "borderColor": self.config.average_line_color,
                "borderDash": [5, 5],
                "fill": False,
                "pointRadius": 0,
            },
        ]

        return {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": False,
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "bottom",
                        "labels": {"boxWidth": 12, "padding": 8},
                    },
                    "title": {
                        "display": True,
                        "text": f"{result.service_name.replace('Amazon ', '')} 비용 추이",
                        "font": {"size": 12},
                        "padding": {"bottom": 8},
                    },
                },
                "scales": {
                    "y": {
                        "beginAtZero": False,
                        "title": {"display": True, "text": "비용 (원)"},
                    },
                    "x": {
                        "title": {"display": True, "text": "날짜"},
                    },
                },
            },
        }

    def _format_date_labels(self, timestamps: List[str], show_every_n: int = 3) -> List[str]:
        labels = []
        for idx, ts in enumerate(timestamps):
            try:
                dt = datetime.strptime(ts[:10], "%Y-%m-%d")
                if idx % show_every_n == 0 or idx == len(timestamps) - 1:
                    labels.append(f"{dt.month}/{dt.day}")
                else:
                    labels.append("")
            except:
                labels.append("")
        return labels


# ============================================================================
# Kakao Notifier (간소화)
# ============================================================================

class KakaoNotifier:
    SEND_ME_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    TOKEN_URL = "https://kauth.kakao.com/oauth/token"

    SEVERITY_EMOJI = {
        Severity.CRITICAL: "🚨",
        Severity.HIGH: "⚠️",
        Severity.MEDIUM: "📊",
        Severity.LOW: "ℹ️",
    }

    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.rest_api_key = None
        self.token_path = Path(__file__).parent.parent / "src/agents/bdp_cost/conf/kakao_tokens.json"
        self.config_path = Path(__file__).parent.parent / "src/agents/bdp_cost/conf/kakao_config.json"

    def load_tokens(self) -> bool:
        try:
            # REST API 키 로드
            if self.config_path.exists():
                with open(self.config_path) as f:
                    config = json.load(f)
                self.rest_api_key = config.get("rest_api_key")

            # 토큰 로드
            with open(self.token_path) as f:
                data = json.load(f)
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            return True
        except Exception as e:
            print(f"토큰 로드 실패: {e}")
            return False

    def refresh_access_token(self) -> bool:
        if not self.refresh_token or not self.rest_api_key:
            return False

        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.rest_api_key,
                    "refresh_token": self.refresh_token,
                },
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()

            self.access_token = result["access_token"]
            if "refresh_token" in result:
                self.refresh_token = result["refresh_token"]

            # 토큰 저장
            with open(self.token_path, "w") as f:
                json.dump({
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                }, f, indent=2)

            print("✅ 토큰 갱신 완료")
            return True
        except Exception as e:
            print(f"토큰 갱신 실패: {e}")
            return False

    def send_alert(self, result: CostDriftResult, summary: AlertSummary) -> bool:
        emoji = self.SEVERITY_EMOJI.get(result.severity, "📊")

        title = f"{emoji} {summary.title}"
        description = (
            f"{summary.message}\n\n"
            f"💰 현재 비용: {result.current_cost:,.0f}원\n"
            f"📈 변화율: {result.change_percent:+.1f}%\n"
            f"📊 신뢰도: {result.confidence_score:.1%}"
        )

        template_object = {
            "object_type": "feed",
            "content": {
                "title": title,
                "description": description,
                "link": {
                    "web_url": "https://console.aws.amazon.com",
                    "mobile_web_url": "https://console.aws.amazon.com",
                },
            },
        }

        if summary.chart_url:
            template_object["content"]["image_url"] = summary.chart_url

        return self._send_memo(template_object)

    def _send_memo(self, template_object: dict) -> bool:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"template_object": json.dumps(template_object)}

        try:
            response = requests.post(
                self.SEND_ME_URL, headers=headers, data=data, timeout=10
            )

            # 토큰 만료 시 갱신 후 재시도
            if response.status_code == 401:
                print("🔄 토큰 만료, 갱신 중...")
                if self.refresh_access_token():
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    response = requests.post(
                        self.SEND_ME_URL, headers=headers, data=data, timeout=10
                    )
                else:
                    return False

            response.raise_for_status()
            result = response.json()
            return result.get("result_code") == 0

        except Exception as e:
            print(f"발송 실패: {e}")
            return False


# ============================================================================
# Main
# ============================================================================

def create_test_data() -> CostDriftResult:
    """테스트용 비용 데이터 생성 (14일)."""
    today = datetime.now()

    costs = [
        15000, 14500, 15200, 14800, 15100,  # 정상
        15300, 14900, 15000, 15500,          # 정상
        18000, 22000, 25000, 28000, 32000,   # 스파이크
    ]

    timestamps = [
        (today - timedelta(days=13-i)).strftime("%Y-%m-%d")
        for i in range(14)
    ]

    return CostDriftResult(
        service_name="Amazon EC2",
        current_cost=32000.0,
        historical_average=15150.0,
        change_percent=111.2,
        severity=Severity.HIGH,
        confidence_score=0.92,
        anomaly_type="cost_spike",
        historical_costs=costs,
        timestamps=timestamps,
        spike_start_date=timestamps[9],
        spike_duration_days=5,
    )


def main():
    print("=" * 60)
    print("🧪 카카오톡 차트 테스트 (400x400 정사각형)")
    print("=" * 60)

    # 1. 테스트 데이터
    result = create_test_data()
    print(f"\n📊 테스트 데이터:")
    print(f"   서비스: {result.service_name}")
    print(f"   현재 비용: {result.current_cost:,.0f}원")
    print(f"   변화율: {result.change_percent:+.1f}%")

    # 2. 차트 URL 생성
    generator = CostTrendChartGenerator()
    chart_url = generator.generate_chart_url(result)

    print(f"\n📈 차트 설정:")
    print(f"   크기: {generator.config.width}x{generator.config.height} (정사각형)")

    # 브라우저에서 확인용
    print(f"\n🔗 차트 URL (브라우저에서 확인):")
    print(f"   {chart_url[:120]}...")

    # 3. 카카오톡 발송
    summary = AlertSummary(
        title="EC2 비용 급증 감지 (차트 테스트)",
        message="최근 5일간 EC2 비용이 평균 대비 111% 증가했습니다.",
        chart_url=chart_url,
        detection_time=datetime.now().isoformat(),
    )

    print("\n📱 카카오톡 발송 중...")
    notifier = KakaoNotifier()

    if not notifier.load_tokens():
        print("❌ 토큰 로드 실패")
        return

    success = notifier.send_alert(result, summary)

    if success:
        print("\n✅ 발송 성공! 카카오톡을 확인하세요.")
        print("   - 이미지가 잘리지 않고 전체가 보이는지 확인")
        print("   - X축 레이블이 3일 간격으로 표시되는지 확인")
    else:
        print("\n❌ 발송 실패")


if __name__ == "__main__":
    main()
