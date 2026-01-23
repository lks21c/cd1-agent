#!/usr/bin/env python3
"""
Athena Spike Alert Script.

TC 시나리오 기반 Athena 비용 스파이크 탐지 및 KakaoTalk 알림 발송.

TC 시나리오 (test_detect_athena_spike_jan21):
- 서비스: Amazon Athena
- 계정: bdp-prod (111111111111)
- 정상 비용: 25만원
- 스파이크 비용: 75만원
- 변화율: +200%
- 심각도: CRITICAL

Usage:
    python scripts/send_athena_alert.py
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.bdp_compact.services.anomaly_detector import CostDriftDetector
from src.agents.bdp_compact.services.cost_explorer_provider import ServiceCostData
from src.agents.bdp_compact.services.kakao_notifier import KakaoNotifier
from src.agents.bdp_compact.services.summary_generator import SummaryGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_athena_spike_data() -> ServiceCostData:
    """TC 시나리오 데이터 생성.

    test_detect_athena_spike_jan21 시나리오:
    - 13일간 정상 (25만원)
    - 1일 스파이크 (75만원)
    """
    # 1월 8일 ~ 1월 21일 (14일)
    timestamps = [f"2025-01-{d:02d}" for d in range(8, 22)]

    # 13일 정상 + 1일 스파이크
    historical_costs = [250000.0] * 13 + [750000.0]

    return ServiceCostData(
        service_name="Amazon Athena",
        account_id="111111111111",
        account_name="bdp-prod",
        current_cost=750000.0,
        historical_costs=historical_costs,
        timestamps=timestamps,
        currency="KRW",
    )


def main():
    """메인 실행 함수."""
    print("=" * 60)
    print("Athena 비용 스파이크 탐지 및 KakaoTalk 알림")
    print("=" * 60)

    # 1. TC 시나리오 데이터 구성
    print("\n[1/4] TC 시나리오 데이터 구성...")
    data = create_athena_spike_data()
    print(f"  - 서비스: {data.service_name}")
    print(f"  - 계정: {data.account_name} ({data.account_id})")
    print(f"  - 현재 비용: {data.current_cost:,.0f}원")
    print(f"  - 평균 비용: {sum(data.historical_costs[:-1])/13:,.0f}원")

    # 2. 비용 드리프트 탐지
    print("\n[2/4] 비용 드리프트 탐지...")
    detector = CostDriftDetector(sensitivity=0.7)
    result = detector.analyze_service(data)

    print(f"  - 이상 탐지: {'예' if result.is_anomaly else '아니오'}")
    print(f"  - 심각도: {result.severity.value.upper()}")
    print(f"  - 변화율: {result.change_percent:+.1f}%")
    print(f"  - 신뢰도: {result.confidence_score:.1%}")
    print(f"  - 탐지 방법: {result.detection_method}")

    # 3. 요약 생성
    print("\n[3/4] 알림 요약 생성...")
    generator = SummaryGenerator(currency="KRW")
    summary = generator.generate(result)

    print(f"  - 제목: {summary.title}")
    print(f"  - 메시지:\n{summary.message}")
    if summary.chart_url:
        print(f"  - 차트 URL: {summary.chart_url[:80]}...")

    # 4. KakaoTalk 발송
    print("\n[4/4] KakaoTalk 알림 발송...")
    notifier = KakaoNotifier()

    if not notifier.load_tokens():
        print("  ❌ 토큰 로드 실패. 토큰 설정을 확인하세요.")
        print("     실행: python -m src.agents.bdp_compact.services.kakao_notifier")
        return 1

    success = notifier.send_alert(result, summary)

    if success:
        print("  ✅ KakaoTalk 발송 성공!")
    else:
        print("  ❌ KakaoTalk 발송 실패")
        return 1

    print("\n" + "=" * 60)
    print("완료!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
