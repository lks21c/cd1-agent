"""
Summary Generator for Drift Alerts.

드리프트 알람을 위한 한글 요약 생성기.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from src.agents.bdp_drift.bdp_drift.services.models import DriftResult, DriftSeverity

logger = logging.getLogger(__name__)


@dataclass
class DriftAlertSummary:
    """드리프트 알람 요약."""

    title: str
    message: str
    severity_emoji: str
    resource_type: str
    resource_id: str
    timestamp: str
    drift_count: int
    critical_count: int
    high_count: int


class DriftSummaryGenerator:
    """
    한글 드리프트 요약 생성기.

    예시 출력:
    "Glue 테이블 'analytics/users'에서 3건의 설정 드리프트가 탐지되었습니다.
     테이블 스키마(columns)가 변경되어 즉각적인 확인이 필요합니다.
     [리소스: glue/analytics/users | 심각도: CRITICAL]"
    """

    SEVERITY_EMOJI = {
        DriftSeverity.CRITICAL: "🚨",
        DriftSeverity.HIGH: "⚠️",
        DriftSeverity.MEDIUM: "📊",
        DriftSeverity.LOW: "ℹ️",
    }

    SEVERITY_KOREAN = {
        DriftSeverity.CRITICAL: "심각",
        DriftSeverity.HIGH: "높음",
        DriftSeverity.MEDIUM: "보통",
        DriftSeverity.LOW: "낮음",
    }

    RESOURCE_TYPE_KOREAN = {
        "glue": "Glue 카탈로그",
        "athena": "Athena 워크그룹",
        "emr": "EMR 클러스터",
        "sagemaker": "SageMaker",
        "s3": "S3 버킷",
        "mwaa": "MWAA 환경",
        "msk": "MSK 클러스터",
        "lambda": "Lambda 함수",
    }

    def __init__(self):
        """Summary 생성기 초기화."""
        pass

    def generate(self, result: DriftResult) -> DriftAlertSummary:
        """단일 탐지 결과에 대한 한글 요약 생성.

        Args:
            result: 드리프트 탐지 결과

        Returns:
            DriftAlertSummary 객체
        """
        severity_emoji = self.SEVERITY_EMOJI.get(result.severity, "📊")
        severity_korean = self.SEVERITY_KOREAN.get(result.severity, "보통")
        resource_type_korean = self.RESOURCE_TYPE_KOREAN.get(
            result.resource_type, result.resource_type
        )

        # 제목 생성
        title = f"{severity_emoji} 설정 드리프트: {resource_type_korean} ({result.resource_id})"

        # 메시지 생성
        message = self._build_message(result, resource_type_korean, severity_korean)

        return DriftAlertSummary(
            title=title,
            message=message,
            severity_emoji=severity_emoji,
            resource_type=result.resource_type,
            resource_id=result.resource_id,
            timestamp=datetime.utcnow().isoformat(),
            drift_count=result.drift_count,
            critical_count=result.critical_count,
            high_count=result.high_count,
        )

    def generate_batch_summary(
        self,
        results: List[DriftResult],
        max_items: int = 5,
    ) -> DriftAlertSummary:
        """여러 탐지 결과에 대한 통합 한글 요약 생성.

        Args:
            results: 탐지 결과 목록
            max_items: 요약에 포함할 최대 항목 수

        Returns:
            통합 DriftAlertSummary 객체
        """
        # 드리프트가 있는 결과만 필터링
        drifts = [r for r in results if r.has_drift]

        if not drifts:
            return DriftAlertSummary(
                title="✅ 설정 정상",
                message="모든 리소스의 설정이 베이스라인과 일치합니다.",
                severity_emoji="✅",
                resource_type="all",
                resource_id="all",
                timestamp=datetime.utcnow().isoformat(),
                drift_count=0,
                critical_count=0,
                high_count=0,
            )

        # 심각도별 카운트
        severity_counts = {
            DriftSeverity.CRITICAL: 0,
            DriftSeverity.HIGH: 0,
            DriftSeverity.MEDIUM: 0,
            DriftSeverity.LOW: 0,
        }
        for r in drifts:
            severity_counts[r.severity] += 1

        # 가장 높은 심각도
        highest_severity = DriftSeverity.LOW
        for sev in [DriftSeverity.CRITICAL, DriftSeverity.HIGH, DriftSeverity.MEDIUM]:
            if severity_counts[sev] > 0:
                highest_severity = sev
                break

        severity_emoji = self.SEVERITY_EMOJI.get(highest_severity, "📊")

        # 리소스 타입별 그룹화
        by_type: Dict[str, List[DriftResult]] = {}
        for r in drifts:
            if r.resource_type not in by_type:
                by_type[r.resource_type] = []
            by_type[r.resource_type].append(r)

        # 제목
        title = f"{severity_emoji} 설정 드리프트 탐지: {len(drifts)}건"

        # 메시지 본문
        lines = [
            f"총 {len(drifts)}건의 설정 드리프트가 탐지되었습니다.",
            "",
            f"• 심각: {severity_counts[DriftSeverity.CRITICAL]}건",
            f"• 높음: {severity_counts[DriftSeverity.HIGH]}건",
            f"• 보통: {severity_counts[DriftSeverity.MEDIUM]}건",
            f"• 낮음: {severity_counts[DriftSeverity.LOW]}건",
            "",
            "리소스 타입별:",
        ]

        for resource_type, type_results in by_type.items():
            type_korean = self.RESOURCE_TYPE_KOREAN.get(resource_type, resource_type)
            lines.append(f"  • {type_korean}: {len(type_results)}건")

        lines.append("")
        lines.append("주요 항목:")

        # 상위 항목 상세 (심각도 순)
        sorted_drifts = sorted(
            drifts,
            key=lambda r: (
                [DriftSeverity.CRITICAL, DriftSeverity.HIGH, DriftSeverity.MEDIUM, DriftSeverity.LOW].index(r.severity),
                -r.drift_count,
            ),
        )

        for result in sorted_drifts[:max_items]:
            emoji = self.SEVERITY_EMOJI.get(result.severity, "📊")
            type_korean = self.RESOURCE_TYPE_KOREAN.get(
                result.resource_type, result.resource_type
            )
            lines.append(
                f"  {emoji} {type_korean}/{result.resource_id}: "
                f"{result.drift_count}건 드리프트"
            )

        if len(drifts) > max_items:
            lines.append(f"  ... 외 {len(drifts) - max_items}건")

        message = "\n".join(lines)

        total_critical = sum(r.critical_count for r in drifts)
        total_high = sum(r.high_count for r in drifts)

        return DriftAlertSummary(
            title=title,
            message=message,
            severity_emoji=severity_emoji,
            resource_type="multiple",
            resource_id=", ".join(by_type.keys()),
            timestamp=datetime.utcnow().isoformat(),
            drift_count=sum(r.drift_count for r in drifts),
            critical_count=total_critical,
            high_count=total_high,
        )

    def _build_message(
        self,
        result: DriftResult,
        resource_type_korean: str,
        severity_korean: str,
    ) -> str:
        """상세 메시지 구성."""
        lines = []

        # 기본 정보
        lines.append(
            f"{resource_type_korean} '{result.resource_id}'에서 "
            f"{result.drift_count}건의 설정 드리프트가 탐지되었습니다."
        )
        lines.append("")

        # 주요 변경 사항
        if result.drift_fields:
            lines.append("📋 주요 변경 사항:")
            for field in result.drift_fields[:5]:
                emoji = self.SEVERITY_EMOJI.get(field.severity, "📊")
                lines.append(f"  {emoji} {field.field_name}")
                if field.description:
                    lines.append(f"     {field.description}")

            if len(result.drift_fields) > 5:
                lines.append(f"  ... 외 {len(result.drift_fields) - 5}건")

        lines.append("")

        # 조언
        advice = self._get_advice(result.severity)
        lines.append(advice)

        lines.append("")

        # 메타 정보
        lines.append(
            f"[리소스: {result.resource_type}/{result.resource_id} | "
            f"베이스라인 v{result.baseline_version} | 심각도: {severity_korean}]"
        )

        return "\n".join(lines)

    def _get_advice(self, severity: DriftSeverity) -> str:
        """심각도별 조언 반환."""
        advice_map = {
            DriftSeverity.CRITICAL: (
                "⚠️ 즉시 확인이 필요합니다. "
                "보안 또는 데이터 무결성에 영향을 줄 수 있는 변경입니다."
            ),
            DriftSeverity.HIGH: (
                "📢 빠른 확인을 권장합니다. "
                "런타임 또는 버전 관련 변경이 감지되었습니다."
            ),
            DriftSeverity.MEDIUM: (
                "📌 모니터링이 필요합니다. "
                "용량 또는 스케일 관련 변경이 감지되었습니다."
            ),
            DriftSeverity.LOW: (
                "ℹ️ 참고용 알림입니다. "
                "메타데이터 또는 설명 관련 변경입니다."
            ),
        }
        return advice_map.get(severity, "설정 변경이 감지되었습니다.")
