"""
HTML Report Base (Common).

HTML 리포트 공통 베이스 클래스.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agents.bdp_common.reports.styles import (
    ReportStyles,
    SEVERITY_COLORS,
    MD3_COLORS,
    MATERIAL_ICONS,
    get_material_icon,
)

logger = logging.getLogger(__name__)


class HTMLReportBase(ABC):
    """
    HTML 리포트 베이스 클래스.

    공통 스타일 및 레이아웃 제공.
    각 에이전트에서 상속하여 도메인별 리포트 구현.
    """

    def __init__(
        self,
        title: str = "Report",
        styles: Optional[ReportStyles] = None,
    ):
        """리포트 베이스 초기화.

        Args:
            title: 리포트 제목
            styles: 스타일 설정
        """
        self.title = title
        self.styles = styles or ReportStyles()

    @abstractmethod
    def generate_content(self, data: Any) -> str:
        """리포트 콘텐츠 생성 (서브클래스에서 구현).

        Args:
            data: 리포트 데이터

        Returns:
            HTML 콘텐츠
        """
        pass

    def generate_report(
        self,
        data: Any,
        output_path: Optional[str] = None,
    ) -> str:
        """전체 HTML 리포트 생성.

        Args:
            data: 리포트 데이터
            output_path: 출력 파일 경로 (없으면 HTML 문자열 반환)

        Returns:
            HTML 문자열 또는 파일 경로
        """
        content = self.generate_content(data)
        html = self._wrap_html(content)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"Report saved to: {output_path}")
            return output_path

        return html

    def _wrap_html(self, content: str) -> str:
        """HTML 래퍼 생성.

        Args:
            content: 내부 콘텐츠

        Returns:
            완성된 HTML
        """
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

    def _get_icon_css(self) -> str:
        """Material Symbols 아이콘 유틸리티 CSS 반환."""
        return f"""
        /* =========================================================
           Material Symbols Icon Utilities
           ========================================================= */
        .material-symbols-outlined {{
            font-family: 'Material Symbols Outlined';
            font-weight: normal;
            font-style: normal;
            font-size: 24px;
            line-height: 1;
            letter-spacing: normal;
            text-transform: none;
            display: inline-block;
            white-space: nowrap;
            word-wrap: normal;
            direction: ltr;
            -webkit-font-feature-settings: 'liga';
            -webkit-font-smoothing: antialiased;
            vertical-align: middle;
        }}

        /* Icon Sizes */
        .icon-xs {{ font-size: 14px; }}
        .icon-sm {{ font-size: 18px; }}
        .icon-md {{ font-size: 24px; }}
        .icon-lg {{ font-size: 32px; }}
        .icon-xl {{ font-size: 48px; }}

        /* Icon Filled Style */
        .icon-filled {{
            font-variation-settings: 'FILL' 1;
        }}

        /* Icon Colors (MD3 Semantic) */
        .icon-error {{ color: {MD3_COLORS['error']}; }}
        .icon-warning {{ color: {MD3_COLORS['warning']}; }}
        .icon-success {{ color: {MD3_COLORS['success']}; }}
        .icon-primary {{ color: {MD3_COLORS['primary']}; }}
        .icon-muted {{ color: {MD3_COLORS['on_surface_variant']}; }}
        .icon-on-surface {{ color: {MD3_COLORS['on_surface']}; }}

        /* Icon with text alignment helper */
        .icon-inline {{
            vertical-align: -0.125em;
            margin-right: 4px;
        }}
        """

    def _icon(
        self,
        name: str,
        size: str = "md",
        filled: bool = False,
        color: str = "",
        inline: bool = False,
    ) -> str:
        """Material Symbol 아이콘 렌더링.

        Args:
            name: 아이콘 이름 (e.g., 'error', 'check_circle')
            size: 크기 (xs, sm, md, lg, xl)
            filled: filled 스타일 여부
            color: 색상 클래스 (error, warning, success, primary, muted)
            inline: 텍스트와 인라인 정렬 여부

        Returns:
            HTML 아이콘 문자열
        """
        classes = ["material-symbols-outlined", f"icon-{size}"]
        if filled:
            classes.append("icon-filled")
        if color:
            classes.append(f"icon-{color}")
        if inline:
            classes.append("icon-inline")
        return f'<span class="{" ".join(classes)}">{name}</span>'

    def render_card(
        self,
        title: str,
        content: str,
        header_extra: str = "",
    ) -> str:
        """카드 컴포넌트 렌더링.

        Args:
            title: 카드 제목
            content: 카드 내용
            header_extra: 헤더 추가 요소 (배지 등)

        Returns:
            HTML 문자열
        """
        return f"""
        <div class="card">
            <div class="card-header">
                <span class="card-title">{title}</span>
                {header_extra}
            </div>
            {content}
        </div>
        """

    def render_stat_cards(
        self,
        stats: List[Dict[str, Any]],
        columns: int = 4,
    ) -> str:
        """통계 카드 그리드 렌더링.

        Args:
            stats: [{"label": "...", "value": "...", "color": "..."}, ...]
            columns: 열 개수

        Returns:
            HTML 문자열
        """
        cards = []
        for stat in stats:
            color = stat.get("color", self.styles.primary_color)
            cards.append(f"""
            <div class="card stat-card">
                <div class="stat-value" style="color: {color};">{stat['value']}</div>
                <div class="stat-label">{stat['label']}</div>
            </div>
            """)

        return f"""
        <div class="grid grid-{columns}">
            {''.join(cards)}
        </div>
        """

    def render_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        highlight_column: Optional[int] = None,
    ) -> str:
        """테이블 렌더링.

        Args:
            headers: 헤더 목록
            rows: 행 데이터
            highlight_column: 강조할 열 인덱스

        Returns:
            HTML 문자열
        """
        header_html = "".join(f"<th>{h}</th>" for h in headers)

        row_html = []
        for row in rows:
            cells = []
            for i, cell in enumerate(row):
                if highlight_column is not None and i == highlight_column:
                    cells.append(f"<td><strong>{cell}</strong></td>")
                else:
                    cells.append(f"<td>{cell}</td>")
            row_html.append(f"<tr>{''.join(cells)}</tr>")

        return f"""
        <table class="table">
            <thead>
                <tr>{header_html}</tr>
            </thead>
            <tbody>
                {''.join(row_html)}
            </tbody>
        </table>
        """

    def render_severity_badge(self, severity: str) -> str:
        """심각도 배지 렌더링.

        Args:
            severity: 심각도 (critical, high, medium, low)

        Returns:
            HTML 문자열
        """
        return self.styles.get_severity_badge(severity)

    def render_diff(
        self,
        old_value: Any,
        new_value: Any,
        label: str = "",
    ) -> str:
        """변경 사항 diff 렌더링.

        Args:
            old_value: 이전 값
            new_value: 새 값
            label: 필드 레이블

        Returns:
            HTML 문자열
        """
        label_html = f"<strong>{label}:</strong> " if label else ""

        return f"""
        <div style="margin: 8px 0;">
            {label_html}
            <span class="diff-removed" style="padding: 2px 4px; text-decoration: line-through;">
                {old_value}
            </span>
            →
            <span class="diff-added" style="padding: 2px 4px;">
                {new_value}
            </span>
        </div>
        """

    def render_code_block(
        self,
        code: str,
        language: str = "",
    ) -> str:
        """코드 블록 렌더링.

        Args:
            code: 코드 문자열
            language: 언어 (표시용)

        Returns:
            HTML 문자열
        """
        lang_label = f"<div style='color: #9ca3af; margin-bottom: 8px;'>{language}</div>" if language else ""

        return f"""
        <div class="code-block">
            {lang_label}
            <pre>{code}</pre>
        </div>
        """

    def render_alert(
        self,
        message: str,
        alert_type: str = "info",
    ) -> str:
        """알림 박스 렌더링.

        Args:
            message: 메시지
            alert_type: 타입 (info, warning, danger, success)

        Returns:
            HTML 문자열
        """
        return f"""
        <div class="alert alert-{alert_type}">
            {message}
        </div>
        """

    def render_nav(
        self,
        items: List[Dict[str, str]],
    ) -> str:
        """네비게이션 렌더링.

        Args:
            items: [{"label": "...", "href": "...", "active": True/False}, ...]

        Returns:
            HTML 문자열
        """
        nav_items = []
        for item in items:
            active_class = " active" if item.get("active") else ""
            nav_items.append(
                f'<a href="{item["href"]}" class="nav-item{active_class}">'
                f'{item["label"]}</a>'
            )

        return f"""
        <nav class="nav">
            {''.join(nav_items)}
        </nav>
        """
