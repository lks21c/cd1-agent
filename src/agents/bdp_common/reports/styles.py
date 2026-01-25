"""
Report Styles (Common).

HTML 리포트 공통 스타일 및 색상 상수.
Material Design 3 기반 디자인 시스템.
"""

from dataclasses import dataclass
from typing import Dict


# =============================================================================
# Material Design 3 Color Palette (12색 제한)
# =============================================================================
MD3_COLORS: Dict[str, str] = {
    # Primary
    "primary": "#1976D2",
    "primary_container": "#E3F2FD",
    "on_primary": "#FFFFFF",
    "on_primary_container": "#1565C0",

    # Semantic - Error
    "error": "#D32F2F",
    "error_container": "#FFEBEE",
    "on_error": "#FFFFFF",
    "on_error_container": "#B71C1C",

    # Semantic - Warning
    "warning": "#F57C00",
    "warning_container": "#FFF3E0",
    "on_warning_container": "#E65100",

    # Semantic - Success
    "success": "#388E3C",
    "success_container": "#E8F5E9",
    "on_success_container": "#1B5E20",

    # Neutral
    "surface": "#FFFFFF",
    "surface_variant": "#F5F5F5",
    "on_surface": "#212121",
    "on_surface_variant": "#757575",
    "outline": "#BDBDBD",
    "outline_variant": "#E0E0E0",
}


# =============================================================================
# Material Symbols 아이콘 매핑
# =============================================================================
MATERIAL_ICONS: Dict[str, Dict[str, str]] = {
    # Resource Types (AWS)
    "resource": {
        "glue": "folder_data",
        "athena": "query_stats",
        "emr": "bolt",
        "sagemaker": "smart_toy",
        "s3": "inventory_2",
        "mwaa": "air",
        "msk": "stream",
        "lambda": "function",
        "default": "cloud",
        # K8s Resources
        "pod": "deployed_code",
        "node": "dns",
        "service": "hub",
        "deployment": "rocket_launch",
        "statefulset": "database",
        "daemonset": "dynamic_feed",
        "job": "task_alt",
        "cronjob": "schedule",
        "persistentvolume": "hard_drive",
        "persistentvolumeclaim": "sd_card",
    },
    # Severity
    "severity": {
        "critical": "error",
        "high": "warning",
        "medium": "info",
        "low": "check_circle",
    },
    # Status/Meta
    "status": {
        "enabled": "check_circle",
        "disabled": "cancel",
        "null": "remove",
        "increase": "trending_up",
        "decrease": "trending_down",
    },
    # UI Elements
    "ui": {
        "settings": "settings",
        "recommendation": "lightbulb",
        "impact": "priority_high",
        "version": "history",
        "account": "business",
        "time": "schedule",
        "navigation": "near_me",
        "monitoring": "monitoring",
        "discovered": "search",
        "dashboard": "dashboard",
        "baseline": "description",
        "current": "description",
        "change": "swap_horiz",
        "chart": "show_chart",
        "timeline": "timeline",
        # K8s/HDSP UI Elements
        "cluster": "cloud",
        "namespace": "folder",
        "label": "label",
        "duration": "timer",
        "summary": "summarize",
        "message": "chat",
        "occurrence": "repeat",
        "first_seen": "schedule",
        "check": "check_circle",
        "alert": "notifications",
    },
}


# =============================================================================
# Severity 색상 및 아이콘 (MD3 기반)
# =============================================================================
SEVERITY_COLORS: Dict[str, Dict[str, str]] = {
    "critical": {
        "bg": MD3_COLORS["error_container"],
        "border": MD3_COLORS["error"],
        "text": MD3_COLORS["on_error_container"],
        "icon": "error",
        "icon_filled": True,
    },
    "high": {
        "bg": MD3_COLORS["warning_container"],
        "border": MD3_COLORS["warning"],
        "text": MD3_COLORS["on_warning_container"],
        "icon": "warning",
        "icon_filled": True,
    },
    "medium": {
        "bg": MD3_COLORS["primary_container"],
        "border": MD3_COLORS["primary"],
        "text": MD3_COLORS["on_primary_container"],
        "icon": "info",
        "icon_filled": False,
    },
    "low": {
        "bg": MD3_COLORS["surface_variant"],
        "border": MD3_COLORS["outline"],
        "text": MD3_COLORS["on_surface_variant"],
        "icon": "check_circle",
        "icon_filled": False,
    },
}


