"""
Report Styles (Common).

HTML 리포트 공통 스타일 및 색상 상수.
"""

from dataclasses import dataclass
from typing import Dict


# Severity 색상
SEVERITY_COLORS: Dict[str, Dict[str, str]] = {
    "critical": {
        "bg": "#fee2e2",
        "border": "#ef4444",
        "text": "#991b1b",
        "emoji": "🚨",
    },
    "high": {
        "bg": "#fef3c7",
        "border": "#f59e0b",
        "text": "#92400e",
        "emoji": "⚠️",
    },
    "medium": {
        "bg": "#dbeafe",
        "border": "#3b82f6",
        "text": "#1e40af",
        "emoji": "📊",
    },
    "low": {
        "bg": "#f3f4f6",
        "border": "#9ca3af",
        "text": "#4b5563",
        "emoji": "ℹ️",
    },
}


@dataclass
class ReportStyles:
    """리포트 CSS 스타일."""

    # 기본 색상
    primary_color: str = "#3b82f6"
    secondary_color: str = "#6b7280"
    success_color: str = "#10b981"
    warning_color: str = "#f59e0b"
    danger_color: str = "#ef4444"
    info_color: str = "#3b82f6"

    # 배경 색상
    bg_color: str = "#f9fafb"
    card_bg_color: str = "#ffffff"

    # 텍스트 색상
    text_color: str = "#111827"
    text_muted: str = "#6b7280"

    # 테두리
    border_color: str = "#e5e7eb"
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
        """심각도 배지 HTML 반환."""
        severity_lower = severity.lower()
        emoji = SEVERITY_COLORS.get(severity_lower, {}).get("emoji", "📊")
        return f'<span class="badge badge-{severity_lower}">{emoji} {severity.upper()}</span>'
