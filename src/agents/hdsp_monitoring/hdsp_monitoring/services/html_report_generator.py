"""
HTML Report Generator for HDSP Alert Monitoring.

알림 모니터링 결과를 HTML 리포트로 생성.
- 요약 대시보드 (심각도별 카운트)
- Pod Level / Node Level 분리 타임라인 (QuickChart.io 기반)
- 심각도별 네비게이션
- 알림 상세 카드 (클러스터, 네임스페이스, 리소스 정보)
"""

import html
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from src.agents.bdp_common.reports.base import HTMLReportBase
from src.agents.bdp_common.reports.styles import (
    ReportStyles,
    SEVERITY_COLORS,
    MD3_COLORS,
    MATERIAL_ICONS,
    get_material_icon,
)
from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import (
    ProcessedAlert,
    AlertSeverity,
)

logger = logging.getLogger(__name__)


class AlertHTMLReportGenerator(HTMLReportBase):
    """
    HDSP 알림 모니터링 HTML 리포트 생성기.

    심각도별 그룹화, 요약 통계,
    알림 상세 카드 (클러스터, 네임스페이스, 리소스 정보) 표시.
    Sticky Navigation으로 빠른 섹션 이동 지원.
    """

    SEVERITY_KOREAN = {
        "critical": "심각",
        "high": "높음",
        "medium": "보통",
    }

    # Material Icons for severity (icon name, filled, color)
    SEVERITY_ICON = {
        "critical": {"icon": "error", "filled": True, "color": "error"},
        "high": {"icon": "warning", "filled": True, "color": "warning"},
        "medium": {"icon": "info", "filled": False, "color": "primary"},
    }

    # Material Icons for K8s resource types
    RESOURCE_TYPE_ICON = {
        "Pod": "deployed_code",
        "Node": "dns",
        "Service": "hub",
        "Deployment": "rocket_launch",
        "StatefulSet": "database",
        "DaemonSet": "dynamic_feed",
        "Job": "task_alt",
        "CronJob": "schedule",
        "PersistentVolume": "hard_drive",
        "PersistentVolumeClaim": "sd_card",
    }

    def __init__(self):
        """리포트 생성기 초기화."""
        super().__init__(
            title="HDSP Alert Monitoring Report",
            styles=ReportStyles(),
        )

    def _get_additional_css(self) -> str:
        """추가 CSS 스타일 반환 (MD3 색상 팔레트)."""
        return f"""
        /* =========================================================
           Alert Card - Self-contained card design (MD3)
           ========================================================= */
        .alert-card {{
            margin-bottom: 20px;
            border-radius: 12px;
            border: 1px solid {MD3_COLORS['outline_variant']};
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            transition: box-shadow 0.2s ease;
        }}

        .alert-card:hover {{
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        }}

        .alert-card.critical {{
            border-left: 4px solid {MD3_COLORS['error']};
        }}

        .alert-card.high {{
            border-left: 4px solid {MD3_COLORS['warning']};
        }}

        .alert-card.medium {{
            border-left: 4px solid {MD3_COLORS['primary']};
        }}

        /* Card Header */
        .alert-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            padding: 16px 20px;
            background: {MD3_COLORS['surface_variant']};
            border-bottom: 1px solid {MD3_COLORS['outline_variant']};
        }}

        .alert-card-header-left {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .alert-card-title {{
            font-size: 15px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface']};
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .alert-card-title .icon {{
            font-size: 18px;
        }}

        .alert-card-meta {{
            font-size: 12px;
            color: {MD3_COLORS['on_surface_variant']};
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}

        .alert-card-meta-item {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}

        .alert-card-header-right {{
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 4px;
        }}

        /* Alert Content Box */
        .alert-content-box {{
            margin: 16px 20px;
            padding: 16px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 10px;
            border: 1px solid {MD3_COLORS['outline_variant']};
        }}

        .alert-content-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 10px;
            border-bottom: 1px dashed {MD3_COLORS['outline_variant']};
        }}

        .alert-content-title {{
            font-size: 14px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface_variant']};
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        /* Summary & Description */
        .alert-summary {{
            font-size: 14px;
            color: {MD3_COLORS['on_surface']};
            margin-bottom: 12px;
            padding: 12px;
            background: {MD3_COLORS['surface']};
            border-radius: 8px;
            border-left: 3px solid {MD3_COLORS['primary']};
            font-weight: 500;
        }}

        .alert-description {{
            font-size: 13px;
            color: {MD3_COLORS['on_surface_variant']};
            padding: 12px;
            background: {MD3_COLORS['surface']};
            border-radius: 8px;
            border-left: 3px solid {MD3_COLORS['outline']};
            line-height: 1.6;
        }}

        /* Timeline Info */
        .alert-timeline {{
            display: flex;
            align-items: center;
            gap: 24px;
            margin-top: 16px;
            padding: 12px 16px;
            background: {MD3_COLORS['primary_container']};
            border-radius: 8px;
        }}

        .timeline-item {{
            display: flex;
            flex-direction: column;
            align-items: flex-start;
        }}

        .timeline-label {{
            font-size: 10px;
            text-transform: uppercase;
            font-weight: 600;
            color: {MD3_COLORS['on_surface_variant']};
            margin-bottom: 2px;
        }}

        .timeline-value {{
            font-size: 13px;
            font-weight: 500;
            color: {MD3_COLORS['on_surface']};
        }}

        .duration-badge {{
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }}

        .duration-badge.long {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['on_error_container']};
        }}

        .duration-badge.normal {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
        }}

        /* =========================================================
           GNB - Sticky Navigation (MD3)
           ========================================================= */
        .severity-nav {{
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

        .severity-nav-label {{
            font-weight: 600;
            color: {MD3_COLORS['on_surface_variant']};
            padding: 8px 0;
            font-size: 14px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}

        .severity-nav-link {{
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

        .severity-nav-link:hover {{
            transform: translateY(-2px);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
        }}

        .severity-nav-link.critical {{
            background: {MD3_COLORS['error_container']};
            color: {MD3_COLORS['on_error_container']};
            border: 1px solid {MD3_COLORS['error']};
        }}

        .severity-nav-link.high {{
            background: {MD3_COLORS['warning_container']};
            color: {MD3_COLORS['on_warning_container']};
            border: 1px solid {MD3_COLORS['warning']};
        }}

        .severity-nav-link.medium {{
            background: {MD3_COLORS['primary_container']};
            color: {MD3_COLORS['on_primary_container']};
            border: 1px solid {MD3_COLORS['primary']};
        }}

        /* Section anchor offset for sticky nav */
        .severity-section {{
            scroll-margin-top: 80px;
            margin-bottom: 32px;
        }}

        .severity-section-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 2px solid {MD3_COLORS['outline_variant']};
        }}

        .severity-section-title {{
            font-size: 18px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface']};
        }}

        .severity-section-count {{
            background: {MD3_COLORS['outline_variant']};
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

        /* Severity badge styling */
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

        /* Resource Info Grid */
        .resource-info-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin-top: 12px;
        }}

        @media (max-width: 768px) {{
            .resource-info-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .resource-info-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 12px;
            background: {MD3_COLORS['surface']};
            border-radius: 8px;
            border: 1px solid {MD3_COLORS['outline_variant']};
        }}

        .resource-info-icon {{
            font-size: 18px;
            color: {MD3_COLORS['on_surface_variant']};
        }}

        .resource-info-content {{
            display: flex;
            flex-direction: column;
        }}

        .resource-info-label {{
            font-size: 10px;
            text-transform: uppercase;
            color: {MD3_COLORS['on_surface_variant']};
            font-weight: 600;
        }}

        .resource-info-value {{
            font-size: 13px;
            color: {MD3_COLORS['on_surface']};
            font-weight: 500;
        }}

        /* =========================================================
           Timeline Visualization - Alert Causality Chart (MD3)
           ========================================================= */
        .timeline-container {{
            background: {MD3_COLORS['surface']};
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            overflow-x: auto;
        }}

        .timeline-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 2px solid {MD3_COLORS['outline_variant']};
        }}

        .timeline-title {{
            font-size: 18px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface']};
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .timeline-subtitle {{
            font-size: 12px;
            color: {MD3_COLORS['on_surface_variant']};
        }}

        .timeline-legend {{
            display: flex;
            gap: 16px;
            font-size: 12px;
        }}

        .timeline-legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .timeline-legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
        }}

        .timeline-legend-dot.critical {{
            background: {MD3_COLORS['error']};
        }}

        .timeline-legend-dot.high {{
            background: {MD3_COLORS['warning']};
        }}

        .timeline-legend-dot.medium {{
            background: {MD3_COLORS['primary']};
        }}

        /* Time Scale (X-axis) */
        .timeline-scale {{
            display: flex;
            margin-left: 220px;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 2px solid {MD3_COLORS['outline_variant']};
            position: relative;
        }}

        .timeline-scale-mark {{
            flex: 1;
            font-size: 11px;
            color: {MD3_COLORS['on_surface_variant']};
            text-align: left;
            position: relative;
        }}

        .timeline-scale-mark::before {{
            content: '';
            position: absolute;
            left: 0;
            bottom: -10px;
            width: 1px;
            height: 6px;
            background: {MD3_COLORS['outline']};
        }}

        /* Timeline Rows */
        .timeline-rows {{
            min-width: 800px;
        }}

        .timeline-row {{
            display: flex;
            align-items: center;
            height: 32px;
            margin-bottom: 6px;
        }}

        .timeline-row:hover {{
            background: {MD3_COLORS['surface_variant']};
            border-radius: 4px;
        }}

        .timeline-label {{
            width: 220px;
            flex-shrink: 0;
            font-size: 12px;
            font-weight: 500;
            padding-right: 12px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .timeline-label .icon {{
            font-size: 14px;
        }}

        /* Track and Bar */
        .timeline-track {{
            flex: 1;
            height: 20px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 4px;
            position: relative;
            overflow: hidden;
        }}

        .timeline-bar {{
            position: absolute;
            height: 100%;
            border-radius: 4px;
            cursor: pointer;
            transition: opacity 0.2s, transform 0.2s;
            min-width: 6px;
            display: flex;
            align-items: center;
            padding-left: 6px;
            font-size: 10px;
            color: white;
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
        }}

        .timeline-bar:hover {{
            opacity: 0.85;
            transform: scaleY(1.15);
            z-index: 10;
        }}

        /* Severity Colors */
        .timeline-bar.critical {{
            background: {MD3_COLORS['error']};
            box-shadow: 0 1px 3px rgba(211, 47, 47, 0.4);
        }}

        .timeline-bar.high {{
            background: {MD3_COLORS['warning']};
            box-shadow: 0 1px 3px rgba(245, 124, 0, 0.4);
        }}

        .timeline-bar.medium {{
            background: {MD3_COLORS['primary']};
            box-shadow: 0 1px 3px rgba(25, 118, 210, 0.4);
        }}

        /* Tooltip */
        .timeline-bar::after {{
            content: attr(data-tooltip);
            position: absolute;
            left: 50%;
            bottom: 100%;
            transform: translateX(-50%);
            background: {MD3_COLORS['on_surface']};
            color: {MD3_COLORS['surface']};
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 11px;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s;
            z-index: 100;
            margin-bottom: 8px;
        }}

        .timeline-bar:hover::after {{
            opacity: 1;
        }}

        /* Causality Hint */
        .timeline-causality-hint {{
            margin-top: 16px;
            padding: 12px 16px;
            background: {MD3_COLORS['primary_container']};
            border-radius: 8px;
            font-size: 12px;
            color: {MD3_COLORS['on_surface_variant']};
            display: flex;
            align-items: flex-start;
            gap: 8px;
        }}

        .timeline-causality-hint .hint-icon {{
            font-size: 16px;
            flex-shrink: 0;
            color: {MD3_COLORS['primary']};
        }}

        .timeline-causality-hint .hint-text {{
            line-height: 1.5;
        }}

        /* Now marker */
        .timeline-now-marker {{
            position: absolute;
            right: 0;
            top: 0;
            bottom: 0;
            width: 2px;
            background: {MD3_COLORS['success']};
        }}

        .timeline-now-label {{
            position: absolute;
            right: -4px;
            top: -20px;
            font-size: 10px;
            color: {MD3_COLORS['success']};
            font-weight: 600;
        }}

        /* Collapsible Section */
        .collapsible-section {{
            margin-top: 24px;
        }}

        .collapsible-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.2s;
        }}

        .collapsible-header:hover {{
            background: {MD3_COLORS['outline_variant']};
        }}

        .collapsible-header-title {{
            font-size: 15px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface_variant']};
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .collapsible-toggle {{
            font-size: 12px;
            color: {MD3_COLORS['on_surface_variant']};
            display: flex;
            align-items: center;
            gap: 4px;
        }}

        .collapsible-content {{
            display: none;
            margin-top: 16px;
        }}

        .collapsible-content.expanded {{
            display: block;
        }}

        /* Responsive */
        @media (max-width: 768px) {{
            .timeline-container {{
                overflow-x: scroll;
            }}

            .timeline-rows {{
                min-width: 600px;
            }}

            .timeline-label {{
                width: 150px;
                font-size: 11px;
            }}
        }}

        /* =========================================================
           Grouped Timeline - Pod/Node Level Separation (MD3)
           ========================================================= */
        .grouped-timeline-container {{
            background: {MD3_COLORS['surface']};
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        }}

        .grouped-timeline-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid {MD3_COLORS['outline_variant']};
        }}

        .grouped-timeline-title {{
            font-size: 18px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface']};
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .grouped-timeline-subtitle {{
            font-size: 12px;
            color: {MD3_COLORS['on_surface_variant']};
        }}

        /* Group Section */
        .timeline-group {{
            margin-bottom: 24px;
            padding: 16px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 8px;
        }}

        .timeline-group:last-child {{
            margin-bottom: 0;
        }}

        .timeline-group-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid {MD3_COLORS['outline_variant']};
        }}

        .timeline-group-icon {{
            font-size: 16px;
            color: {MD3_COLORS['on_surface_variant']};
        }}

        .timeline-group-title {{
            font-size: 14px;
            font-weight: 600;
            color: {MD3_COLORS['on_surface_variant']};
        }}

        .timeline-group-count {{
            font-size: 12px;
            color: {MD3_COLORS['on_surface_variant']};
            background: {MD3_COLORS['outline_variant']};
            padding: 2px 8px;
            border-radius: 10px;
        }}

        /* QuickChart Timeline Image */
        .timeline-chart-wrapper {{
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 12px 0;
        }}

        .timeline-chart-img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
        }}

        /* Alert List in Group */
        .timeline-alert-list {{
            margin-top: 12px;
        }}

        .timeline-alert-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: {MD3_COLORS['surface']};
            border-radius: 6px;
            margin-bottom: 6px;
            border-left: 3px solid {MD3_COLORS['outline_variant']};
        }}

        .timeline-alert-item:last-child {{
            margin-bottom: 0;
        }}

        .timeline-alert-item.critical {{
            border-left-color: {MD3_COLORS['error']};
        }}

        .timeline-alert-item.high {{
            border-left-color: {MD3_COLORS['warning']};
        }}

        .timeline-alert-item.medium {{
            border-left-color: {MD3_COLORS['primary']};
        }}

        .timeline-alert-severity {{
            font-size: 14px;
            display: flex;
            align-items: center;
        }}

        .timeline-alert-name {{
            font-size: 13px;
            font-weight: 500;
            color: {MD3_COLORS['on_surface']};
            flex: 1;
        }}

        .timeline-alert-time {{
            font-size: 11px;
            color: {MD3_COLORS['on_surface_variant']};
            white-space: nowrap;
        }}

        .timeline-alert-duration {{
            font-size: 11px;
            color: {MD3_COLORS['on_surface_variant']};
            padding: 2px 6px;
            background: {MD3_COLORS['surface_variant']};
            border-radius: 4px;
        }}

        /* No Data Message */
        .timeline-no-data {{
            text-align: center;
            padding: 40px 20px;
            color: {MD3_COLORS['on_surface_variant']};
            font-size: 14px;
        }}

        /* =========================================================
           KakaoTalk Message Preview
           ========================================================= */
        .kakao-preview {{
            margin: 16px 20px 20px;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid #fae100;
        }}

        .kakao-preview-header {{
            background: #fae100;
            color: #3c1e1e;
            padding: 8px 12px;
            font-weight: 600;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .kakao-preview-content {{
            background: {MD3_COLORS['surface_variant']};
            padding: 12px;
        }}

        .kakao-preview-content pre {{
            font-family: 'Apple SD Gothic Neo', -apple-system, BlinkMacSystemFont, 'Malgun Gothic', sans-serif;
            font-size: 11px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
            margin: 0;
            color: {MD3_COLORS['on_surface']};
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

    def generate_content(self, data: List[ProcessedAlert]) -> str:
        """리포트 콘텐츠 생성.

        Args:
            data: ProcessedAlert 목록

        Returns:
            HTML 콘텐츠
        """
        sections = []

        # 1. 요약 대시보드
        sections.append(self._generate_summary_dashboard(data))

        # 2. Pod/Node 레벨 분리 타임라인 (QuickChart.io 기반)
        if data:
            pod_alerts, node_alerts = self._categorize_alerts_by_level(data)

            # 2-1. Pod Level 타임라인 (namespace별 그룹화)
            if pod_alerts:
                pod_groups = self._group_pod_alerts_by_namespace(pod_alerts)
                sections.append(self._generate_grouped_timeline_section(
                    title="Pod Level 타임라인",
                    icon_name="deployed_code",
                    groups=pod_groups,
                    group_icon_name="folder",
                ))

            # 2-2. Node Level 타임라인 (node_group별 그룹화)
            if node_alerts:
                node_groups = self._group_node_alerts_by_node_group(node_alerts)
                sections.append(self._generate_grouped_timeline_section(
                    title="Node Level 타임라인",
                    icon_name="dns",
                    groups=node_groups,
                    group_icon_name="label",
                ))

        # 3. 심각도별 네비게이션
        by_severity = self._group_by_severity(data)
        if by_severity:
            sections.append(self._build_severity_nav(by_severity))

        # 4. 심각도별 알림 섹션
        for severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM]:
            alerts = by_severity.get(severity, [])
            if alerts:
                sections.append(self._generate_severity_section(severity, alerts))

        return "\n".join(sections)

    def _build_severity_nav(self, by_severity: Dict[AlertSeverity, List[ProcessedAlert]]) -> str:
        """심각도별 네비게이션 생성.

        Args:
            by_severity: 심각도별 ProcessedAlert 그룹

        Returns:
            HTML 네비게이션 문자열
        """
        links = []
        for severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM]:
            alerts = by_severity.get(severity, [])
            if alerts:
                severity_korean = self.SEVERITY_KOREAN.get(severity.value, severity.value)
                severity_config = self.SEVERITY_ICON.get(severity.value, {"icon": "info", "filled": False, "color": "primary"})
                icon_html = self._icon(
                    severity_config["icon"],
                    size="sm",
                    filled=severity_config["filled"],
                    color=severity_config["color"],
                )
                count = len(alerts)
                links.append(
                    f'<a href="#section-{severity.value}" class="severity-nav-link {severity.value}">'
                    f'{icon_html} {severity_korean} ({count})'
                    f'</a>'
                )

        nav_icon = self._icon("near_me", size="sm", color="muted")
        return f"""
        <div class="severity-nav">
            <span class="severity-nav-label">{nav_icon} 바로가기:</span>
            {" ".join(links)}
        </div>
        """

    def _generate_summary_dashboard(self, alerts: List[ProcessedAlert]) -> str:
        """요약 대시보드 생성."""
        # 심각도별 카운트
        severity_counts = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.HIGH: 0,
            AlertSeverity.MEDIUM: 0,
        }
        for alert in alerts:
            if alert.severity in severity_counts:
                severity_counts[alert.severity] += 1

        # 통계 카드
        stats = [
            {
                "label": "총 알림",
                "value": str(len(alerts)),
                "color": self.styles.info_color,
            },
            {
                "label": "심각",
                "value": str(severity_counts[AlertSeverity.CRITICAL]),
                "color": SEVERITY_COLORS["critical"]["border"],
            },
            {
                "label": "높음",
                "value": str(severity_counts[AlertSeverity.HIGH]),
                "color": SEVERITY_COLORS["high"]["border"],
            },
            {
                "label": "보통",
                "value": str(severity_counts[AlertSeverity.MEDIUM]),
                "color": SEVERITY_COLORS["medium"]["border"],
            },
        ]

        stat_cards = self.render_stat_cards(stats, columns=4)

        # 상태 메시지
        if not alerts:
            check_icon = self._icon("check_circle", size="sm", filled=True, color="success", inline=True)
            status_alert = self.render_alert(
                f"{check_icon} 현재 발생 중인 알림이 없습니다.",
                "success",
            )
        elif severity_counts[AlertSeverity.CRITICAL] > 0:
            error_icon = self._icon("error", size="sm", filled=True, color="error", inline=True)
            status_alert = self.render_alert(
                f"{error_icon} {severity_counts[AlertSeverity.CRITICAL]}건의 심각한 알림이 발생했습니다. 즉시 확인이 필요합니다.",
                "danger",
            )
        elif severity_counts[AlertSeverity.HIGH] > 0:
            warning_icon = self._icon("warning", size="sm", filled=True, color="warning", inline=True)
            status_alert = self.render_alert(
                f"{warning_icon} {severity_counts[AlertSeverity.HIGH]}건의 높은 심각도 알림이 발생했습니다.",
                "warning",
            )
        else:
            info_icon = self._icon("info", size="sm", color="primary", inline=True)
            status_alert = self.render_alert(
                f"{info_icon} {len(alerts)}건의 알림이 발생했습니다.",
                "info",
            )

        dashboard_icon = self._icon("dashboard", size="sm", color="muted", inline=True)
        return self.render_card(
            f"{dashboard_icon} 알림 요약",
            f"{status_alert}{stat_cards}",
        )

    def _group_by_severity(
        self,
        alerts: List[ProcessedAlert],
    ) -> Dict[AlertSeverity, List[ProcessedAlert]]:
        """심각도별 그룹화."""
        by_severity: Dict[AlertSeverity, List[ProcessedAlert]] = {}
        for alert in alerts:
            if alert.severity not in by_severity:
                by_severity[alert.severity] = []
            by_severity[alert.severity].append(alert)
        return by_severity

    def _categorize_alerts_by_level(
        self,
        alerts: List[ProcessedAlert],
    ) -> Tuple[List[ProcessedAlert], List[ProcessedAlert]]:
        """Pod Level과 Node Level 알림 분리.

        Args:
            alerts: 전체 알림 목록

        Returns:
            (pod_alerts, node_alerts) 튜플
        """
        pod_alerts = [a for a in alerts if a.resource_type != "Node"]
        node_alerts = [a for a in alerts if a.resource_type == "Node"]
        return pod_alerts, node_alerts

    def _group_pod_alerts_by_namespace(
        self,
        alerts: List[ProcessedAlert],
    ) -> Dict[str, List[ProcessedAlert]]:
        """Pod 알림을 namespace별로 그룹화 및 severity 정렬.

        Args:
            alerts: Pod 레벨 알림 목록

        Returns:
            namespace → 알림 목록 딕셔너리 (severity 순 정렬됨)
        """
        groups: Dict[str, List[ProcessedAlert]] = {}
        for alert in alerts:
            ns = alert.namespace
            if ns not in groups:
                groups[ns] = []
            groups[ns].append(alert)

        # 각 그룹 내 severity → first_seen 순 정렬
        severity_order = {AlertSeverity.CRITICAL: 0, AlertSeverity.HIGH: 1, AlertSeverity.MEDIUM: 2}
        for ns in groups:
            groups[ns].sort(key=lambda a: (severity_order.get(a.severity, 3), a.first_seen))

        return groups

    def _group_node_alerts_by_node_group(
        self,
        alerts: List[ProcessedAlert],
    ) -> Dict[str, List[ProcessedAlert]]:
        """Node 알림을 node_group label별로 그룹화 및 severity 정렬.

        Args:
            alerts: Node 레벨 알림 목록

        Returns:
            node_group → 알림 목록 딕셔너리 (severity 순 정렬됨)
        """
        groups: Dict[str, List[ProcessedAlert]] = {}
        for alert in alerts:
            node_group = alert.labels.get("node_group", "unknown")
            if node_group not in groups:
                groups[node_group] = []
            groups[node_group].append(alert)

        # 각 그룹 내 severity → first_seen 순 정렬
        severity_order = {AlertSeverity.CRITICAL: 0, AlertSeverity.HIGH: 1, AlertSeverity.MEDIUM: 2}
        for ng in groups:
            groups[ng].sort(key=lambda a: (severity_order.get(a.severity, 3), a.first_seen))

        return groups

    def _sort_groups_by_count(
        self,
        groups: Dict[str, List[ProcessedAlert]],
    ) -> List[Tuple[str, List[ProcessedAlert]]]:
        """그룹을 알림 수 → 이름 순으로 정렬.

        Args:
            groups: 그룹 딕셔너리

        Returns:
            정렬된 (그룹명, 알림 목록) 튜플 리스트
        """
        return sorted(
            groups.items(),
            key=lambda x: (-len(x[1]), x[0])  # 알림 수 내림차순, 이름 오름차순
        )

    def _generate_timeline_chart_url(
        self,
        alerts: List[ProcessedAlert],
        title: str,
        width: int = 700,
        height: int = 300,
    ) -> Optional[str]:
        """QuickChart.io를 사용하여 Gantt 스타일 타임라인 차트 URL 생성.

        x축에 실제 시간을 표시하고, 각 바에 시작 시간을 표시하여 직관성을 높임.

        Args:
            alerts: 알림 목록
            title: 차트 제목
            width: 차트 너비
            height: 차트 높이

        Returns:
            QuickChart 이미지 URL
        """
        if not alerts:
            return None

        # 시간 범위 계산
        min_time = min(a.first_seen for a in alerts)
        max_time = datetime.utcnow()

        # 약간의 여유 추가
        min_time = min_time - timedelta(minutes=5)
        max_time = max_time + timedelta(minutes=2)

        total_minutes = (max_time - min_time).total_seconds() / 60

        # 시간 형식 결정 (24시간 초과 시 날짜 포함)
        total_hours = total_minutes / 60
        time_format = "%m/%d %H:%M" if total_hours > 24 else "%H:%M"

        # 시간 눈금 간격 결정 (5~8개 눈금 목표)
        if total_minutes <= 60:
            interval = 15
        elif total_minutes <= 180:
            interval = 30
        elif total_minutes <= 360:
            interval = 60
        else:
            interval = 120

        # x축 시간 레이블: 시작/종료 시간만 간단히 표시
        start_time_str = min_time.strftime(time_format)
        end_time_str = max_time.strftime(time_format)
        scale_label_text = f"{start_time_str} → {end_time_str}"

        # 알림별 데이터 준비 (Horizontal bar chart로 Gantt 표현)
        labels = []
        start_offsets = []
        durations = []
        bar_colors = []

        severity_colors = {
            AlertSeverity.CRITICAL: "rgba(239, 68, 68, 0.85)",
            AlertSeverity.HIGH: "rgba(245, 158, 11, 0.85)",
            AlertSeverity.MEDIUM: "rgba(59, 130, 246, 0.85)",
        }

        for alert in alerts:
            # 알림명만 표시 (시작시간은 하단 리스트에서 확인)
            labels.append(alert.alert_name[:18])

            start_offset = (alert.first_seen - min_time).total_seconds() / 60
            end_time = alert.last_seen if alert.last_seen and alert.last_seen < max_time else max_time
            duration = (end_time - alert.first_seen).total_seconds() / 60
            duration = max(duration, total_minutes * 0.03)  # 최소 너비 보장

            start_offsets.append(round(start_offset, 1))
            durations.append(round(duration, 1))
            bar_colors.append(severity_colors.get(alert.severity, "rgba(107, 114, 128, 0.85)"))

        # Chart.js 설정 (Horizontal stacked bar로 Gantt 표현)
        # 참고: QuickChart.io는 JS 함수를 지원하지 않으므로 정적 값만 사용
        chart_config = {
            "type": "horizontalBar",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "",
                        "data": start_offsets,
                        "backgroundColor": "rgba(0, 0, 0, 0)",
                        "borderWidth": 0,
                        "barThickness": 12,  # 바 두께 고정
                        "datalabels": {"display": False},
                    },
                    {
                        "label": "",
                        "data": durations,
                        "backgroundColor": bar_colors,
                        "borderRadius": 3,
                        "barThickness": 12,  # 바 두께 고정
                        "datalabels": {"display": False},
                    },
                ],
            },
            "options": {
                "responsive": False,
                "legend": {"display": False},
                "title": {
                    "display": False,  # 제목 숨김 (HTML에서 별도 표시)
                },
                "scales": {
                    "xAxes": [{
                        "stacked": True,
                        "ticks": {
                            "min": 0,
                            "max": round(total_minutes, 1),
                            "display": False,  # x축 숫자 숨김
                        },
                        "gridLines": {"display": False},
                        "scaleLabel": {
                            "display": True,
                            "labelString": scale_label_text,
                            "fontSize": 9,
                            "fontColor": "#6b7280",
                        },
                    }],
                    "yAxes": [{
                        "stacked": True,
                        "ticks": {
                            "fontSize": 9,
                            "fontColor": "#374151",
                        },
                        "gridLines": {"display": False},
                        "scaleLabel": {"display": False},
                    }],
                },
                "layout": {
                    "padding": {"left": 5, "right": 10, "top": 5, "bottom": 5},
                },
            },
        }

        # URL 생성 (devicePixelRatio=2로 고해상도 렌더링)
        chart_json = json.dumps(chart_config, ensure_ascii=False)
        encoded_config = quote(chart_json)
        url = f"https://quickchart.io/chart?c={encoded_config}&w={width}&h={height}&bkg=white&devicePixelRatio=2"

        return url

    def _generate_grouped_timeline_section(
        self,
        title: str,
        icon_name: str,
        groups: Dict[str, List[ProcessedAlert]],
        group_icon_name: str,
    ) -> str:
        """그룹별 타임라인 섹션 HTML 생성.

        Args:
            title: 섹션 제목
            icon_name: Material Symbol 아이콘 이름
            groups: 그룹별 알림 딕셔너리
            group_icon_name: 그룹 Material Symbol 아이콘 이름

        Returns:
            HTML 문자열
        """
        if not groups:
            return ""

        # 전체 알림 수
        total_count = sum(len(alerts) for alerts in groups.values())

        # 시간 범위 계산
        all_alerts = [a for alerts in groups.values() for a in alerts]
        scale = self._calculate_time_scale(all_alerts)

        # 시간 범위 표시 형식 결정
        total_hours = scale['total_minutes'] / 60
        if total_hours > 24:
            time_format = "%m/%d %H:%M"
        else:
            time_format = "%H:%M"

        time_range_text = f"{scale['min_time'].strftime(time_format)} ~ {scale['max_time'].strftime(time_format)}"

        # 그룹 정렬 (알림 수 내림차순)
        sorted_groups = self._sort_groups_by_count(groups)

        # 그룹별 HTML 생성
        group_html_list = []
        for group_name, alerts in sorted_groups:
            group_html = self._generate_group_timeline(
                group_name, alerts, scale, group_icon_name, time_format
            )
            group_html_list.append(group_html)

        # 아이콘 렌더링
        title_icon = self._icon(icon_name, size="sm", color="muted")

        return f'''
        <div class="grouped-timeline-container">
            <div class="grouped-timeline-header">
                <div>
                    <div class="grouped-timeline-title">
                        {title_icon} {title}
                    </div>
                    <div class="grouped-timeline-subtitle">
                        {time_range_text} • 총 {total_count}건 • {len(groups)}개 그룹
                    </div>
                </div>
                <div class="timeline-legend">
                    <div class="timeline-legend-item">
                        <div class="timeline-legend-dot critical"></div>
                        <span>심각</span>
                    </div>
                    <div class="timeline-legend-item">
                        <div class="timeline-legend-dot high"></div>
                        <span>높음</span>
                    </div>
                    <div class="timeline-legend-item">
                        <div class="timeline-legend-dot medium"></div>
                        <span>보통</span>
                    </div>
                </div>
            </div>
            {''.join(group_html_list)}
        </div>
        '''

    def _generate_group_timeline(
        self,
        group_name: str,
        alerts: List[ProcessedAlert],
        scale: Dict[str, Any],
        icon_name: str,
        time_format: str,
    ) -> str:
        """개별 그룹의 타임라인 HTML 생성.

        Args:
            group_name: 그룹 이름
            alerts: 알림 목록
            scale: 시간 스케일 설정
            icon_name: Material Symbol 아이콘 이름
            time_format: 시간 표시 형식

        Returns:
            HTML 문자열
        """
        # 알림 목록 HTML
        alert_items = []
        for alert in alerts:
            severity_class = alert.severity.value
            severity_config = self.SEVERITY_ICON.get(alert.severity.value, {"icon": "info", "filled": False, "color": "primary"})
            severity_icon = self._icon(
                severity_config["icon"],
                size="sm",
                filled=severity_config["filled"],
                color=severity_config["color"],
            )
            time_str = alert.first_seen.strftime(time_format)
            duration = alert.duration_minutes
            if duration >= 60:
                duration_text = f"{duration // 60}h {duration % 60}m"
            else:
                duration_text = f"{duration}m"

            alert_items.append(f'''
            <div class="timeline-alert-item {severity_class}">
                <span class="timeline-alert-severity">{severity_icon}</span>
                <span class="timeline-alert-name">{alert.alert_name}</span>
                <span class="timeline-alert-time">{time_str}</span>
                <span class="timeline-alert-duration">{duration_text}</span>
            </div>
            ''')

        # QuickChart.io 차트 URL 생성 (간결한 사이즈)
        chart_url = self._generate_timeline_chart_url(
            alerts,
            title=f"{group_name}",
            width=550,
            height=max(60, len(alerts) * 22 + 30),
        )

        chart_html = ""
        if chart_url:
            chart_html = f'''
            <div class="timeline-chart-wrapper">
                <img src="{chart_url}" alt="{group_name} Timeline" class="timeline-chart-img">
            </div>
            '''

        # 그룹 아이콘 렌더링
        group_icon = self._icon(icon_name, size="sm", color="muted")

        return f'''
        <div class="timeline-group">
            <div class="timeline-group-header">
                <span class="timeline-group-icon">{group_icon}</span>
                <span class="timeline-group-title">{group_name}</span>
                <span class="timeline-group-count">{len(alerts)}건</span>
            </div>
            {chart_html}
            <div class="timeline-alert-list">
                {''.join(alert_items)}
            </div>
        </div>
        '''

    def _calculate_time_scale(
        self,
        alerts: List[ProcessedAlert],
    ) -> Dict[str, Any]:
        """시간 범위 및 스케일 계산.

        Args:
            alerts: ProcessedAlert 목록

        Returns:
            시간 스케일 설정 딕셔너리
        """
        if not alerts:
            now = datetime.utcnow()
            return {
                "min_time": now - timedelta(hours=1),
                "max_time": now,
                "total_minutes": 60,
                "intervals": [],
            }

        # 시간 범위 계산 (first_seen ~ 현재)
        min_time = min(a.first_seen for a in alerts)
        max_time = datetime.utcnow()

        # 약간의 여유 추가 (앞뒤 5분)
        min_time = min_time - timedelta(minutes=5)
        max_time = max_time + timedelta(minutes=2)

        total_minutes = (max_time - min_time).total_seconds() / 60

        # 적절한 시간 간격 결정
        if total_minutes <= 60:
            interval_minutes = 15
        elif total_minutes <= 180:
            interval_minutes = 30
        elif total_minutes <= 360:
            interval_minutes = 60
        else:
            interval_minutes = 120

        # 시간 눈금 생성
        intervals = self._generate_time_intervals(min_time, max_time, interval_minutes)

        return {
            "min_time": min_time,
            "max_time": max_time,
            "total_minutes": total_minutes,
            "interval_minutes": interval_minutes,
            "intervals": intervals,
        }

    def _generate_time_intervals(
        self,
        min_time: datetime,
        max_time: datetime,
        interval_minutes: int,
    ) -> List[Tuple[datetime, str]]:
        """시간 눈금 생성.

        Args:
            min_time: 시작 시간
            max_time: 종료 시간
            interval_minutes: 눈금 간격 (분)

        Returns:
            (시간, 레이블) 튜플 목록
        """
        intervals = []
        # 시작 시간을 interval에 맞게 정렬
        start_minute = (min_time.minute // interval_minutes) * interval_minutes
        current = min_time.replace(minute=start_minute, second=0, microsecond=0)

        # 24시간 초과 시 날짜+시간 형식 사용
        total_hours = (max_time - min_time).total_seconds() / 3600
        if total_hours > 24:
            time_format = "%m/%d %H:%M"
        else:
            time_format = "%H:%M"

        while current <= max_time:
            label = current.strftime(time_format)
            intervals.append((current, label))
            current = current + timedelta(minutes=interval_minutes)

        return intervals

    def _generate_timeline_section(
        self,
        alerts: List[ProcessedAlert],
        max_hours: int = 3,
    ) -> str:
        """타임라인 섹션 생성.

        Args:
            alerts: ProcessedAlert 목록
            max_hours: 타임라인에 표시할 최대 시간 범위 (기본 3시간)

        Returns:
            HTML 타임라인 섹션 문자열
        """
        if not alerts:
            return ""

        # 최근 N시간 내 알림만 필터링 (인과관계 시각화에 적합한 범위)
        now = datetime.utcnow()
        cutoff_time = now - timedelta(hours=max_hours)
        recent_alerts = [a for a in alerts if a.first_seen >= cutoff_time]

        # 최근 알림이 없으면 전체 알림 중 가장 최근 것들 사용
        if not recent_alerts:
            sorted_by_time = sorted(alerts, key=lambda x: x.first_seen, reverse=True)
            recent_alerts = sorted_by_time[:10]  # 최근 10개만

        # 시간 스케일 계산
        scale = self._calculate_time_scale(recent_alerts)

        # 시간순 정렬 (first_seen 오름차순)
        sorted_alerts = sorted(recent_alerts, key=lambda x: x.first_seen)

        # 타임라인에서 제외된 알림 수
        excluded_count = len(alerts) - len(recent_alerts)

        # 시간 눈금 HTML
        scale_marks = []
        for i, (_, label) in enumerate(scale["intervals"]):
            scale_marks.append(f'<div class="timeline-scale-mark">{label}</div>')

        # 타임라인 행 생성
        timeline_rows = []
        for alert in sorted_alerts:
            timeline_rows.append(self._generate_timeline_bar(alert, scale))

        # 인과관계 힌트 생성
        causality_hint = self._generate_causality_hint(sorted_alerts)

        # 시간 범위 표시
        time_range_text = f"{scale['min_time'].strftime('%H:%M')} ~ {scale['max_time'].strftime('%H:%M')}"

        # 지속 시간 표시 형식
        total_minutes = int(scale['total_minutes'])
        if total_minutes >= 60:
            hours = total_minutes // 60
            mins = total_minutes % 60
            total_duration = f"약 {hours}시간 {mins}분" if mins > 0 else f"약 {hours}시간"
        else:
            total_duration = f"약 {total_minutes}분"

        # 제외된 알림 메시지
        excluded_note = ""
        if excluded_count > 0:
            excluded_note = f' • <span style="color: #6b7280;">이전 알림 {excluded_count}건은 하단 상세 목록에서 확인</span>'

        timeline_icon = self._icon("timeline", size="sm", color="muted")

        return f"""
        <div class="timeline-container">
            <div class="timeline-header">
                <div>
                    <div class="timeline-title">
                        {timeline_icon} 알림 타임라인 (최근 {max_hours}시간)
                    </div>
                    <div class="timeline-subtitle">
                        {time_range_text} ({total_duration}) • {len(sorted_alerts)}건 표시{excluded_note}
                    </div>
                </div>
                <div class="timeline-legend">
                    <div class="timeline-legend-item">
                        <div class="timeline-legend-dot critical"></div>
                        <span>심각</span>
                    </div>
                    <div class="timeline-legend-item">
                        <div class="timeline-legend-dot high"></div>
                        <span>높음</span>
                    </div>
                    <div class="timeline-legend-item">
                        <div class="timeline-legend-dot medium"></div>
                        <span>보통</span>
                    </div>
                </div>
            </div>
            <div class="timeline-scale">
                {''.join(scale_marks)}
                <div class="timeline-now-marker">
                    <span class="timeline-now-label">NOW</span>
                </div>
            </div>
            <div class="timeline-rows">
                {''.join(timeline_rows)}
            </div>
            {causality_hint}
        </div>
        """

    def _generate_timeline_bar(
        self,
        alert: ProcessedAlert,
        scale: Dict[str, Any],
    ) -> str:
        """개별 알림의 타임라인 바 HTML 생성.

        Args:
            alert: ProcessedAlert 객체
            scale: 시간 스케일 설정

        Returns:
            HTML 타임라인 행 문자열
        """
        severity_class = alert.severity.value
        severity_config = self.SEVERITY_ICON.get(alert.severity.value, {"icon": "info", "filled": False, "color": "primary"})
        severity_icon = self._icon(
            severity_config["icon"],
            size="sm",
            filled=severity_config["filled"],
            color=severity_config["color"],
        )

        # 위치 계산 (%)
        start_offset = (alert.first_seen - scale["min_time"]).total_seconds() / 60
        start_percent = (start_offset / scale["total_minutes"]) * 100

        # 너비 계산 (현재까지 지속)
        now = datetime.utcnow()
        end_time = alert.last_seen if alert.last_seen and alert.last_seen < now else now
        duration = (end_time - alert.first_seen).total_seconds() / 60
        width_percent = (duration / scale["total_minutes"]) * 100

        # 최소 너비 보장
        width_percent = max(width_percent, 1.5)

        # 툴팁 텍스트
        duration_text = f"{int(duration)}분" if duration < 60 else f"{int(duration // 60)}시간 {int(duration % 60)}분"
        tooltip = f"{alert.alert_name} | {alert.first_seen.strftime('%H:%M')} 시작 | {duration_text} 지속 | {alert.namespace}"

        # 바 내부 텍스트 (넓으면 표시)
        bar_text = ""
        if width_percent > 15:
            bar_text = duration_text

        return f"""
        <div class="timeline-row">
            <div class="timeline-label">
                <span class="icon">{severity_icon}</span>
                {alert.alert_name}
            </div>
            <div class="timeline-track">
                <div class="timeline-bar {severity_class}"
                     style="left: {start_percent:.1f}%; width: {width_percent:.1f}%;"
                     data-tooltip="{tooltip}">
                    {bar_text}
                </div>
            </div>
        </div>
        """

    def _generate_causality_hint(self, sorted_alerts: List[ProcessedAlert]) -> str:
        """인과관계 힌트 생성.

        Args:
            sorted_alerts: 시간순 정렬된 알림 목록

        Returns:
            HTML 힌트 문자열
        """
        if len(sorted_alerts) < 2:
            return ""

        # 첫 번째 알림과 마지막 알림
        first_alert = sorted_alerts[0]
        last_alert = sorted_alerts[-1]

        # 시간 차이
        time_diff = (last_alert.first_seen - first_alert.first_seen).total_seconds() / 60

        # 동일 네임스페이스 알림 그룹 찾기
        namespace_groups: Dict[str, List[ProcessedAlert]] = {}
        for alert in sorted_alerts:
            if alert.namespace not in namespace_groups:
                namespace_groups[alert.namespace] = []
            namespace_groups[alert.namespace].append(alert)

        # 연쇄 반응 가능성 분석
        hints = []

        # 같은 네임스페이스에서 여러 알림이 발생한 경우
        for ns, ns_alerts in namespace_groups.items():
            if len(ns_alerts) >= 2:
                alert_names = [a.alert_name for a in ns_alerts[:3]]
                hints.append(f"<strong>{ns}</strong> 네임스페이스: {' → '.join(alert_names)}")

        if not hints:
            hints.append(f"첫 알림 <strong>{first_alert.alert_name}</strong> 발생 후 약 {int(time_diff)}분 내에 {len(sorted_alerts)}개의 알림이 연쇄 발생")

        hint_icon = self._icon("lightbulb", size="sm", filled=True, color="primary")

        return f"""
        <div class="timeline-causality-hint">
            <span class="hint-icon">{hint_icon}</span>
            <span class="hint-text">
                <strong>인과관계 힌트:</strong> 위에서 아래로 시간순 정렬되어 있습니다.
                먼저 발생한 알림(위쪽)이 후속 알림(아래쪽)의 원인일 수 있습니다.<br>
                {'<br>'.join(hints)}
            </span>
        </div>
        """

    def _generate_severity_section(
        self,
        severity: AlertSeverity,
        alerts: List[ProcessedAlert],
    ) -> str:
        """심각도별 섹션 생성.

        Args:
            severity: 알림 심각도
            alerts: ProcessedAlert 목록

        Returns:
            HTML 섹션 문자열
        """
        severity_korean = self.SEVERITY_KOREAN.get(severity.value, severity.value)
        severity_config = self.SEVERITY_ICON.get(severity.value, {"icon": "info", "filled": False, "color": "primary"})
        section_icon = self._icon(
            severity_config["icon"],
            size="lg",
            filled=severity_config["filled"],
            color=severity_config["color"],
        )

        # 네임스페이스 → 알림명 순으로 정렬
        sorted_alerts = sorted(alerts, key=lambda x: (x.namespace, x.alert_name))

        # 각 알림에 대한 카드 생성
        cards = []
        for alert in sorted_alerts:
            cards.append(self._generate_alert_card(alert))

        return f"""
        <div id="section-{severity.value}" class="severity-section">
            <div class="severity-section-header">
                {section_icon}
                <span class="severity-section-title">{severity_korean} 알림</span>
                <span class="severity-section-count">{len(alerts)}건</span>
            </div>
            {''.join(cards)}
        </div>
        """

    RESOURCE_TYPE_KOREAN = {
        "Pod": "파드",
        "Node": "노드",
        "Deployment": "디플로이먼트",
        "Service": "서비스",
        "StatefulSet": "스테이트풀셋",
        "DaemonSet": "데몬셋",
        "Job": "잡",
        "CronJob": "크론잡",
        "PersistentVolume": "퍼시스턴트볼륨",
        "PersistentVolumeClaim": "퍼시스턴트볼륨클레임",
    }

    def _generate_kakao_preview(self, alert: ProcessedAlert) -> str:
        """카카오톡 메시지 미리보기 생성.

        Args:
            alert: ProcessedAlert 객체

        Returns:
            카카오톡 메시지 형식의 문자열
        """
        resource_type_kr = self.RESOURCE_TYPE_KOREAN.get(
            alert.resource_type, alert.resource_type
        )
        severity_kr = self.SEVERITY_KOREAN.get(
            alert.severity.value, alert.severity.value
        )

        # 심각도별 조치 권고 메시지
        action_messages = {
            "critical": "🚨 즉시 확인이 필요합니다.\n서비스 장애 또는 심각한 문제가 발생했습니다.",
            "high": "📢 빠른 확인을 권장합니다.\n성능 저하 또는 안정성 문제가 발생할 수 있습니다.",
            "medium": "📌 모니터링이 필요합니다.\n잠재적인 문제가 감지되었습니다.",
        }
        action_msg = action_messages.get(
            alert.severity.value,
            "📋 확인이 필요합니다."
        )

        # 지속 시간 포맷팅
        duration = alert.duration_minutes
        if duration >= 60:
            duration_text = f"{duration // 60}시간 {duration % 60}분"
        else:
            duration_text = f"{duration}분"

        message = f"""━━━━━━━━━━━━━━━━━━━━
