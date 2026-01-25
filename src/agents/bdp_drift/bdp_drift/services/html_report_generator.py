"""
HTML Report Generator for Drift Detection.

드리프트 탐지 결과를 HTML 리포트로 생성.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.bdp_common.reports.base import HTMLReportBase
from src.agents.bdp_common.reports.styles import ReportStyles, SEVERITY_COLORS
from src.agents.bdp_drift.bdp_drift.services.models import DriftResult, DriftSeverity

logger = logging.getLogger(__name__)


class DriftHTMLReportGenerator(HTMLReportBase):
    """
    드리프트 탐지 HTML 리포트 생성기.

    리소스 타입별 그룹화, 심각도별 통계,
    드리프트 상세 (baseline vs current diff) 표시.
    """

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
        """리포트 생성기 초기화."""
        super().__init__(
            title="BDP Drift Detection Report",
            styles=ReportStyles(),
        )

    def generate_content(self, data: List[DriftResult]) -> str:
        """리포트 콘텐츠 생성.

        Args:
            data: DriftResult 목록

        Returns:
            HTML 콘텐츠
        """
        # 드리프트가 있는 결과만 필터링
        drifts = [r for r in data if r.has_drift]

        sections = []

        # 1. 요약 대시보드
        sections.append(self._generate_summary_dashboard(data, drifts))

        # 2. 리소스 타입별 그룹
        by_type = self._group_by_type(drifts)
        for resource_type, results in by_type.items():
            sections.append(self._generate_type_section(resource_type, results))

        # 3. 상세 드리프트 목록
        if drifts:
            sections.append(self._generate_detail_section(drifts))

        return "\n".join(sections)

    def _generate_summary_dashboard(
        self,
        all_results: List[DriftResult],
        drifts: List[DriftResult],
    ) -> str:
        """요약 대시보드 생성."""
        # 심각도별 카운트
        severity_counts = {
            DriftSeverity.CRITICAL: 0,
            DriftSeverity.HIGH: 0,
            DriftSeverity.MEDIUM: 0,
            DriftSeverity.LOW: 0,
        }
        for r in drifts:
            severity_counts[r.severity] += 1

        # 통계 카드
        stats = [
            {
                "label": "총 검사",
                "value": str(len(all_results)),
                "color": self.styles.info_color,
            },
            {
                "label": "드리프트 발견",
                "value": str(len(drifts)),
                "color": self.styles.danger_color if drifts else self.styles.success_color,
            },
            {
                "label": "심각",
                "value": str(severity_counts[DriftSeverity.CRITICAL]),
                "color": SEVERITY_COLORS["critical"]["border"],
            },
            {
                "label": "높음",
                "value": str(severity_counts[DriftSeverity.HIGH]),
                "color": SEVERITY_COLORS["high"]["border"],
            },
        ]

        stat_cards = self.render_stat_cards(stats, columns=4)

        # 상태 메시지
        if not drifts:
            status_alert = self.render_alert(
                "✅ 모든 리소스의 설정이 베이스라인과 일치합니다.",
                "success",
            )
        elif severity_counts[DriftSeverity.CRITICAL] > 0:
            status_alert = self.render_alert(
                f"🚨 {severity_counts[DriftSeverity.CRITICAL]}건의 심각한 드리프트가 발견되었습니다. 즉시 확인이 필요합니다.",
                "danger",
            )
        elif severity_counts[DriftSeverity.HIGH] > 0:
            status_alert = self.render_alert(
                f"⚠️ {severity_counts[DriftSeverity.HIGH]}건의 높은 심각도 드리프트가 발견되었습니다.",
                "warning",
            )
        else:
            status_alert = self.render_alert(
                f"📊 {len(drifts)}건의 드리프트가 발견되었습니다.",
                "info",
            )

        return self.render_card(
            "📊 탐지 요약",
            f"{status_alert}{stat_cards}",
        )

    def _group_by_type(
        self,
        results: List[DriftResult],
    ) -> Dict[str, List[DriftResult]]:
        """리소스 타입별 그룹화."""
        by_type: Dict[str, List[DriftResult]] = {}
        for r in results:
            if r.resource_type not in by_type:
                by_type[r.resource_type] = []
            by_type[r.resource_type].append(r)
        return by_type

    def _generate_type_section(
        self,
        resource_type: str,
        results: List[DriftResult],
    ) -> str:
        """리소스 타입별 섹션 생성."""
        type_korean = self.RESOURCE_TYPE_KOREAN.get(resource_type, resource_type)

        # 테이블 행 생성
        rows = []
        for r in sorted(results, key=lambda x: (
            [DriftSeverity.CRITICAL, DriftSeverity.HIGH, DriftSeverity.MEDIUM, DriftSeverity.LOW].index(x.severity),
            x.resource_id,
        )):
            severity_badge = self.render_severity_badge(r.severity.value)
            rows.append([
                r.resource_id,
                severity_badge,
                str(r.drift_count),
                ", ".join(f.field_name for f in r.drift_fields[:3]) + (
                    "..." if len(r.drift_fields) > 3 else ""
                ),
            ])

        table = self.render_table(
            headers=["리소스 ID", "심각도", "드리프트 수", "변경된 필드"],
            rows=rows,
            highlight_column=0,
        )

        header_extra = f'<span class="badge" style="margin-left: 8px;">{len(results)}건</span>'

        return self.render_card(
            f"📦 {type_korean}",
            table,
            header_extra=header_extra,
        )

    def _generate_detail_section(
        self,
        results: List[DriftResult],
    ) -> str:
        """상세 드리프트 섹션 생성."""
        details = []

        for r in sorted(results, key=lambda x: (
            [DriftSeverity.CRITICAL, DriftSeverity.HIGH, DriftSeverity.MEDIUM, DriftSeverity.LOW].index(x.severity),
            x.resource_type,
            x.resource_id,
        )):
            type_korean = self.RESOURCE_TYPE_KOREAN.get(r.resource_type, r.resource_type)
            severity_badge = self.render_severity_badge(r.severity.value)

            # 드리프트 필드 상세
            field_html = []
            for f in r.drift_fields:
                field_severity_badge = self.render_severity_badge(f.severity.value)
                diff_html = self.render_diff(
                    f.baseline_value,
                    f.current_value,
                    f.field_name,
                )
                field_html.append(f"""
                <div style="margin-bottom: 12px; padding: 8px; background: #f9fafb; border-radius: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong>{f.field_name}</strong>
                        {field_severity_badge}
                    </div>
                    {diff_html}
                    {f'<div style="font-size: 12px; color: #6b7280; margin-top: 4px;">{f.description}</div>' if f.description else ''}
                </div>
                """)

            details.append(f"""
            <div class="card" style="margin-bottom: 16px;">
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                    <span>
                        <strong>{type_korean}</strong> / {r.resource_id}
                    </span>
                    {severity_badge}
                </div>
                <div style="padding: 16px;">
                    <div style="margin-bottom: 8px; font-size: 14px; color: #6b7280;">
                        베이스라인 버전: v{r.baseline_version} |
                        탐지 시간: {r.detection_timestamp.strftime('%Y-%m-%d %H:%M:%S') if r.detection_timestamp else 'N/A'}
                    </div>
                    {''.join(field_html)}
                </div>
            </div>
            """)

        return f"""
        <div class="card">
            <div class="card-header">
                <span class="card-title">🔍 드리프트 상세</span>
            </div>
            {''.join(details)}
        </div>
        """


def generate_drift_report(
    results: List[DriftResult],
    output_path: Optional[str] = None,
) -> str:
    """드리프트 리포트 생성 편의 함수.

    Args:
        results: DriftResult 목록
        output_path: 출력 파일 경로 (없으면 HTML 문자열 반환)

    Returns:
        HTML 문자열 또는 파일 경로
    """
    generator = DriftHTMLReportGenerator()
    return generator.generate_report(results, output_path)
