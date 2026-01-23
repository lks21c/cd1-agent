"""
Rich Summary Generator for Cost Drift Alerts.

비용 드리프트 알람을 위한 한글 Rich Summary 생성기.
단순 현상 탐지가 아닌 분석 포함된 상세 요약 제공.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from src.agents.bdp_compact.services.anomaly_detector import CostDriftResult, Severity
from src.agents.bdp_compact.services.chart_generator import (
    ChartConfig,
    CostTrendChartGenerator,
)

logger = logging.getLogger(__name__)


@dataclass
class AlertSummary:
    """알람 요약 데이터."""

    title: str
    message: str
    severity_emoji: str
    service_name: str
    account_name: str
    timestamp: str
    chart_url: Optional[str] = None


class SummaryGenerator:
    """
    한글 Rich Summary 생성기.

    예시 출력:
    "아테나(hyundaicard-payer) 비용이 일평균 25만원인데
     1월 14일에 58만원으로 132% 치솟았고, 이 상승 추세가
     3일 지속되었습니다. [계정: hyundaicard-payer | 심각도: HIGH]"
    """

    SEVERITY_EMOJI = {
        Severity.CRITICAL: "🚨",
        Severity.HIGH: "⚠️",
        Severity.MEDIUM: "📊",
        Severity.LOW: "ℹ️",
    }

    SEVERITY_KOREAN = {
        Severity.CRITICAL: "심각",
        Severity.HIGH: "높음",
        Severity.MEDIUM: "보통",
        Severity.LOW: "낮음",
    }

    TREND_KOREAN = {
        "increasing": "상승",
        "decreasing": "하락",
        "stable": "안정",
    }

    def __init__(
        self,
        currency: str = "KRW",
        enable_chart: bool = True,
        chart_config: Optional[ChartConfig] = None,
    ):
        """Summary 생성기 초기화.

        Args:
            currency: 통화 단위 (KRW, USD)
            enable_chart: 차트 URL 생성 여부
            chart_config: 차트 설정 (없으면 기본값 사용)
        """
        self.currency = currency
        self.enable_chart = enable_chart
        self.chart_generator = (
            CostTrendChartGenerator(config=chart_config) if enable_chart else None
        )

    def generate(self, result: CostDriftResult) -> AlertSummary:
        """단일 탐지 결과에 대한 한글 요약 생성.

        Args:
            result: 비용 드리프트 탐지 결과

        Returns:
            AlertSummary 객체
        """
        severity_emoji = self.SEVERITY_EMOJI.get(result.severity, "📊")
        severity_korean = self.SEVERITY_KOREAN.get(result.severity, "보통")

        # 서비스명 정리 (Amazon, AWS 접두사 제거)
        service_display = self._clean_service_name(result.service_name)

        # 비용 포맷팅
        current_cost_str = self._format_cost(result.current_cost)
        avg_cost_str = self._format_cost(result.historical_average)

        # 변화 방향
        if result.change_percent > 0:
            change_direction = "상승"
            change_verb = "치솟았고"
        else:
            change_direction = "하락"
            change_verb = "떨어졌고"

        # 날짜 포맷팅
        if result.spike_start_date:
            spike_date = self._format_date(result.spike_start_date)
        else:
            spike_date = "최근"

        # 메시지 생성
        message = self._build_message(
            service_display=service_display,
            account_name=result.account_name,
            avg_cost_str=avg_cost_str,
            current_cost_str=current_cost_str,
            change_percent=abs(result.change_percent),
            change_verb=change_verb,
            spike_date=spike_date,
            spike_duration=result.spike_duration_days,
            trend_direction=result.trend_direction,
            severity_korean=severity_korean,
        )

        # 제목 생성
        title = f"{severity_emoji} 비용 드리프트: {service_display} ({result.account_name})"

        # 차트 URL 생성
        chart_url = None
        if self.chart_generator:
            chart_url = self.chart_generator.generate_chart_url(result)

        return AlertSummary(
            title=title,
            message=message,
            severity_emoji=severity_emoji,
            service_name=result.service_name,
            account_name=result.account_name,
            timestamp=datetime.utcnow().isoformat(),
            chart_url=chart_url,
        )

    def generate_batch_summary(
        self, results: List[CostDriftResult], max_items: int = 5
    ) -> AlertSummary:
        """여러 탐지 결과에 대한 통합 한글 요약 생성.

        Args:
            results: 탐지 결과 목록
            max_items: 요약에 포함할 최대 항목 수

        Returns:
            통합 AlertSummary 객체
        """
        # 이상 탐지된 결과만 필터링
        anomalies = [r for r in results if r.is_anomaly]

        if not anomalies:
            return AlertSummary(
                title="✅ 비용 정상",
                message="모든 서비스의 비용이 정상 범위 내에 있습니다.",
                severity_emoji="✅",
                service_name="all",
                account_name="all",
                timestamp=datetime.utcnow().isoformat(),
            )

        # 심각도별 카운트
        severity_counts = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 0,
            Severity.MEDIUM: 0,
            Severity.LOW: 0,
        }
        for r in anomalies:
            severity_counts[r.severity] += 1

        # 가장 높은 심각도
        highest_severity = Severity.LOW
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            if severity_counts[sev] > 0:
                highest_severity = sev
                break

        severity_emoji = self.SEVERITY_EMOJI.get(highest_severity, "📊")

        # 계정별 그룹화
        accounts = set(r.account_name for r in anomalies)

        # 제목
        title = f"{severity_emoji} 비용 드리프트 탐지: {len(anomalies)}건"

        # 메시지 본문
        lines = [
            f"총 {len(anomalies)}건의 비용 이상이 탐지되었습니다.",
            "",
            f"• 심각: {severity_counts[Severity.CRITICAL]}건",
            f"• 높음: {severity_counts[Severity.HIGH]}건",
            f"• 보통: {severity_counts[Severity.MEDIUM]}건",
            f"• 낮음: {severity_counts[Severity.LOW]}건",
            "",
            f"영향 계정: {', '.join(accounts)}",
            "",
            "주요 항목:",
        ]

        # 상위 항목 상세
        for result in anomalies[:max_items]:
            service_display = self._clean_service_name(result.service_name)
            cost_str = self._format_cost(result.current_cost)
            emoji = self.SEVERITY_EMOJI.get(result.severity, "📊")

            lines.append(
                f"  {emoji} {service_display}({result.account_name}): "
                f"{cost_str} ({result.change_percent:+.1f}%)"
            )

        if len(anomalies) > max_items:
            lines.append(f"  ... 외 {len(anomalies) - max_items}건")

        message = "\n".join(lines)

        return AlertSummary(
            title=title,
            message=message,
            severity_emoji=severity_emoji,
            service_name="multiple",
            account_name=", ".join(accounts),
            timestamp=datetime.utcnow().isoformat(),
        )

    def _build_message(
        self,
        service_display: str,
        account_name: str,
        avg_cost_str: str,
        current_cost_str: str,
        change_percent: float,
        change_verb: str,
        spike_date: str,
        spike_duration: int,
        trend_direction: str,
        severity_korean: str,
    ) -> str:
        """상세 메시지 구성.

        예: "아테나(hyundaicard-payer) 비용이 일평균 25만원인데
             1월 14일에 58만원으로 132% 치솟았고, 이 상승 추세가
             3일 지속되었습니다."
        """
        trend_korean = self.TREND_KOREAN.get(trend_direction, "안정")

        # 기본 메시지
        msg = f"{service_display}({account_name}) 비용이 일평균 {avg_cost_str}인데 "
        msg += f"{spike_date}에 {current_cost_str}로 {change_percent:.0f}% {change_verb}"

        # 지속 기간
        if spike_duration > 1:
            msg += f" 이 {trend_korean} 추세가 {spike_duration}일 지속되었습니다."
        else:
            msg += " 즉각적인 확인이 필요합니다."

        # 메타 정보
        msg += f"\n\n[계정: {account_name} | 심각도: {severity_korean}]"

        return msg

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
                name = name[len(prefix) :]
        return name.strip()

    def _format_cost(self, cost: float) -> str:
        """비용을 읽기 쉬운 형식으로 포맷팅.

        Args:
            cost: 비용 값

        Returns:
            포맷팅된 문자열
        """
        if self.currency == "KRW":
            if cost >= 100000000:  # 1억 이상
                return f"{cost / 100000000:.1f}억원"
            elif cost >= 10000:  # 1만 이상
                return f"{cost / 10000:.0f}만원"
            else:
                return f"{cost:,.0f}원"
        else:  # USD
            if cost >= 1000000:
                return f"${cost / 1000000:.1f}M"
            elif cost >= 1000:
                return f"${cost / 1000:.1f}K"
            else:
                return f"${cost:,.2f}"

    def _format_date(self, date_str: str) -> str:
        """날짜를 한글 형식으로 포맷팅.

        Args:
            date_str: YYYY-MM-DD 형식 날짜

        Returns:
            "M월 D일" 형식
        """
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            return f"{dt.month}월 {dt.day}일"
        except (ValueError, TypeError):
            return date_str


def generate_analysis(result: CostDriftResult, language: str = "ko") -> str:
    """탐지 결과에 대한 자연어 분석 생성 (KakaoTalk용).

    단순 현상 탐지가 아닌, 심각도/변화율/추세/패턴 컨텍스트/신뢰도에 대한
    분석 문장을 생성합니다.

    Args:
        result: 비용 드리프트 탐지 결과
        language: 언어 코드 ("ko" 또는 "en")

    Returns:
        분석 문장 (한글 또는 영어)
    """
    if language == "en":
        return _generate_analysis_en(result)
    return _generate_analysis_ko(result)


def _generate_analysis_ko(result: CostDriftResult) -> str:
    """한글 분석 문장 생성.

    Args:
        result: 비용 드리프트 탐지 결과

    Returns:
        한글 분석 문장
    """
    lines = []

    # 1. 심각도 설명
    severity_explanations = {
        Severity.CRITICAL: "즉각적인 조치가 필요한 심각한 이상입니다.",
        Severity.HIGH: "주의가 필요한 높은 수준의 이상입니다.",
        Severity.MEDIUM: "모니터링이 필요한 중간 수준의 이상입니다.",
        Severity.LOW: "참고용 낮은 수준의 변동입니다.",
    }
    lines.append(f"[심각도] {severity_explanations.get(result.severity, '알 수 없음')}")

    # 2. 변화율 설명
    change = result.change_percent
    if abs(change) >= 200:
        change_desc = "급격한"
    elif abs(change) >= 100:
        change_desc = "큰 폭의"
    elif abs(change) >= 50:
        change_desc = "상당한"
    else:
        change_desc = "소폭의"

    direction = "상승" if change > 0 else "하락"
    lines.append(f"[변화율] 평균 대비 {abs(change):.1f}% {direction} ({change_desc} 변화)")

    # 3. 추세 설명
    trend_descriptions = {
        "increasing": "비용이 지속적으로 증가하는 추세입니다.",
        "decreasing": "비용이 지속적으로 감소하는 추세입니다.",
        "stable": "비용이 안정적인 추세를 보입니다.",
    }
    lines.append(f"[추세] {trend_descriptions.get(result.trend_direction, '분석 불가')}")

    # 4. 지속 기간 설명
    if result.spike_duration_days > 1:
        lines.append(f"[지속] 이 변동이 {result.spike_duration_days}일간 지속되었습니다.")

    # 5. 패턴 컨텍스트 설명
    if result.pattern_contexts:
        pattern_str = ", ".join(result.pattern_contexts)
        lines.append(f"[패턴] 인식된 패턴: {pattern_str}")
        lines.append("  → 패턴 인식으로 인해 신뢰도가 조정되었습니다.")

    # 6. 신뢰도 설명
    confidence = result.confidence_score
    raw_confidence = result.raw_confidence_score

    if confidence >= 0.9:
        confidence_desc = "매우 높은 신뢰도로 탐지되었습니다."
    elif confidence >= 0.7:
        confidence_desc = "높은 신뢰도로 탐지되었습니다."
    elif confidence >= 0.5:
        confidence_desc = "중간 신뢰도로 탐지되었습니다."
    else:
        confidence_desc = "낮은 신뢰도로 탐지되었습니다."

    confidence_line = f"[신뢰도] {confidence:.1%} - {confidence_desc}"
    if raw_confidence and raw_confidence != confidence:
        confidence_line += f" (원본: {raw_confidence:.1%})"
    lines.append(confidence_line)

    # 7. 탐지 방법 설명
    method_descriptions = {
        "ecod": "ECOD 알고리즘",
        "ecod_lite": "경량 ECOD 알고리즘",
        "ensemble": "앙상블 탐지 (ECOD+Ratio+Stddev)",
        "ensemble_lite": "경량 앙상블 탐지",
        "stddev": "Z-Score 기반 탐지",
        "ratio": "비율 기반 탐지",
        "insufficient_data": "데이터 부족",
    }
    method = result.detection_method
    method_desc = method_descriptions.get(method, method)
    lines.append(f"[탐지 방법] {method_desc}")

    return "\n".join(lines)


def _generate_analysis_en(result: CostDriftResult) -> str:
    """영어 분석 문장 생성.

    Args:
        result: 비용 드리프트 탐지 결과

    Returns:
        영어 분석 문장
    """
    lines = []

    # 1. Severity explanation
    severity_explanations = {
        Severity.CRITICAL: "Immediate action required - critical anomaly.",
        Severity.HIGH: "High severity anomaly requiring attention.",
        Severity.MEDIUM: "Medium severity anomaly - monitoring recommended.",
        Severity.LOW: "Low severity variation - for reference.",
    }
    lines.append(f"[Severity] {severity_explanations.get(result.severity, 'Unknown')}")

    # 2. Change rate explanation
    change = result.change_percent
    if abs(change) >= 200:
        change_desc = "dramatic"
    elif abs(change) >= 100:
        change_desc = "significant"
    elif abs(change) >= 50:
        change_desc = "notable"
    else:
        change_desc = "minor"

    direction = "increase" if change > 0 else "decrease"
    lines.append(f"[Change] {abs(change):.1f}% {direction} from average ({change_desc} change)")

    # 3. Trend explanation
    trend_descriptions = {
        "increasing": "Costs are showing an increasing trend.",
        "decreasing": "Costs are showing a decreasing trend.",
        "stable": "Costs are stable.",
    }
    lines.append(f"[Trend] {trend_descriptions.get(result.trend_direction, 'Unable to analyze')}")

    # 4. Duration explanation
    if result.spike_duration_days > 1:
        lines.append(f"[Duration] This variation has persisted for {result.spike_duration_days} days.")

    # 5. Pattern context explanation
    if result.pattern_contexts:
        pattern_str = ", ".join(result.pattern_contexts)
        lines.append(f"[Patterns] Recognized patterns: {pattern_str}")
        lines.append("  → Confidence adjusted based on pattern recognition.")

    # 6. Confidence explanation
    confidence = result.confidence_score
    raw_confidence = result.raw_confidence_score

    if confidence >= 0.9:
        confidence_desc = "Detected with very high confidence."
    elif confidence >= 0.7:
        confidence_desc = "Detected with high confidence."
    elif confidence >= 0.5:
        confidence_desc = "Detected with moderate confidence."
    else:
        confidence_desc = "Detected with low confidence."

    confidence_line = f"[Confidence] {confidence:.1%} - {confidence_desc}"
    if raw_confidence and raw_confidence != confidence:
        confidence_line += f" (raw: {raw_confidence:.1%})"
    lines.append(confidence_line)

    # 7. Detection method explanation
    method_descriptions = {
        "ecod": "ECOD algorithm",
        "ecod_lite": "Lightweight ECOD algorithm",
        "ensemble": "Ensemble detection (ECOD+Ratio+Stddev)",
        "ensemble_lite": "Lightweight ensemble detection",
        "stddev": "Z-Score based detection",
        "ratio": "Ratio based detection",
        "insufficient_data": "Insufficient data",
    }
    method = result.detection_method
    method_desc = method_descriptions.get(method, method)
    lines.append(f"[Method] {method_desc}")

    return "\n".join(lines)
