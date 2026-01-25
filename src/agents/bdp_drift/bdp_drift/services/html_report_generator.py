"""
HTML Report Generator for Drift Detection.

드리프트 탐지 결과를 HTML 리포트로 생성.
- GNB (네비게이션 바): 리소스 타입별 클릭 이동
- 리소스 이모지 매핑
- 통합 드리프트 카드 (자체 완결형)
- 시계열 스타일 변경 시각화
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.bdp_common.reports.base import HTMLReportBase
from src.agents.bdp_common.reports.styles import (
    ReportStyles,
    SEVERITY_COLORS,
    MD3_COLORS,
    MATERIAL_ICONS,
)
from src.agents.bdp_drift.bdp_drift.services.chart_generator import DriftChartGenerator
from src.agents.bdp_drift.bdp_drift.services.models import DriftCategory, DriftResult, DriftSeverity

logger = logging.getLogger(__name__)


class DriftHTMLReportGenerator(HTMLReportBase):
    """
    드리프트 탐지 HTML 리포트 생성기.

    리소스 타입별 그룹화, 심각도별 통계,
    통합 드리프트 카드 (baseline vs current diff) 표시.
    GNB (Sticky Navigation)로 빠른 섹션 이동 지원.
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

    # Material Symbol 아이콘 매핑 (Resource Type)
    RESOURCE_ICON = {
        "glue": "folder_data",
        "athena": "query_stats",
        "emr": "bolt",
        "sagemaker": "smart_toy",
        "s3": "inventory_2",
        "mwaa": "air",
        "msk": "stream",
        "lambda": "function",
    }

    def __init__(self):
        """리포트 생성기 초기화."""
        super().__init__(
            title="BDP Drift Detection Report",
            styles=ReportStyles(),
        )
        self._chart_generator = DriftChartGenerator()

    def _get_additional_css(self) -> str:
        """추가 CSS 스타일 반환 (MD3 기반)."""
        return f"""
        /* =========================================================
           Integrated Drift Card - Self-contained card design (MD3)
           ========================================================= */
        .drift-card {{
            margin-bottom: 20px;
            border-radius: 12px;
            border: 1px solid {MD3_COLORS['outline_variant']};
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            transition: box-shadow 0.2s ease;
        }}

        .drift-card:hover {{
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        }}

        .drift-card.critical {{
            border-left: 4px solid {MD3_COLORS['error']};
        }}

        .drift-card.high {{
            border-left: 4px solid {MD3_COLORS['warning']};
        }}

        .drift-card.medium {{
            border-left: 4px solid {MD3_COLORS['primary']};
        }}

        .drift-card.low {{
            border-left: 4px solid {MD3_COLORS['outline']};
        }}

        /* Card Header */
        .drift-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            padding: 16px 20px;
            background: {MD3_COLORS['surface_variant']};
            border-bottom: 1px solid {MD3_COLORS['outline_variant']};
        }}

        .drift-card-header-left {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .drift-card-title {{
            font-size: 15px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface']};
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .drift-card-title .resource-icon {{
            color: {MD3_COLORS['primary']};
        }}

        .drift-card-meta {{
            font-size: 12px;
            color: {MD3_COLORS['on_surface_variant']};
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}

        .drift-card-meta-item {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}

        .drift-card-header-right {{
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 4px;
        }}

        /* Field Change Box - The main change visualization */
        .field-change-box {{
            margin: 16px 20px;
            padding: 16px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 10px;
            border: 1px solid {MD3_COLORS['outline_variant']};
        }}

        .field-change-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 10px;
            border-bottom: 1px dashed {MD3_COLORS['outline_variant']};
        }}

        .field-change-name {{
            font-size: 14px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface']};
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .field-change-description {{
            font-size: 13px;
            color: {MD3_COLORS['on_surface_variant']};
            margin-bottom: 16px;
            padding: 10px 12px;
            background: {MD3_COLORS['surface']};
            border-radius: 6px;
            border-left: 3px solid {MD3_COLORS['primary']};
        }}

        /* =========================================================
           Timeline Visualization - Past → Present flow (MD3)
           ========================================================= */
        .change-timeline {{
            display: flex;
            align-items: stretch;
            background: {MD3_COLORS['surface_variant']};
            padding: 16px;
            border-radius: 8px;
            gap: 0;
            min-height: 80px;
        }}

        .timeline-point {{
            flex: 1;
            padding: 12px 16px;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-width: 0; /* Allow text truncation */
        }}

        .timeline-point.baseline {{
            background: {MD3_COLORS['primary_container']};
            border: 2px solid {MD3_COLORS['primary']};
            margin-right: -8px;
            z-index: 1;
        }}

        .timeline-point.current {{
            background: {MD3_COLORS['error_container']};
            border: 2px solid {MD3_COLORS['error']};
            margin-left: -8px;
            z-index: 1;
        }}

        .timeline-point.current.high {{
            background: {MD3_COLORS['warning_container']};
            border-color: {MD3_COLORS['warning']};
        }}

        .timeline-point.current.medium {{
            background: {MD3_COLORS['primary_container']};
            border-color: {MD3_COLORS['primary']};
        }}

        .timeline-point.current.low {{
            background: {MD3_COLORS['success_container']};
            border-color: {MD3_COLORS['success']};
        }}

        .timeline-point-label {{
            font-size: 10px;
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 4px;
            letter-spacing: 0.5px;
        }}

        .timeline-point.baseline .timeline-point-label {{
            color: {MD3_COLORS['on_primary_container']};
        }}

        .timeline-point.current .timeline-point-label {{
            color: {MD3_COLORS['on_error_container']};
        }}

        .timeline-point.current.high .timeline-point-label {{
            color: {MD3_COLORS['on_warning_container']};
        }}

        .timeline-point.current.medium .timeline-point-label {{
            color: {MD3_COLORS['on_primary_container']};
        }}

        .timeline-point.current.low .timeline-point-label {{
            color: {MD3_COLORS['on_success_container']};
        }}

        .timeline-point-value {{
            font-size: 14px;
            font-weight: 500;
            word-break: break-word;
            overflow-wrap: break-word;
        }}

        .timeline-point.baseline .timeline-point-value {{
            color: {MD3_COLORS['on_primary_container']};
        }}

        .timeline-point.current .timeline-point-value {{
            color: {MD3_COLORS['on_error_container']};
        }}

        .timeline-point.current.high .timeline-point-value {{
            color: {MD3_COLORS['on_warning_container']};
        }}

        .timeline-point.current.medium .timeline-point-value {{
            color: {MD3_COLORS['on_primary_container']};
        }}

        .timeline-point.current.low .timeline-point-value {{
            color: {MD3_COLORS['on_success_container']};
        }}

        .timeline-arrow {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 0 16px;
            z-index: 2;
        }}

        .timeline-arrow-line {{
            width: 60px;
            height: 3px;
            background: linear-gradient(90deg, {MD3_COLORS['primary']}, {MD3_COLORS['error']});
            border-radius: 2px;
            position: relative;
        }}

        .timeline-arrow-line::after {{
            content: '';
            position: absolute;
            right: -6px;
            top: -4px;
            border: 6px solid transparent;
            border-left: 8px solid {MD3_COLORS['error']};
        }}

        .timeline-arrow-text {{
            font-size: 10px;
            color: {MD3_COLORS['on_surface_variant']};
            margin-top: 4px;
            font-weight: 500;
        }}

        /* =========================================================
           Numeric Trend - Mini chart for numbers (MD3)
           ========================================================= */
        .numeric-trend {{
            padding: 16px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 8px;
        }}

        .trend-chart {{
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            height: 80px;
            margin-bottom: 12px;
            padding: 0 20px;
        }}

        .trend-bar-group {{
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 40%;
        }}

        .trend-bar {{
            width: 60px;
            border-radius: 4px 4px 0 0;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding-top: 8px;
            font-size: 12px;
            font-weight: 600;
            color: white;
            min-height: 20px;
            transition: height 0.3s ease;
        }}

        .trend-bar.baseline {{
            background: {MD3_COLORS['primary']};
        }}

        .trend-bar.current-up {{
            background: {MD3_COLORS['error']};
        }}

        .trend-bar.current-down {{
            background: {MD3_COLORS['success']};
        }}

        .trend-bar-label {{
            margin-top: 8px;
            font-size: 11px;
            color: {MD3_COLORS['on_surface_variant']};
            font-weight: 500;
        }}

        .trend-connector {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            flex: 1;
        }}

        .trend-connector-line {{
            width: 100%;
            height: 2px;
            background: linear-gradient(90deg, {MD3_COLORS['primary']}, {MD3_COLORS['outline']} 50%, {MD3_COLORS['error']});
            position: relative;
        }}

        .trend-change-badge {{
            margin-top: 8px;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }}

        .trend-change-badge.up {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['error']};
        }}

        .trend-change-badge.down {{
            background: {MD3_COLORS['success_container']};
            color: {MD3_COLORS['success']};
        }}

        .trend-values {{
            display: flex;
            justify-content: space-between;
            padding: 0 20px;
        }}

        .trend-value {{
            text-align: center;
        }}

        .trend-value-number {{
            font-size: 18px;
            font-weight: 700;
        }}

        .trend-value-number.baseline {{
            color: {MD3_COLORS['primary']};
        }}

        .trend-value-number.current-up {{
            color: {MD3_COLORS['error']};
        }}

        .trend-value-number.current-down {{
            color: {MD3_COLORS['success']};
        }}

        .trend-value-label {{
            font-size: 11px;
            color: {MD3_COLORS['on_surface_variant']};
            margin-top: 2px;
        }}

        /* =========================================================
           State Transition - Boolean/Enum toggle (MD3)
           ========================================================= */
        .state-transition {{
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 8px;
            gap: 24px;
        }}

        .state-box {{
            padding: 16px 24px;
            border-radius: 10px;
            text-align: center;
            min-width: 120px;
        }}

        .state-box.baseline {{
            background: {MD3_COLORS['primary_container']};
            border: 2px solid {MD3_COLORS['primary']};
        }}

        .state-box.current {{
            background: {MD3_COLORS['error_container']};
            border: 2px solid {MD3_COLORS['error']};
        }}

        .state-icon {{
            font-size: 28px;
            margin-bottom: 4px;
        }}

        .state-label {{
            font-size: 10px;
            text-transform: uppercase;
            color: {MD3_COLORS['on_surface_variant']};
            font-weight: 600;
            margin-bottom: 4px;
        }}

        .state-value {{
            font-size: 14px;
            font-weight: 600;
        }}

        .state-box.baseline .state-value {{
            color: {MD3_COLORS['on_primary_container']};
        }}

        .state-box.current .state-value {{
            color: {MD3_COLORS['on_error_container']};
        }}

        .state-arrow {{
            display: flex;
            flex-direction: column;
            align-items: center;
            color: {MD3_COLORS['outline']};
        }}

        .state-arrow-icon {{
            font-size: 32px;
            font-weight: 300;
        }}

        .state-arrow-label {{
            font-size: 10px;
            margin-top: -4px;
        }}

        /* =========================================================
           Object Diff - Side-by-side comparison (MD3)
           ========================================================= */
        .object-diff {{
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid {MD3_COLORS['outline_variant']};
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
            font-size: 12px;
        }}

        .object-diff-header {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            background: {MD3_COLORS['surface_variant']};
            border-bottom: 1px solid {MD3_COLORS['outline_variant']};
        }}

        .object-diff-header-cell {{
            padding: 10px 14px;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .object-diff-header-cell.baseline {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
            border-right: 1px solid {MD3_COLORS['outline_variant']};
        }}

        .object-diff-header-cell.current {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['on_error_container']};
        }}

        .object-diff-body {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            max-height: 300px;
            overflow-y: auto;
        }}

        .object-diff-cell {{
            padding: 14px;
            white-space: pre-wrap;
            word-break: break-all;
            line-height: 1.6;
        }}

        .object-diff-cell.baseline {{
            background: {MD3_COLORS['primary_container']};
            border-right: 1px solid {MD3_COLORS['outline_variant']};
            color: {MD3_COLORS['on_primary_container']};
        }}

        .object-diff-cell.current {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['on_error_container']};
        }}

        /* =========================================================
           Impact & Recommendation boxes (MD3)
           ========================================================= */
        .info-boxes {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-top: 16px;
        }}

        @media (max-width: 768px) {{
            .info-boxes {{
                grid-template-columns: 1fr;
            }}
        }}

        .impact-box {{
            background: {MD3_COLORS['warning_container']};
            border-left: 4px solid {MD3_COLORS['warning']};
            padding: 12px 14px;
            border-radius: 0 8px 8px 0;
            font-size: 13px;
        }}

        .impact-box-title {{
            font-weight: 600;
            color: {MD3_COLORS['on_warning_container']};
            margin-bottom: 4px;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .impact-box-content {{
            color: {MD3_COLORS['on_warning_container']};
        }}

        .recommendation-box {{
            background: {MD3_COLORS['success_container']};
            border-left: 4px solid {MD3_COLORS['success']};
            padding: 12px 14px;
            border-radius: 0 8px 8px 0;
            font-size: 13px;
        }}

        .recommendation-box-title {{
            font-weight: 600;
            color: {MD3_COLORS['on_success_container']};
            margin-bottom: 4px;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .recommendation-box-content {{
            color: {MD3_COLORS['on_success_container']};
        }}

        /* =========================================================
           GNB - Sticky Navigation (MD3)
           ========================================================= */
        .type-nav {{
            position: sticky;
            top: 10px;
            z-index: 100;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            padding: 15px;
            background: {MD3_COLORS['surface']};
            border-radius: 12px;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
            margin-bottom: 20px;
            align-items: center;
        }}

        .type-nav-label {{
            font-weight: 600;
            color: {MD3_COLORS['on_surface']};
            padding: 8px 0;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .type-nav-link {{
            padding: 8px 16px;
            border-radius: 20px;
            text-decoration: none;
            font-weight: 500;
            font-size: 13px;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}

        .type-nav-link:hover {{
            transform: translateY(-2px);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
        }}

        .type-nav-link.critical {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['on_error_container']};
            border: 1px solid {MD3_COLORS['error']};
        }}

        .type-nav-link.high {{
            background: {MD3_COLORS['warning_container']};
            color: {MD3_COLORS['on_warning_container']};
            border: 1px solid {MD3_COLORS['warning']};
        }}

        .type-nav-link.medium {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
            border: 1px solid {MD3_COLORS['primary']};
        }}

        .type-nav-link.low {{
            background: {MD3_COLORS['success_container']};
            color: {MD3_COLORS['on_success_container']};
            border: 1px solid {MD3_COLORS['success']};
        }}

        .type-nav-link.none {{
            background: {MD3_COLORS['surface_variant']};
            color: {MD3_COLORS['on_surface_variant']};
            border: 1px solid {MD3_COLORS['outline']};
        }}

        /* Section anchor offset for sticky nav */
        .resource-section {{
            scroll-margin-top: 80px;
            margin-bottom: 32px;
        }}

        .resource-section-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 2px solid {MD3_COLORS['outline_variant']};
        }}

        .resource-section-title {{
            font-size: 18px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface']};
        }}

        .resource-section-count {{
            background: {MD3_COLORS['surface_variant']};
            color: {MD3_COLORS['on_surface_variant']};
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }}

        /* Smooth scroll behavior */
        html {{
            scroll-behavior: smooth;
        }}

        /* Severity badge styling (MD3) */
        .severity-badge {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .severity-badge.critical {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['on_error_container']};
        }}

        .severity-badge.high {{
            background: {MD3_COLORS['warning_container']};
            color: {MD3_COLORS['on_warning_container']};
        }}

        .severity-badge.medium {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
        }}

        .severity-badge.low {{
            background: {MD3_COLORS['success_container']};
            color: {MD3_COLORS['on_success_container']};
        }}

        /* =========================================================
           Temporal Timeline - Line Graph Style (MD3)
           ========================================================= */
        .temporal-timeline {{
            padding: 20px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 10px;
            border: 1px solid {MD3_COLORS['outline_variant']};
        }}

        .temporal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px dashed {MD3_COLORS['outline']};
        }}

        .temporal-header-title {{
            font-size: 12px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface_variant']};
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .temporal-duration-badge {{
            padding: 4px 10px;
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }}

        /* Line Graph Container */
        .timeline-graph {{
            position: relative;
            height: 140px;
            margin: 16px 0 8px 0;
            padding: 0 20px;
        }}

        /* Horizontal time axis line */
        .timeline-axis-line {{
            position: absolute;
            bottom: 30px;
            left: 20px;
            right: 20px;
            height: 2px;
            background: {MD3_COLORS['outline']};
        }}

        /* Data point wrapper */
        .timeline-data-point {{
            position: absolute;
            display: flex;
            flex-direction: column;
            align-items: center;
            z-index: 10;
        }}

        .timeline-data-point.baseline {{
            left: 10%;
        }}

        .timeline-data-point.current {{
            right: 10%;
        }}

        /* Value label above point */
        .timeline-value-label {{
            font-size: 14px;
            font-weight: 700;
            padding: 6px 12px;
            border-radius: 8px;
            white-space: nowrap;
            margin-bottom: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }}

        .timeline-value-label.baseline {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
            border: 2px solid {MD3_COLORS['primary']};
        }}

        .timeline-value-label.current {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['on_error_container']};
            border: 2px solid {MD3_COLORS['error']};
        }}

        .timeline-value-label.current.high {{
            background: {MD3_COLORS['warning_container']};
            color: {MD3_COLORS['on_warning_container']};
            border-color: {MD3_COLORS['warning']};
        }}

        .timeline-value-label.current.medium {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
            border-color: {MD3_COLORS['primary']};
        }}

        .timeline-value-label.current.low {{
            background: {MD3_COLORS['success_container']};
            color: {MD3_COLORS['on_success_container']};
            border-color: {MD3_COLORS['success']};
        }}

        /* Point dot */
        .timeline-dot {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
            border: 3px solid;
            background: {MD3_COLORS['surface']};
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
        }}

        .timeline-dot.baseline {{
            border-color: {MD3_COLORS['primary']};
        }}

        .timeline-dot.current {{
            border-color: {MD3_COLORS['error']};
        }}

        .timeline-dot.current.high {{
            border-color: {MD3_COLORS['warning']};
        }}

        .timeline-dot.current.medium {{
            border-color: {MD3_COLORS['primary']};
        }}

        .timeline-dot.current.low {{
            border-color: {MD3_COLORS['success']};
        }}

        /* Connector line between points */
        .timeline-connector-svg {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 5;
        }}

        .timeline-connector-path {{
            fill: none;
            stroke-width: 3;
            stroke-linecap: round;
        }}

        .timeline-connector-path.increase {{
            stroke: url(#gradient-increase);
        }}

        .timeline-connector-path.decrease {{
            stroke: url(#gradient-decrease);
        }}

        .timeline-connector-path.neutral {{
            stroke: url(#gradient-neutral);
        }}

        /* Time labels below axis */
        .timeline-time-labels {{
            display: flex;
            justify-content: space-between;
            padding: 8px 20px 0 20px;
        }}

        .timeline-time-label {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
        }}

        .timeline-time-label.start {{
            align-items: flex-start;
        }}

        .timeline-time-label.end {{
            align-items: flex-end;
        }}

        .timeline-time-type {{
            font-size: 10px;
            color: {MD3_COLORS['on_surface_variant']};
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .timeline-time-value {{
            font-size: 12px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface']};
        }}

        /* Change indicator */
        .timeline-change-indicator {{
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            top: 50%;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            z-index: 15;
        }}

        .timeline-change-indicator.increase {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['error']};
        }}

        .timeline-change-indicator.decrease {{
            background: {MD3_COLORS['success_container']};
            color: {MD3_COLORS['success']};
        }}

        .timeline-change-indicator.neutral {{
            background: {MD3_COLORS['surface_variant']};
            color: {MD3_COLORS['on_surface_variant']};
        }}

        /* Duration footer */
        .temporal-footer {{
            display: flex;
            justify-content: center;
            margin-top: 8px;
            padding-top: 12px;
            border-top: 1px dashed {MD3_COLORS['outline_variant']};
        }}

        .temporal-footer-duration {{
            font-size: 12px;
            color: {MD3_COLORS['on_surface_variant']};
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .temporal-footer-duration .duration-highlight {{
            font-weight: 600;
            color: {MD3_COLORS['on_primary_container']};
        }}

        /* =========================================================
           QuickChart Container - bdp_cost 스타일 (MD3)
           ========================================================= */
        .drift-chart-container {{
            padding: 16px;
            text-align: center;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 8px;
            margin: 12px 0;
        }}

        .drift-chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        .drift-chart-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 10px;
            border-bottom: 1px dashed {MD3_COLORS['outline']};
        }}

        .drift-chart-title {{
            font-size: 12px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface_variant']};
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .drift-chart-badge {{
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }}

        .drift-chart-badge.increase {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['error']};
        }}

        .drift-chart-badge.decrease {{
            background: {MD3_COLORS['success_container']};
            color: {MD3_COLORS['success']};
        }}

        .drift-chart-badge.neutral {{
            background: {MD3_COLORS['surface_variant']};
            color: {MD3_COLORS['on_surface_variant']};
        }}

        .drift-chart-badge.duration {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
        }}

        .drift-chart-footer {{
            display: flex;
            justify-content: center;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px dashed {MD3_COLORS['outline_variant']};
        }}

        .drift-chart-footer-text {{
            font-size: 12px;
            color: {MD3_COLORS['on_surface_variant']};
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .drift-chart-values {{
            display: flex;
            justify-content: space-between;
            padding: 12px 20px;
            margin-top: 8px;
        }}

        .drift-chart-value {{
            text-align: center;
        }}

        .drift-chart-value-number {{
            font-size: 16px;
            font-weight: 700;
        }}

        .drift-chart-value-number.baseline {{
            color: {MD3_COLORS['primary']};
        }}

        .drift-chart-value-number.current {{
            color: {MD3_COLORS['error']};
        }}

        .drift-chart-value-number.current.decrease {{
            color: {MD3_COLORS['success']};
        }}

        .drift-chart-value-label {{
            font-size: 11px;
            color: {MD3_COLORS['on_surface_variant']};
            margin-top: 2px;
        }}

        /* =========================================================
           Discovered Field Styling - 발견 필드 (신규 추가/삭제) (MD3)
           ========================================================= */
        .field-change-box.discovered {{
            background: {MD3_COLORS['surface']};
            border: 1px dashed {MD3_COLORS['outline']};
            opacity: 0.9;
        }}

        .category-badge {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
            margin-left: 8px;
        }}

        .category-badge.monitored {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
        }}

        .category-badge.discovered {{
            background: {MD3_COLORS['surface_variant']};
            color: {MD3_COLORS['on_surface_variant']};
            border: 1px dashed {MD3_COLORS['outline']};
        }}

        .discovered-section {{
            margin: 16px 20px;
            padding-top: 16px;
            border-top: 2px dashed {MD3_COLORS['outline_variant']};
        }}

        .discovered-section-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            padding: 10px 14px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 8px;
            border: 1px dashed {MD3_COLORS['outline']};
        }}

        .discovered-section-header-title {{
            font-size: 13px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface_variant']};
        }}

        .discovered-section-header-count {{
            font-size: 11px;
            padding: 2px 8px;
            background: {MD3_COLORS['outline_variant']};
            color: {MD3_COLORS['on_surface_variant']};
            border-radius: 10px;
        }}

        /* Field count badges in card header */
        .field-count-badges {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }}

        .field-count-badge {{
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 10px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}

        .field-count-badge.monitored {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
        }}

        .field-count-badge.discovered {{
            background: {MD3_COLORS['surface_variant']};
            color: {MD3_COLORS['on_surface_variant']};
            border: 1px dashed {MD3_COLORS['outline']};
        }}
        """

    def _wrap_html(self, content: str) -> str:
        """HTML 래퍼 생성 (추가 CSS 포함)."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title}</title>
    <!-- Material Symbols Font (Google CDN) -->
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" />
    <style>
        {self.styles.get_base_css()}
        {self._get_icon_css()}
        {self._get_additional_css()}
    </style>
</head>
<body>
    <div class="header">
        <div class="container">
            <h1 class="header-title">{self.title}</h1>
            <p class="header-subtitle">Generated at {timestamp}</p>
        </div>
    </div>
    <div class="container">
        {content}
    </div>
</body>
</html>"""

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

        # 2. GNB (리소스 타입 네비게이션)
        by_type = self._group_by_type(drifts)
        if by_type:
            sections.append(self._build_resource_nav(by_type))

        # 3. 리소스 타입별 통합 카드 섹션 (NEW - 테이블+상세 통합)
        for resource_type, results in by_type.items():
            sections.append(self._generate_resource_section(resource_type, results))

        # 별도 상세 섹션 제거됨

        return "\n".join(sections)

    def _build_resource_nav(self, by_type: Dict[str, List[DriftResult]]) -> str:
        """리소스 타입 네비게이션 생성.

        Args:
            by_type: 리소스 타입별 DriftResult 그룹

        Returns:
            HTML 네비게이션 문자열
        """
        links = []
        for resource_type, results in by_type.items():
            type_korean = self.RESOURCE_TYPE_KOREAN.get(resource_type, resource_type)
            icon_name = self.RESOURCE_ICON.get(resource_type, "cloud")
            severity_class = self._get_max_severity_class(results)
            count = len(results)
            resource_icon = self._icon(icon_name, size="sm", inline=True)
            links.append(
                f'<a href="#section-{resource_type}" class="type-nav-link {severity_class}">'
                f'{resource_icon} {type_korean} ({count})'
                f'</a>'
            )

        nav_icon = self._icon("near_me", size="sm", color="primary", inline=True)
        return f"""
        <div class="type-nav">
            <span class="type-nav-label">{nav_icon} 바로가기:</span>
            {" ".join(links)}
        </div>
        """

    def _get_max_severity_class(self, results: List[DriftResult]) -> str:
        """결과 목록에서 최대 심각도 클래스 반환.

        Args:
            results: DriftResult 목록

        Returns:
            CSS 클래스명 (critical, high, medium, low, none)
        """
        if not results:
            return "none"

        severity_order = [
            DriftSeverity.CRITICAL,
            DriftSeverity.HIGH,
            DriftSeverity.MEDIUM,
            DriftSeverity.LOW,
        ]

        max_severity = DriftSeverity.LOW
        for r in results:
            if severity_order.index(r.severity) < severity_order.index(max_severity):
                max_severity = r.severity

        return max_severity.value

    def _generate_summary_dashboard(
        self,
        all_results: List[DriftResult],
        drifts: List[DriftResult],
    ) -> str:
        """요약 대시보드 생성."""
        # 심각도별 카운트 (MONITORED 필드만 집계)
        severity_counts = {
            DriftSeverity.CRITICAL: 0,
            DriftSeverity.HIGH: 0,
            DriftSeverity.MEDIUM: 0,
            DriftSeverity.LOW: 0,
        }
        for r in drifts:
            # MONITORED 필드의 심각도만 집계
            for f in r.monitored_fields:
                severity_counts[f.severity] += 1

        # 모니터링/발견 필드 총 카운트
        total_monitored = sum(r.monitored_count for r in drifts)
        total_discovered = sum(r.discovered_count for r in drifts)

        # 통계 카드
        stats = [
            {
                "label": "총 검사",
                "value": str(len(all_results)),
                "color": self.styles.info_color,
            },
            {
                "label": "모니터링 변경",
                "value": str(total_monitored),
                "color": self.styles.danger_color if total_monitored else self.styles.success_color,
            },
            {
                "label": "발견 (정보용)",
                "value": str(total_discovered),
                "color": "#6b7280",  # Gray for informational
            },
            {
                "label": "심각 (CRITICAL)",
                "value": str(severity_counts[DriftSeverity.CRITICAL]),
                "color": SEVERITY_COLORS["critical"]["border"],
            },
        ]

        stat_cards = self.render_stat_cards(stats, columns=4)

        # 상태 메시지
        check_icon = self._icon("check_circle", size="sm", filled=True, color="success", inline=True)
        error_icon = self._icon("error", size="sm", filled=True, color="error", inline=True)
        warning_icon = self._icon("warning", size="sm", filled=True, color="warning", inline=True)
        info_icon = self._icon("info", size="sm", color="primary", inline=True)
        search_icon = self._icon("search", size="sm", color="muted", inline=True)

        if not drifts:
            status_alert = self.render_alert(
                f"{check_icon} 모든 리소스의 설정이 베이스라인과 일치합니다.",
                "success",
            )
        elif severity_counts[DriftSeverity.CRITICAL] > 0:
            status_alert = self.render_alert(
                f"{error_icon} {severity_counts[DriftSeverity.CRITICAL]}건의 심각한 모니터링 필드 드리프트가 발견되었습니다. 즉시 확인이 필요합니다.",
                "danger",
            )
        elif severity_counts[DriftSeverity.HIGH] > 0:
            status_alert = self.render_alert(
                f"{warning_icon} {severity_counts[DriftSeverity.HIGH]}건의 높은 심각도 모니터링 필드 드리프트가 발견되었습니다.",
                "warning",
            )
        elif total_monitored > 0:
            status_alert = self.render_alert(
                f"{info_icon} {total_monitored}건의 모니터링 필드 변경이 발견되었습니다.",
                "info",
            )
        elif total_discovered > 0:
            status_alert = self.render_alert(
                f"{search_icon} {total_discovered}건의 발견 필드가 있습니다 (정보용, 주요 모니터링 대상 아님).",
                "info",
            )
        else:
            status_alert = self.render_alert(
                f"{info_icon} {len(drifts)}건의 리소스에서 변경이 발견되었습니다.",
                "info",
            )

        dashboard_icon = self._icon("dashboard", size="sm", color="primary", inline=True)
        return self.render_card(
            f"{dashboard_icon} 탐지 요약",
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

    def _generate_resource_section(
        self,
        resource_type: str,
        results: List[DriftResult],
    ) -> str:
        """리소스 타입별 통합 섹션 생성.

        각 리소스 타입 섹션에 자체 완결형 드리프트 카드를 포함.

        Args:
            resource_type: 리소스 타입
            results: DriftResult 목록

        Returns:
            HTML 섹션 문자열
        """
        type_korean = self.RESOURCE_TYPE_KOREAN.get(resource_type, resource_type)
        icon_name = self.RESOURCE_ICON.get(resource_type, "cloud")
        resource_icon = self._icon(icon_name, size="lg", color="primary")

        # 심각도 순으로 정렬
        sorted_results = sorted(results, key=lambda x: (
            [DriftSeverity.CRITICAL, DriftSeverity.HIGH, DriftSeverity.MEDIUM, DriftSeverity.LOW].index(x.severity),
            x.resource_id,
        ))

        # 각 결과에 대한 통합 드리프트 카드 생성
        cards = []
        for r in sorted_results:
            cards.append(self._generate_drift_card(r))

        return f"""
        <div id="section-{resource_type}" class="resource-section">
            <div class="resource-section-header">
                {resource_icon}
                <span class="resource-section-title">{type_korean}</span>
                <span class="resource-section-count">{len(results)}건</span>
            </div>
            {''.join(cards)}
        </div>
        """

    def _generate_drift_card(self, result: DriftResult) -> str:
        """통합 드리프트 카드 생성.

        하나의 카드에 모든 정보를 자체 완결형으로 포함:
        - 리소스 정보 (헤더)
        - MONITORED 필드 변경 사항 (주요 관심 대상)
        - DISCOVERED 필드 변경 사항 (정보성, 별도 섹션)
        - 영향도 및 권장 조치

        Args:
            result: DriftResult 객체

        Returns:
            HTML 카드 문자열
        """
        type_korean = self.RESOURCE_TYPE_KOREAN.get(result.resource_type, result.resource_type)
        icon_name = self.RESOURCE_ICON.get(result.resource_type, "cloud")
        resource_icon = self._icon(icon_name, size="md", color="primary")
        severity_class = result.severity.value

        # 심각도별 아이콘
        severity_icons = {
            "critical": self._icon("error", size="sm", filled=True, inline=True),
            "high": self._icon("warning", size="sm", filled=True, inline=True),
            "medium": self._icon("info", size="sm", inline=True),
            "low": self._icon("check_circle", size="sm", inline=True),
        }
        severity_icon = severity_icons.get(severity_class, self._icon("info", size="sm", inline=True))

        # 메타 아이콘
        version_icon = self._icon("history", size="xs", color="muted", inline=True)
        account_icon = self._icon("business", size="xs", color="muted", inline=True)
        time_icon = self._icon("schedule", size="xs", color="muted", inline=True)

        # 메타 정보
        meta_items = []
        meta_items.append(f'<span class="drift-card-meta-item">{version_icon} v{result.baseline_version}</span>')
        if result.account_name or result.account_id:
            account = result.account_name or result.account_id
            meta_items.append(f'<span class="drift-card-meta-item">{account_icon} {account}</span>')
        if result.detection_timestamp:
            timestamp = result.detection_timestamp.strftime('%Y-%m-%d %H:%M:%S')
            meta_items.append(f'<span class="drift-card-meta-item">{time_icon} {timestamp}</span>')

        # 필드를 카테고리별로 분리
        monitored_fields = result.monitored_fields
        discovered_fields = result.discovered_fields

        # MONITORED 필드 박스 생성
        monitored_boxes = []
        for f in monitored_fields:
            monitored_boxes.append(self._generate_field_change_box(
                f,
                baseline_timestamp=result.baseline_timestamp,
                detection_timestamp=result.detection_timestamp,
            ))

        # DISCOVERED 필드 박스 생성 (별도 섹션)
        discovered_section = ""
        if discovered_fields:
            discovered_boxes = []
            for f in discovered_fields:
                discovered_boxes.append(self._generate_field_change_box(
                    f,
                    baseline_timestamp=result.baseline_timestamp,
                    detection_timestamp=result.detection_timestamp,
                ))
            search_icon = self._icon("search", size="md", color="muted")
            discovered_section = f"""
            <div class="discovered-section">
                <div class="discovered-section-header">
                    {search_icon}
                    <span class="discovered-section-header-title">발견된 변경 (정보용)</span>
                    <span class="discovered-section-header-count">{len(discovered_fields)}개</span>
                </div>
                {''.join(discovered_boxes)}
            </div>
            """

        # 필드 카운트 배지 생성
        monitoring_badge_icon = self._icon("monitoring", size="xs", inline=True)
        search_badge_icon = self._icon("search", size="xs", inline=True)

        field_count_badges = []
        if monitored_fields:
            field_count_badges.append(
                f'<span class="field-count-badge monitored">{monitoring_badge_icon} {len(monitored_fields)} 모니터링</span>'
            )
        if discovered_fields:
            field_count_badges.append(
                f'<span class="field-count-badge discovered">{search_badge_icon} {len(discovered_fields)} 발견</span>'
            )

        return f"""
        <div class="drift-card {severity_class}">
            <div class="drift-card-header">
                <div class="drift-card-header-left">
                    <div class="drift-card-title">
                        <span class="resource-icon">{resource_icon}</span>
                        {type_korean} / {result.resource_id}
                    </div>
                    <div class="drift-card-meta">
                        {' '.join(meta_items)}
                    </div>
                </div>
                <div class="drift-card-header-right">
                    <span class="severity-badge {severity_class}">
                        {severity_icon} {severity_class.upper()}
                    </span>
                    <div class="field-count-badges">
                        {' '.join(field_count_badges)}
                    </div>
                </div>
            </div>
            {''.join(monitored_boxes)}
            {discovered_section}
        </div>
        """

    def _generate_field_change_box(
        self,
        field,
        baseline_timestamp: Optional[datetime] = None,
        detection_timestamp: Optional[datetime] = None,
    ) -> str:
        """필드 변경 박스 생성.

        Args:
            field: DriftField 객체
            baseline_timestamp: 베이스라인 설정 시점
            detection_timestamp: 드리프트 탐지 시점

        Returns:
            HTML 필드 박스 문자열
        """
        severity_class = field.severity.value
        severity_badge = f'<span class="severity-badge {severity_class}">{severity_class.upper()}</span>'

        # 카테고리 배지 및 박스 클래스 결정
        category_class = field.category.value
        is_discovered = field.category == DriftCategory.DISCOVERED
        box_class = "field-change-box discovered" if is_discovered else "field-change-box"

        if is_discovered:
            cat_icon = self._icon("search", size="xs", inline=True)
            category_badge = f'<span class="category-badge {category_class}">{cat_icon} 발견</span>'
        else:
            cat_icon = self._icon("monitoring", size="xs", inline=True)
            category_badge = f'<span class="category-badge {category_class}">{cat_icon} 모니터링</span>'

        # 설명
        description_html = ""
        if field.description:
            description_html = f"""
            <div class="field-change-description">
                {field.description}
            </div>
            """

        # 시계열 시각화 선택
        change_visualization = self._render_change_timeline(
            field.field_name,
            field.baseline_value,
            field.current_value,
            field.severity,
            baseline_timestamp=baseline_timestamp,
            detection_timestamp=detection_timestamp,
        )

        # 영향도/권장조치 박스 (DISCOVERED 필드는 생략)
        info_boxes_html = ""
        if not is_discovered and (field.impact or field.recommendation):
            impact_html = ""
            recommendation_html = ""

            if field.impact:
                impact_icon = self._icon("priority_high", size="sm", color="warning", inline=True)
                impact_html = f"""
                <div class="impact-box">
                    <div class="impact-box-title">{impact_icon} 영향</div>
                    <div class="impact-box-content">{field.impact}</div>
                </div>
                """

            if field.recommendation:
                rec_icon = self._icon("lightbulb", size="sm", color="success", inline=True)
                recommendation_html = f"""
                <div class="recommendation-box">
                    <div class="recommendation-box-title">{rec_icon} 권장 조치</div>
                    <div class="recommendation-box-content">{field.recommendation}</div>
                </div>
                """

            info_boxes_html = f"""
            <div class="info-boxes">
                {impact_html}
                {recommendation_html}
            </div>
            """

        settings_icon = self._icon("settings", size="sm", color="muted", inline=True)
        return f"""
        <div class="{box_class}">
            <div class="field-change-header">
                <span class="field-change-name">
                    {settings_icon} {field.field_name}
                    {category_badge}
                </span>
                {severity_badge}
            </div>
            {description_html}
            {change_visualization}
            {info_boxes_html}
        </div>
        """

    def _render_change_timeline(
        self,
        field_name: str,
        baseline_value: Any,
        current_value: Any,
        severity: DriftSeverity,
        baseline_timestamp: Optional[datetime] = None,
        detection_timestamp: Optional[datetime] = None,
    ) -> str:
        """값 타입에 따른 시계열 시각화 선택.

        Args:
            field_name: 필드명
            baseline_value: 베이스라인 값
            current_value: 현재 값
            severity: 심각도
            baseline_timestamp: 베이스라인 설정 시점
            detection_timestamp: 드리프트 탐지 시점

        Returns:
            HTML 시각화 문자열
        """
        # 시간 정보가 있으면 temporal timeline 사용
        has_temporal_info = baseline_timestamp is not None and detection_timestamp is not None

        # 불린 값은 상태 전환으로 표시
        if isinstance(baseline_value, bool) or isinstance(current_value, bool):
            if has_temporal_info:
                return self._render_temporal_timeline(
                    baseline_value, current_value, baseline_timestamp, detection_timestamp, severity, field_name
                )
            return self._render_state_transition(baseline_value, current_value, severity)

        # 숫자 값 비교 (미니 트렌드 차트) - 의미있는 차이가 있을 때
        if isinstance(baseline_value, (int, float)) and isinstance(current_value, (int, float)):
            # 둘 다 0이 아닌 경우에만 트렌드 차트 사용
            if baseline_value != 0 or current_value != 0:
                if has_temporal_info:
                    return self._render_temporal_timeline(
                        baseline_value, current_value, baseline_timestamp, detection_timestamp, severity, field_name
                    )
                return self._render_numeric_trend(field_name, baseline_value, current_value)

        # None → 값 또는 값 → None (추가/삭제)
        if baseline_value is None or current_value is None:
            if has_temporal_info:
                return self._render_temporal_timeline(
                    baseline_value, current_value, baseline_timestamp, detection_timestamp, severity, field_name
                )
            return self._render_state_transition(baseline_value, current_value, severity)

        # 객체/배열 비교 (Side-by-Side diff) - 시간 정보가 있으면 헤더 추가
        if isinstance(baseline_value, (dict, list)) or isinstance(current_value, (dict, list)):
            if has_temporal_info:
                temporal_header = self._render_temporal_header(baseline_timestamp, detection_timestamp)
                return temporal_header + self._render_object_diff(baseline_value, current_value)
            return self._render_object_diff(baseline_value, current_value)

        # 기본: 타임라인 시각화 (문자열 등)
        if has_temporal_info:
            return self._render_temporal_timeline(
                baseline_value, current_value, baseline_timestamp, detection_timestamp, severity, field_name
            )
        return self._render_default_timeline(baseline_value, current_value, severity)

    def _render_temporal_timeline(
        self,
        baseline_value: Any,
        current_value: Any,
        baseline_timestamp: datetime,
        detection_timestamp: datetime,
        severity: DriftSeverity,
        field_name: str = "값",
    ) -> str:
        """시간 기반 라인 그래프 타임라인 렌더링 (QuickChart.io 기반).

        숫자 값의 경우 QuickChart.io API를 사용하여 라인 차트로 시각화.
        비숫자 값은 기존 SVG 기반 시각화로 폴백.

        Args:
            baseline_value: 베이스라인 값
            current_value: 현재 값
            baseline_timestamp: 베이스라인 설정 시점
            detection_timestamp: 드리프트 탐지 시점
            severity: 심각도
            field_name: 필드명 (차트 제목에 사용)

        Returns:
            HTML 타임라인 문자열
        """
        # 기간 계산
        duration = detection_timestamp - baseline_timestamp
        total_days = duration.days
        total_hours = duration.total_seconds() / 3600

        # 기간 텍스트 생성
        if total_days >= 1:
            duration_text = f"{total_days}일"
        elif total_hours >= 1:
            duration_text = f"{int(total_hours)}시간"
        else:
            minutes = int(duration.total_seconds() / 60)
            duration_text = f"{minutes}분" if minutes > 0 else "방금"

        # 날짜 포맷
        baseline_date = baseline_timestamp.strftime('%Y-%m-%d')
        detection_date = detection_timestamp.strftime('%Y-%m-%d')

        # 값 포맷팅
        baseline_display = self._format_value_for_display(baseline_value)
        current_display = self._format_value_for_display(current_value)

        # 숫자 값인 경우 QuickChart 사용 시도
        if (isinstance(baseline_value, (int, float)) and not isinstance(baseline_value, bool) and
            isinstance(current_value, (int, float)) and not isinstance(current_value, bool)):

            chart_url = self._chart_generator.generate_chart_url(
                baseline_value=baseline_value,
                current_value=current_value,
                baseline_date=baseline_date,
                current_date=detection_date,
                field_name=field_name,
            )

            if chart_url:
                # 증가/감소 판단
                if current_value > baseline_value:
                    change_direction = "increase"
                    change_pct = ((current_value - baseline_value) / baseline_value * 100) if baseline_value != 0 else 100
                    trend_icon = self._icon("trending_up", size="sm", inline=True)
                    change_text = f"{trend_icon} +{change_pct:.1f}%"
                    current_class = ""
                elif current_value < baseline_value:
                    change_direction = "decrease"
                    change_pct = ((baseline_value - current_value) / baseline_value * 100) if baseline_value != 0 else 100
                    trend_icon = self._icon("trending_down", size="sm", inline=True)
                    change_text = f"{trend_icon} -{change_pct:.1f}%"
                    current_class = "decrease"
                else:
                    change_direction = "neutral"
                    change_text = "변경 없음"
                    current_class = ""

                chart_icon = self._icon("show_chart", size="sm", inline=True)
                time_icon = self._icon("schedule", size="sm", inline=True)
                location_icon = self._icon("location_on", size="sm", color="primary", inline=True)
                return f"""
                <div class="drift-chart-container">
                    <div class="drift-chart-header">
                        <span class="drift-chart-title">
                            {chart_icon} {field_name} 변화 추이
                        </span>
                        <div style="display: flex; gap: 8px;">
                            <span class="drift-chart-badge {change_direction}">
                                {change_text}
                            </span>
                            <span class="drift-chart-badge duration">
                                {time_icon} {duration_text}
                            </span>
                        </div>
                    </div>

                    <img src="{chart_url}" alt="{field_name} drift chart" loading="lazy" />

                    <div class="drift-chart-values">
                        <div class="drift-chart-value">
                            <div class="drift-chart-value-number baseline">{baseline_display}</div>
                            <div class="drift-chart-value-label">Baseline ({baseline_date})</div>
                        </div>
                        <div class="drift-chart-value">
                            <div class="drift-chart-value-number current {current_class}">{current_display}</div>
                            <div class="drift-chart-value-label">Current ({detection_date})</div>
                        </div>
                    </div>

                    <div class="drift-chart-footer">
                        <span class="drift-chart-footer-text">
                            ━━━ <span style="font-weight: 600; color: {MD3_COLORS['on_primary_container']};">{duration_text}</span> 유지 후 변경 탐지 {location_icon}
                        </span>
                    </div>
                </div>
                """

        # 비숫자 값 또는 차트 생성 실패시 기존 SVG 기반 시각화
        return self._render_temporal_timeline_svg(
            baseline_value=baseline_value,
            current_value=current_value,
            baseline_date=baseline_date,
            detection_date=detection_date,
            baseline_display=baseline_display,
            current_display=current_display,
            duration_text=duration_text,
            severity=severity,
        )

    def _render_temporal_timeline_svg(
        self,
        baseline_value: Any,
        current_value: Any,
        baseline_date: str,
        detection_date: str,
        baseline_display: str,
        current_display: str,
        duration_text: str,
        severity: DriftSeverity,
    ) -> str:
        """SVG 기반 타임라인 렌더링 (비숫자 값용 폴백).

        Args:
            baseline_value: 베이스라인 값
            current_value: 현재 값
            baseline_date: 베이스라인 날짜 문자열
            detection_date: 탐지 날짜 문자열
            baseline_display: 베이스라인 표시 문자열
            current_display: 현재 값 표시 문자열
            duration_text: 기간 텍스트
            severity: 심각도

        Returns:
            HTML 타임라인 문자열
        """
        severity_class = severity.value

        # 값 변화 방향 결정
        change_direction = "neutral"
        change_text = "변경"
        baseline_y = 50
        current_y = 50

        # 불린 값 처리
        if isinstance(baseline_value, bool) and isinstance(current_value, bool):
            if baseline_value and not current_value:
                change_direction = "decrease"
                cancel_icon = self._icon("cancel", size="sm", filled=True, inline=True)
                change_text = f"{cancel_icon} 비활성화"
                baseline_y = 30
                current_y = 70
            elif not baseline_value and current_value:
                change_direction = "increase"
                check_icon = self._icon("check_circle", size="sm", filled=True, inline=True)
                change_text = f"{check_icon} 활성화"
                baseline_y = 70
                current_y = 30

        # SVG 좌표 계산
        svg_baseline_x = 15
        svg_current_x = 85

        timeline_icon = self._icon("timeline", size="sm", inline=True)
        time_icon = self._icon("schedule", size="sm", inline=True)
        location_icon = self._icon("location_on", size="sm", color="error", inline=True)
        return f"""
        <div class="temporal-timeline">
            <div class="temporal-header">
                <span class="temporal-header-title">
                    {timeline_icon} Timeline
                </span>
                <span class="temporal-duration-badge">
                    {time_icon} {duration_text}간 유지 후 변경
                </span>
            </div>

            <div class="timeline-graph">
                <!-- SVG Gradients and Connector Line -->
                <svg class="timeline-connector-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
                    <defs>
                        <linearGradient id="gradient-increase" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" style="stop-color:{MD3_COLORS['primary']}"/>
                            <stop offset="100%" style="stop-color:{MD3_COLORS['error']}"/>
                        </linearGradient>
                        <linearGradient id="gradient-decrease" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" style="stop-color:{MD3_COLORS['primary']}"/>
                            <stop offset="100%" style="stop-color:{MD3_COLORS['success']}"/>
                        </linearGradient>
                        <linearGradient id="gradient-neutral" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" style="stop-color:{MD3_COLORS['primary']}"/>
                            <stop offset="100%" style="stop-color:{MD3_COLORS['on_surface_variant']}"/>
                        </linearGradient>
                    </defs>
                    <!-- Connector line from baseline to current -->
                    <path class="timeline-connector-path {change_direction}"
                          d="M {svg_baseline_x} {baseline_y} L {svg_current_x} {current_y}"/>
                </svg>

                <!-- Change indicator in the middle -->
                <div class="timeline-change-indicator {change_direction}">
                    {change_text}
                </div>

                <!-- Baseline Point (left side) -->
                <div class="timeline-data-point baseline" style="bottom: {100 - baseline_y}%;">
                    <span class="timeline-value-label baseline">{baseline_display}</span>
                    <span class="timeline-dot baseline"></span>
                </div>

                <!-- Current Point (right side) -->
                <div class="timeline-data-point current" style="bottom: {100 - current_y}%;">
                    <span class="timeline-value-label current {severity_class}">{location_icon} {current_display}</span>
                    <span class="timeline-dot current {severity_class}"></span>
                </div>

                <!-- Time axis line -->
                <div class="timeline-axis-line"></div>
            </div>

            <!-- Time labels -->
            <div class="timeline-time-labels">
                <div class="timeline-time-label start">
                    <span class="timeline-time-type">Baseline</span>
                    <span class="timeline-time-value">{baseline_date}</span>
                </div>
                <div class="timeline-time-label end">
                    <span class="timeline-time-type">Current</span>
                    <span class="timeline-time-value">{detection_date}</span>
                </div>
            </div>

            <div class="temporal-footer">
                <span class="temporal-footer-duration">
                    ━━━ <span class="duration-highlight">{duration_text}</span> 유지 → 변경 탐지 {location_icon}
                </span>
            </div>
        </div>
        """

    def _render_temporal_header(
        self,
        baseline_timestamp: datetime,
        detection_timestamp: datetime,
    ) -> str:
        """시간 정보 헤더만 렌더링 (객체 diff 등에 사용).

        Args:
            baseline_timestamp: 베이스라인 설정 시점
            detection_timestamp: 드리프트 탐지 시점

        Returns:
            HTML 헤더 문자열
        """
        # 기간 계산
        duration = detection_timestamp - baseline_timestamp
        total_days = duration.days
        total_hours = duration.total_seconds() / 3600

        # 기간 텍스트 생성
        if total_days >= 1:
            duration_text = f"{total_days}일간 유지"
        elif total_hours >= 1:
            duration_text = f"{int(total_hours)}시간 유지"
        else:
            duration_text = "최근 변경"

        # 날짜 포맷
        baseline_date = baseline_timestamp.strftime('%Y-%m-%d %H:%M')
        detection_date = detection_timestamp.strftime('%Y-%m-%d %H:%M')

        time_icon = self._icon("schedule", size="xs", color="primary", inline=True)
        location_icon = self._icon("location_on", size="xs", color="error", inline=True)
        return f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 10px 14px; background: {MD3_COLORS['primary_container']}; border-radius: 8px; border: 1px solid {MD3_COLORS['primary']};">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 11px; color: {MD3_COLORS['on_primary_container']}; font-weight: 600;">{time_icon} {baseline_date}</span>
                <span style="color: {MD3_COLORS['on_surface_variant']};">→</span>
                <span style="font-size: 11px; color: {MD3_COLORS['on_error_container']}; font-weight: 600;">{location_icon} {detection_date}</span>
            </div>
            <span style="padding: 3px 8px; background: {MD3_COLORS['primary_container']}; color: {MD3_COLORS['on_primary_container']}; border-radius: 10px; font-size: 10px; font-weight: 600;">
                {duration_text}
            </span>
        </div>
        """

    def _render_numeric_trend(
        self,
        field_name: str,
        baseline: float,
        current: float,
    ) -> str:
        """숫자 값 미니 트렌드 차트 렌더링.

        Args:
            field_name: 필드명
            baseline: 베이스라인 값
            current: 현재 값

        Returns:
            HTML 문자열
        """
        max_val = max(abs(baseline), abs(current), 1)  # 0 방지
        baseline_pct = (abs(baseline) / max_val) * 70 + 10  # 최소 10%, 최대 80%
        current_pct = (abs(current) / max_val) * 70 + 10

        change = current - baseline
        if baseline != 0:
            change_pct = ((current - baseline) / baseline * 100)
        else:
            change_pct = 100 if current > 0 else 0

        is_increase = change > 0
        change_class = "up" if is_increase else "down"
        bar_class = "current-up" if is_increase else "current-down"
        trend_icon = self._icon("trending_up" if is_increase else "trending_down", size="sm", inline=True)

        # 값 포맷팅
        baseline_fmt = self._format_numeric_value(baseline)
        current_fmt = self._format_numeric_value(current)
        change_fmt = f"{change_pct:+.1f}%"

        return f"""
        <div class="numeric-trend">
            <div class="trend-chart">
                <div class="trend-bar-group">
                    <div class="trend-bar baseline" style="height: {baseline_pct}px;">
                    </div>
                    <span class="trend-bar-label">Baseline</span>
                </div>
                <div class="trend-connector">
                    <div class="trend-connector-line"></div>
                    <span class="trend-change-badge {change_class}">
                        {trend_icon} {change_fmt}
                    </span>
                </div>
                <div class="trend-bar-group">
                    <div class="trend-bar {bar_class}" style="height: {current_pct}px;">
                    </div>
                    <span class="trend-bar-label">Current</span>
                </div>
            </div>
            <div class="trend-values">
                <div class="trend-value">
                    <div class="trend-value-number baseline">{baseline_fmt}</div>
                    <div class="trend-value-label">이전 값</div>
                </div>
                <div class="trend-value">
                    <div class="trend-value-number {bar_class}">{current_fmt}</div>
                    <div class="trend-value-label">현재 값</div>
                </div>
            </div>
        </div>
        """

    def _render_state_transition(
        self,
        baseline_value: Any,
        current_value: Any,
        severity: DriftSeverity,
    ) -> str:
        """Boolean/String 상태 전환 시각화.

        Args:
            baseline_value: 베이스라인 값
            current_value: 현재 값
            severity: 심각도

        Returns:
            HTML 문자열
        """
        # 값 및 아이콘 결정
        if baseline_value is None:
            baseline_icon = self._icon("remove", size="lg", color="muted")
            baseline_text = "(없음)"
        elif isinstance(baseline_value, bool):
            if baseline_value:
                baseline_icon = self._icon("check_circle", size="lg", filled=True, color="success")
            else:
                baseline_icon = self._icon("cancel", size="lg", filled=True, color="error")
            baseline_text = "Enabled" if baseline_value else "Disabled"
        else:
            baseline_icon = self._icon("description", size="lg", color="primary")
            baseline_text = self._format_value_for_display(baseline_value)

        if current_value is None:
            current_icon = self._icon("remove", size="lg", color="muted")
            current_text = "(없음)"
        elif isinstance(current_value, bool):
            if current_value:
                current_icon = self._icon("check_circle", size="lg", filled=True, color="success")
            else:
                current_icon = self._icon("cancel", size="lg", filled=True, color="error")
            current_text = "Enabled" if current_value else "Disabled"
        else:
            current_icon = self._icon("description", size="lg", color="error")
            current_text = self._format_value_for_display(current_value)

        arrow_icon = self._icon("arrow_forward", size="lg", color="muted")
        return f"""
        <div class="state-transition">
            <div class="state-box baseline">
                <div class="state-icon">{baseline_icon}</div>
                <div class="state-label">Baseline</div>
                <div class="state-value">{baseline_text}</div>
            </div>
            <div class="state-arrow">
                <div class="state-arrow-icon">{arrow_icon}</div>
                <div class="state-arrow-label">변경</div>
            </div>
            <div class="state-box current">
                <div class="state-icon">{current_icon}</div>
                <div class="state-label">Current</div>
                <div class="state-value">{current_text}</div>
            </div>
        </div>
        """

    def _render_object_diff(
        self,
        baseline_value: Any,
        current_value: Any,
    ) -> str:
        """객체/배열 Side-by-Side diff 렌더링.

        Args:
            baseline_value: 베이스라인 값
            current_value: 현재 값

        Returns:
            HTML 문자열
        """
        baseline_str = self._format_json_for_display(baseline_value)
        current_str = self._format_json_for_display(current_value)

        baseline_icon = self._icon("description", size="sm", inline=True)
        current_icon = self._icon("description", size="sm", inline=True)
        return f"""
        <div class="object-diff">
            <div class="object-diff-header">
                <div class="object-diff-header-cell baseline">{baseline_icon} Baseline (이전)</div>
                <div class="object-diff-header-cell current">{current_icon} Current (현재)</div>
            </div>
            <div class="object-diff-body">
                <div class="object-diff-cell baseline">{baseline_str}</div>
                <div class="object-diff-cell current">{current_str}</div>
            </div>
        </div>
        """

    def _render_default_timeline(
        self,
        baseline_value: Any,
        current_value: Any,
        severity: DriftSeverity,
    ) -> str:
        """기본 타임라인 시각화 (문자열 등).

        Args:
            baseline_value: 베이스라인 값
            current_value: 현재 값
            severity: 심각도

        Returns:
            HTML 문자열
        """
        baseline_str = self._format_value_for_display(baseline_value)
        current_str = self._format_value_for_display(current_value)
        severity_class = severity.value

        baseline_icon = self._icon("description", size="sm", color="primary", inline=True)
        current_icon = self._icon("description", size="sm", color="error", inline=True)
        return f"""
        <div class="change-timeline">
            <div class="timeline-point baseline">
                <div class="timeline-point-label">{baseline_icon} Baseline</div>
                <div class="timeline-point-value">{baseline_str}</div>
            </div>
            <div class="timeline-arrow">
                <div class="timeline-arrow-line"></div>
                <div class="timeline-arrow-text">변경</div>
            </div>
            <div class="timeline-point current {severity_class}">
                <div class="timeline-point-label">{current_icon} Current</div>
                <div class="timeline-point-value">{current_str}</div>
            </div>
        </div>
        """

    def _format_numeric_value(self, value: float, signed: bool = False) -> str:
        """숫자 값 포맷팅."""
        if abs(value) >= 1_000_000_000:
            formatted = f"{value / 1_000_000_000:.1f}B"
        elif abs(value) >= 1_000_000:
            formatted = f"{value / 1_000_000:.1f}M"
        elif abs(value) >= 1_000:
            formatted = f"{value / 1_000:.1f}K"
        elif isinstance(value, float):
            formatted = f"{value:.2f}"
        else:
            formatted = f"{value:,}"

        if signed and value > 0:
            formatted = "+" + formatted

        return formatted

    def _format_value_for_display(self, value: Any) -> str:
        """표시용 값 포맷팅."""
        if value is None:
            return "(없음)"
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, (int, float)):
            return self._format_numeric_value(value)
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, indent=2)
            if len(text) > 100:
                return text[:100] + "..."
            return text
        text = str(value)
        if len(text) > 100:
            return text[:100] + "..."
        return text

    def _format_json_for_display(self, value: Any) -> str:
        """JSON 표시용 포맷팅."""
        if value is None:
            return "(없음 / null)"
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(value)


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
