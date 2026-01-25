#!/usr/bin/env python3
"""
Daily Cost Report Script.

AWS 계정의 일간 비용 리포트를 생성하여 KakaoTalk으로 발송.

Usage:
    python scripts/send_daily_report.py
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.bdp_cost.services.cost_explorer_provider import (
    MockCostExplorerProvider,
    ServiceCostData,
)
from src.agents.bdp_cost.services.kakao_notifier import KakaoNotifier
from src.agents.bdp_cost.services.report_generator import ReportGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_mock_data() -> list[ServiceCostData]:
    """Mock 데이터 생성 (다양한 서비스).

    Returns:
        서비스별 비용 데이터 리스트
    """
    # 1월 15일 ~ 1월 21일 (7일)
    timestamps = [f"2025-01-{d:02d}" for d in range(15, 22)]

    services = [
        # (서비스명, 히스토리컬 비용)
        ("Amazon Athena", [250000, 260000, 255000, 248000, 252000, 250000, 750000]),
        ("Amazon EC2", [500000, 510000, 505000, 520000, 515000, 518000, 525000]),
        ("Amazon S3", [100000, 102000, 101000, 103000, 100500, 101000, 99000]),
        ("AWS Lambda", [50000, 52000, 51000, 53000, 54000, 55000, 58000]),
        ("Amazon DynamoDB", [80000, 82000, 81000, 79000, 80000, 78000, 75000]),
        ("Amazon RDS", [300000, 305000, 302000, 308000, 310000, 312000, 315000]),
        ("Amazon CloudWatch", [30000, 31000, 30500, 31500, 32000, 32500, 33000]),
        ("AWS KMS", [10000, 10000, 10000, 10000, 10000, 10000, 10000]),
    ]

    result = []
    for service_name, costs in services:
        result.append(
            ServiceCostData(
                service_name=service_name,
                account_id="111111111111",
                account_name="bdp-prod",
                current_cost=costs[-1],
                historical_costs=costs,
                timestamps=timestamps,
                currency="KRW",
            )
        )

    return result


def main():
    """메인 실행 함수."""
    print("=" * 60)
    print("일간 비용 리포트 생성 및 KakaoTalk 발송")
    print("=" * 60)

    # 1. Mock 데이터 구성
    print("\n[1/3] 비용 데이터 구성...")
    cost_data = create_mock_data()
    print(f"  - 서비스 수: {len(cost_data)}개")
    print(f"  - 계정: {cost_data[0].account_name}")

    # 2. 리포트 생성
    print("\n[2/3] 일간 리포트 생성...")
    generator = ReportGenerator(currency="KRW")
    report = generator.generate_daily_report(
        cost_data_list=cost_data,
        account_name=cost_data[0].account_name,
    )

    report_text = generator.format_report_text(report)
    print(f"  - 기준일: {report.report_date}")
    print(f"  - 총 비용: {report.total_current:,.0f}원")
    print(f"  - 전일 대비: {report.total_change_amount:+,.0f}원 ({report.total_change_percent:+.1f}%)")

    print("\n--- 리포트 미리보기 ---")
    print(report_text)
    print("--- 미리보기 끝 ---\n")

    # 3. KakaoTalk 발송
    print("[3/3] KakaoTalk 리포트 발송...")
    notifier = KakaoNotifier()

    if not notifier.load_tokens():
        print("  ❌ 토큰 로드 실패. 토큰 설정을 확인하세요.")
        return 1

    success = notifier.send_report(report, report_text)

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
