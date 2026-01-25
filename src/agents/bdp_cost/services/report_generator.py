"""
Daily/Monthly Cost Report Generator.

계정 전체 서비스에 대한 비용 리포트 생성.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from src.agents.bdp_cost.services.cost_explorer_provider import ServiceCostData

logger = logging.getLogger(__name__)


@dataclass
class ServiceSummary:
    """서비스별 비용 요약."""

    service_name: str
    current_cost: float
    previous_cost: float
    change_amount: float
    change_percent: float


@dataclass
class CostReport:
    """비용 리포트."""

    report_type: str  # "daily" or "monthly"
    account_name: str
    report_date: str
    previous_date: str
    total_current: float
    total_previous: float
    total_change_amount: float
    total_change_percent: float
    services: List[ServiceSummary] = field(default_factory=list)
    top_increases: List[ServiceSummary] = field(default_factory=list)
    top_decreases: List[ServiceSummary] = field(default_factory=list)
    currency: str = "KRW"


class ReportGenerator:
    """비용 리포트 생성기."""

    def __init__(self, currency: str = "KRW"):
        """ReportGenerator 초기화.

        Args:
            currency: 통화 (KRW, USD)
        """
        self.currency = currency

    def generate_daily_report(
        self,
        cost_data_list: List[ServiceCostData],
        account_name: str,
    ) -> CostReport:
        """일간 리포트 생성.

        Args:
            cost_data_list: 서비스별 비용 데이터 리스트
            account_name: 계정명

        Returns:
            일간 비용 리포트
        """
        services = []
        total_current = 0.0
        total_previous = 0.0

        for data in cost_data_list:
            if len(data.historical_costs) < 2:
                continue

            current = data.historical_costs[-1]
            previous = data.historical_costs[-2]
            change_amount = current - previous
            change_percent = (
                (change_amount / previous * 100) if previous > 0 else 0.0
            )

            services.append(
                ServiceSummary(
                    service_name=data.service_name,
                    current_cost=current,
                    previous_cost=previous,
                    change_amount=change_amount,
                    change_percent=change_percent,
                )
            )

            total_current += current
            total_previous += previous

        # 정렬: 비용 높은 순
        services.sort(key=lambda x: x.current_cost, reverse=True)

        # Top 증가/감소
        by_change = sorted(services, key=lambda x: x.change_amount, reverse=True)
        top_increases = [s for s in by_change if s.change_amount > 0][:3]
        top_decreases = [s for s in reversed(by_change) if s.change_amount < 0][:3]

        total_change = total_current - total_previous
        total_change_pct = (
            (total_change / total_previous * 100) if total_previous > 0 else 0.0
        )

        # 날짜 추출
        report_date = "N/A"
        previous_date = "N/A"
        if cost_data_list and cost_data_list[0].timestamps:
            timestamps = cost_data_list[0].timestamps
            if len(timestamps) >= 1:
                report_date = timestamps[-1]
            if len(timestamps) >= 2:
                previous_date = timestamps[-2]

        return CostReport(
            report_type="daily",
            account_name=account_name,
            report_date=report_date,
            previous_date=previous_date,
            total_current=total_current,
            total_previous=total_previous,
            total_change_amount=total_change,
            total_change_percent=total_change_pct,
            services=services,
            top_increases=top_increases,
            top_decreases=top_decreases,
            currency=self.currency,
        )

    def format_report_text(self, report: CostReport) -> str:
        """리포트를 텍스트로 포맷팅.

        Args:
            report: 비용 리포트

        Returns:
            포맷팅된 텍스트
        """
        lines = []

        # 헤더
        report_type_kr = "일간" if report.report_type == "daily" else "월간"
        lines.append(f"📊 {report_type_kr} 비용 리포트")
        lines.append("━" * 25)
        lines.append(f"🏢 계정: {report.account_name}")
        lines.append(f"📅 기준일: {report.report_date}")
        lines.append("━" * 25)

        # 총 비용
        change_sign = "+" if report.total_change_amount >= 0 else ""
        lines.append(
            f"\n💰 총 비용: {report.total_current:,.0f}원\n"
            f"   ({change_sign}{report.total_change_amount:,.0f}원, "
            f"{change_sign}{report.total_change_percent:.1f}%)"
        )
        lines.append(f"💰 전일({report.previous_date}): {report.total_previous:,.0f}원")

        # Top 증가 서비스
        if report.top_increases:
            lines.append("\n📈 비용 증가 TOP 3:")
            for s in report.top_increases:
                lines.append(
                    f"  • {s.service_name}: "
                    f"+{s.change_amount:,.0f}원 (+{s.change_percent:.1f}%)"
                )

        # Top 감소 서비스
        if report.top_decreases:
            lines.append("\n📉 비용 감소 TOP 3:")
            for s in report.top_decreases:
                lines.append(
                    f"  • {s.service_name}: "
                    f"{s.change_amount:,.0f}원 ({s.change_percent:.1f}%)"
                )

        # 서비스별 상세 (상위 10개)
        lines.append("\n📋 서비스별 비용 (상위 10개):")
        lines.append("━" * 25)
        for s in report.services[:10]:
            change_sign = "+" if s.change_amount >= 0 else ""
            lines.append(
                f"• {s.service_name}\n"
                f"  {s.current_cost:,.0f}원 "
                f"({change_sign}{s.change_amount:,.0f}원, {change_sign}{s.change_percent:.1f}%)"
            )

        return "\n".join(lines)