🏷️ 클러스터: {alert.cluster_name}
📍 네임스페이스: {alert.namespace}
🔧 리소스: {resource_type_kr}/{alert.resource_name}
━━━━━━━━━━━━━━━━━━━━

📋 알림 내용:
{alert.description or alert.summary or alert.alert_name}

⚠️ 조치 권고:
{action_msg}

[심각도: {severity_kr} | 지속시간: {duration_text}]"""

        return message

    def _generate_alert_card(self, alert: ProcessedAlert) -> str:
        """알림 카드 생성.

        Args:
            alert: ProcessedAlert 객체

        Returns:
            HTML 카드 문자열
        """
        # Resource icon
        resource_icon_name = self.RESOURCE_TYPE_ICON.get(alert.resource_type, "deployed_code")
        resource_icon = self._icon(resource_icon_name, size="sm", color="muted")

        severity_class = alert.severity.value
        severity_korean = self.SEVERITY_KOREAN.get(alert.severity.value, alert.severity.value)
        severity_config = self.SEVERITY_ICON.get(alert.severity.value, {"icon": "info", "filled": False, "color": "primary"})
        severity_icon = self._icon(
            severity_config["icon"],
            size="sm",
            filled=severity_config["filled"],
            color=severity_config["color"],
        )

        # Icons for meta info
        cluster_icon = self._icon("cloud", size="xs", color="muted")
        namespace_icon = self._icon("folder", size="xs", color="muted")

        # 메타 정보
        meta_items = []
        meta_items.append(f'<span class="alert-card-meta-item">{cluster_icon} {alert.cluster_name}</span>')
        meta_items.append(f'<span class="alert-card-meta-item">{namespace_icon} {alert.namespace}</span>')
        meta_items.append(f'<span class="alert-card-meta-item">{resource_icon} {alert.resource_type}</span>')

        # 시간 정보
        first_seen_str = alert.first_seen.strftime('%Y-%m-%d %H:%M:%S')
        duration_minutes = alert.duration_minutes
        duration_class = "long" if duration_minutes > 15 else "normal"
        duration_text = f"{duration_minutes}분" if duration_minutes < 60 else f"{duration_minutes // 60}시간 {duration_minutes % 60}분"

        # Icons for resource info grid
        label_icon = self._icon("label", size="sm", color="muted")
        schedule_icon = self._icon("schedule", size="xs", color="muted")
        timer_icon = self._icon("timer", size="xs", color="muted")
        repeat_icon = self._icon("repeat", size="xs", color="muted")
        chat_icon = self._icon("chat", size="sm", color="primary")

        # 리소스 정보 그리드
        resource_info_html = f"""
        <div class="resource-info-grid">
            <div class="resource-info-item">
                <span class="resource-info-icon">{cluster_icon}</span>
                <div class="resource-info-content">
                    <span class="resource-info-label">클러스터</span>
                    <span class="resource-info-value">{alert.cluster_name}</span>
                </div>
            </div>
            <div class="resource-info-item">
                <span class="resource-info-icon">{namespace_icon}</span>
                <div class="resource-info-content">
                    <span class="resource-info-label">네임스페이스</span>
                    <span class="resource-info-value">{alert.namespace}</span>
                </div>
            </div>
            <div class="resource-info-item">
                <span class="resource-info-icon">{resource_icon}</span>
                <div class="resource-info-content">
                    <span class="resource-info-label">리소스 타입</span>
                    <span class="resource-info-value">{alert.resource_type}</span>
                </div>
            </div>
            <div class="resource-info-item">
                <span class="resource-info-icon">{label_icon}</span>
                <div class="resource-info-content">
                    <span class="resource-info-label">리소스 이름</span>
                    <span class="resource-info-value">{alert.resource_name}</span>
                </div>
            </div>
        </div>
        """

        # Summary & Description
        summary_html = ""
        if alert.summary:
            summary_html = f"""
            <div class="alert-summary">
                {chat_icon} {alert.summary}
            </div>
            """

        description_html = ""
        if alert.description:
            description_html = f"""
            <div class="alert-description">
                {alert.description}
            </div>
            """

        # Timeline
        timeline_html = f"""
        <div class="alert-timeline">
            <div class="timeline-item">
                <span class="timeline-label">{schedule_icon} 최초 발생</span>
                <span class="timeline-value">{first_seen_str}</span>
            </div>
            <div class="timeline-item">
                <span class="timeline-label">{timer_icon} 지속 시간</span>
                <span class="duration-badge {duration_class}">{duration_text}</span>
            </div>
            <div class="timeline-item">
                <span class="timeline-label">{repeat_icon} 발생 횟수</span>
                <span class="timeline-value">{alert.occurrence_count}회</span>
            </div>
        </div>
        """

        # KakaoTalk Preview (keep emoji for KakaoTalk branding)
        kakao_message = self._generate_kakao_preview(alert)
        kakao_message_escaped = html.escape(kakao_message)
        kakao_preview_html = f"""
        <div class="kakao-preview">
            <div class="kakao-preview-header">
                <span>💬</span>
                <span>카카오톡 알림 미리보기</span>
            </div>
            <div class="kakao-preview-content">
                <pre>{kakao_message_escaped}</pre>
            </div>
        </div>
        """

        # Content title icon
        content_title_icon = self._icon("label", size="sm", color="muted")

        return f"""
        <div class="alert-card {severity_class}">
            <div class="alert-card-header">
                <div class="alert-card-header-left">
                    <div class="alert-card-title">
                        <span class="icon">{severity_icon}</span>
                        {alert.alert_name}
                    </div>
                    <div class="alert-card-meta">
                        {' '.join(meta_items)}
                    </div>
                </div>
                <div class="alert-card-header-right">
                    <span class="severity-badge {severity_class}">
                        {severity_icon} {severity_korean}
                    </span>
                </div>
            </div>
            <div class="alert-content-box">
                <div class="alert-content-header">
                    <span class="alert-content-title">
                        {content_title_icon} {alert.resource_name}
                    </span>
                </div>
                {resource_info_html}
                {summary_html}
                {description_html}
                {timeline_html}
            </div>
            {kakao_preview_html}
        </div>
        """


def generate_alert_report(
    alerts: List[ProcessedAlert],
    output_path: Optional[str] = None,
) -> str:
    """알림 리포트 생성 편의 함수.

    Args:
        alerts: ProcessedAlert 목록
        output_path: 출력 파일 경로 (없으면 HTML 문자열 반환)

    Returns:
        HTML 문자열 또는 파일 경로
    """
    generator = AlertHTMLReportGenerator()
    return generator.generate_report(alerts, output_path)