@dataclass
class ReportStyles:
    """리포트 CSS 스타일 (MD3 기반)."""

    # 기본 색상 (MD3 Palette)
    primary_color: str = MD3_COLORS["primary"]
    secondary_color: str = MD3_COLORS["on_surface_variant"]
    success_color: str = MD3_COLORS["success"]
    warning_color: str = MD3_COLORS["warning"]
    danger_color: str = MD3_COLORS["error"]
    info_color: str = MD3_COLORS["primary"]

    # 배경 색상
    bg_color: str = MD3_COLORS["surface_variant"]
    card_bg_color: str = MD3_COLORS["surface"]

    # 텍스트 색상
    text_color: str = MD3_COLORS["on_surface"]
    text_muted: str = MD3_COLORS["on_surface_variant"]

    # 테두리
    border_color: str = MD3_COLORS["outline_variant"]
    border_radius: str = "8px"

    # 폰트
    font_family: str = "'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

    def get_base_css(self) -> str:
        """기본 CSS 스타일 반환."""
        return f"""
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: {self.font_family};
            background-color: {self.bg_color};
            color: {self.text_color};
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}

        .card {{
            background: {self.card_bg_color};
            border-radius: {self.border_radius};
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
            padding: 20px;
        }}

        .card-header {{
            border-bottom: 1px solid {self.border_color};
            padding-bottom: 12px;
            margin-bottom: 16px;
        }}

        .card-title {{
            font-size: 18px;
            font-weight: 600;
            color: {self.text_color};
        }}

        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }}

        .badge-critical {{
            background: {SEVERITY_COLORS['critical']['bg']};
            color: {SEVERITY_COLORS['critical']['text']};
            border: 1px solid {SEVERITY_COLORS['critical']['border']};
        }}

        .badge-high {{
            background: {SEVERITY_COLORS['high']['bg']};
            color: {SEVERITY_COLORS['high']['text']};
            border: 1px solid {SEVERITY_COLORS['high']['border']};
        }}

        .badge-medium {{
            background: {SEVERITY_COLORS['medium']['bg']};
            color: {SEVERITY_COLORS['medium']['text']};
            border: 1px solid {SEVERITY_COLORS['medium']['border']};
        }}

        .badge-low {{
            background: {SEVERITY_COLORS['low']['bg']};
            color: {SEVERITY_COLORS['low']['text']};
            border: 1px solid {SEVERITY_COLORS['low']['border']};
        }}

        .table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .table th,
        .table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid {self.border_color};
        }}

        .table th {{
            background: {self.bg_color};
            font-weight: 600;
        }}

        .table tr:hover {{
            background: {self.bg_color};
        }}

        .stat-card {{
            text-align: center;
            padding: 20px;
        }}

        .stat-value {{
            font-size: 32px;
            font-weight: 700;
            color: {self.primary_color};
        }}

        .stat-label {{
            font-size: 14px;
            color: {self.text_muted};
            margin-top: 4px;
        }}

        .grid {{
            display: grid;
            gap: 20px;
        }}

        .grid-2 {{
            grid-template-columns: repeat(2, 1fr);
        }}

        .grid-3 {{
            grid-template-columns: repeat(3, 1fr);
        }}

        .grid-4 {{
            grid-template-columns: repeat(4, 1fr);
        }}

        @media (max-width: 768px) {{
            .grid-2, .grid-3, .grid-4 {{
                grid-template-columns: 1fr;
            }}
        }}

        .diff-added {{
            background: #dcfce7;
            color: #166534;
        }}

        .diff-removed {{
            background: #fee2e2;
            color: #991b1b;
        }}

        .diff-changed {{
            background: #fef3c7;
            color: #92400e;
        }}

        .code-block {{
            background: #1f2937;
            color: #f9fafb;
            padding: 16px;
            border-radius: {self.border_radius};
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
            overflow-x: auto;
        }}

        .nav {{
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}

        .nav-item {{
            padding: 8px 16px;
            background: {self.card_bg_color};
            border: 1px solid {self.border_color};
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .nav-item:hover {{
            background: {self.bg_color};
        }}

        .nav-item.active {{
            background: {self.primary_color};
            color: white;
            border-color: {self.primary_color};
        }}

        .header {{
            background: {self.card_bg_color};
            padding: 24px;
            border-bottom: 1px solid {self.border_color};
            margin-bottom: 24px;
        }}

        .header-title {{
            font-size: 24px;
            font-weight: 700;
        }}

        .header-subtitle {{
            font-size: 14px;
            color: {self.text_muted};
            margin-top: 4px;
        }}

        .alert {{
            padding: 16px;
            border-radius: {self.border_radius};
            margin-bottom: 16px;
        }}

        .alert-info {{
            background: #dbeafe;
            border: 1px solid #3b82f6;
            color: #1e40af;
        }}

        .alert-warning {{
            background: #fef3c7;
            border: 1px solid #f59e0b;
            color: #92400e;
        }}

        .alert-danger {{
            background: #fee2e2;
            border: 1px solid #ef4444;
            color: #991b1b;
        }}

        .alert-success {{
            background: #dcfce7;
            border: 1px solid #10b981;
            color: #166534;
        }}
        """

    def get_severity_badge(self, severity: str) -> str:
        """심각도 배지 HTML 반환 (Material Icon 사용)."""
        severity_lower = severity.lower()
        severity_config = SEVERITY_COLORS.get(severity_lower, SEVERITY_COLORS["medium"])
        icon_name = severity_config.get("icon", "info")
        is_filled = severity_config.get("icon_filled", False)
        fill_class = " icon-filled" if is_filled else ""
        return f'<span class="badge badge-{severity_lower}"><span class="material-symbols-outlined icon-sm{fill_class}">{icon_name}</span> {severity.upper()}</span>'


def get_material_icon(category: str, key: str, fallback: str = "help") -> str:
    """Material Symbol 아이콘 이름 조회.

    Args:
        category: 아이콘 카테고리 (resource, severity, status, ui)
        key: 아이콘 키
        fallback: 기본값

    Returns:
        Material Symbol 이름
    """
    return MATERIAL_ICONS.get(category, {}).get(key, fallback)
