"""
HTML Report Generator for Cost Anomaly Scenario Testing.

비용 이상 탐지 시나리오 테스트 결과를 HTML 리포트로 생성합니다.

Features:
- 그룹별 시나리오 구성 (7개 그룹, 34개 시나리오)
- 그룹별 네비게이션 및 통계
- 탐지 방법 비교 행렬
- 카카오톡 알림 미리보기 (실제 발송될 메시지 형태)
- 비용 트렌드 차트 (QuickChart.io)
- 대시보드 통계 (심각도별 분포, 탐지율)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.agents.bdp_cost.services.anomaly_detector import CostDriftResult, Severity
from src.agents.bdp_cost.services.chart_generator import (
    ChartConfig,
    CostTrendChartGenerator,
)
from src.agents.bdp_cost.services.summary_generator import AlertSummary, SummaryGenerator

logger = logging.getLogger(__name__)


@dataclass
class ScenarioResult:
    """시나리오 실행 결과."""

    scenario_id: str
    scenario_name: str
    scenario_name_ko: str
    description_ko: str
    expected_severity: Severity
    detection_result: CostDriftResult
    alert_summary: AlertSummary
    chart_url: Optional[str] = None
    passed: bool = False  # 예상 심각도 일치 여부
    # 그룹 정보
    group_id: str = ""
    group_name: str = ""
    group_name_ko: str = ""
    # 추가 메타데이터
    expected_detection_method: str = ""
    pattern_recognizer: Optional[str] = None


@dataclass
class GroupResult:
    """그룹 실행 결과."""

    id: str
    name: str
    name_ko: str
    description_ko: str
    emoji: str
    scenarios: List[ScenarioResult] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0


class HTMLReportGenerator:
    """
    HTML 리포트 생성기.

    7개 그룹, 34개 시나리오 테스트 결과를 그룹별로 구성된 HTML 리포트로 생성합니다.
    """

    SEVERITY_COLORS = {
        Severity.CRITICAL: "#dc3545",  # Red
        Severity.HIGH: "#fd7e14",  # Orange
        Severity.MEDIUM: "#ffc107",  # Yellow
        Severity.LOW: "#28a745",  # Green
    }

    SEVERITY_BG_COLORS = {
        Severity.CRITICAL: "#f8d7da",
        Severity.HIGH: "#fff3cd",
        Severity.MEDIUM: "#fff3cd",
        Severity.LOW: "#d4edda",
    }

    GROUP_COLORS = {
        "1": "#4f46e5",  # Indigo - Sudden Spike
        "2": "#0ea5e9",  # Sky - Gradual Change
        "3": "#ef4444",  # Red - Cost Reduction
        "4": "#8b5cf6",  # Violet - Cyclic Patterns
        "5": "#10b981",  # Emerald - Service Profile
        "6": "#f59e0b",  # Amber - Edge Cases
        "7": "#6366f1",  # Indigo - Detection Method
    }

    def __init__(self, chart_config: Optional[ChartConfig] = None):
        """리포트 생성기 초기화.

        Args:
            chart_config: 차트 설정 (없으면 기본값 사용)
        """
        self.chart_generator = CostTrendChartGenerator(config=chart_config)
        self.summary_generator = SummaryGenerator(currency="KRW", enable_chart=False)

    def generate_report(
        self,
        scenario_results: List[ScenarioResult],
        output_path: Path = Path("reports/scenario_report.html"),
        groups: Optional[List] = None,
    ) -> Path:
        """HTML 리포트 생성.

        Args:
            scenario_results: 시나리오 실행 결과 목록
            output_path: 출력 파일 경로
            groups: ScenarioGroup 목록 (없으면 결과에서 추출)

        Returns:
            생성된 HTML 파일 경로
        """
        # 그룹별 결과 구성
        group_results = self._organize_by_groups(scenario_results, groups)

        # 통계 계산
        stats = self._calculate_statistics(scenario_results, group_results)

        # HTML 생성
        html_content = self._build_html(scenario_results, group_results, stats)

        # 파일 저장
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content, encoding="utf-8")

        logger.info(f"HTML report generated: {output_path}")
        return output_path

    def _organize_by_groups(
        self,
        results: List[ScenarioResult],
        groups: Optional[List] = None,
    ) -> List[GroupResult]:
        """그룹별 결과 구성.

        Args:
            results: 시나리오 결과 목록
            groups: ScenarioGroup 목록

        Returns:
            GroupResult 목록
        """
        # 그룹 정보 매핑
        group_info = {
            "1": ("Sudden Spike", "급등 패턴", "다양한 크기와 기간의 급격한 비용 상승 패턴을 검증합니다.", "📈"),
            "2": ("Gradual Change", "점진적 변화", "일정 기간에 걸쳐 꾸준히 증가하는 패턴을 검증합니다.", "📊"),
            "3": ("Cost Reduction", "비용 감소", "비용이 급감하는 이상 패턴 (서비스 장애, 삭제 등)을 검증합니다.", "📉"),
            "4": ("Cyclic Patterns", "주기적 패턴", "DayOfWeek, MonthCycle 패턴 인식기를 검증합니다.", "🔄"),
            "5": ("Service Profile", "서비스 프로파일", "spike-normal 서비스 특성 (Lambda, Glue 등)을 검증합니다.", "🎯"),
            "6": ("Edge Cases", "엣지 케이스", "특수 상황 및 경계값 테스트를 수행합니다.", "⚠️"),
            "7": ("Detection Method Comparison", "탐지 방법 비교", "각 탐지 방법(ECOD, Ratio, StdDev)의 특성을 검증합니다.", "🔬"),
        }

        # 그룹별 결과 분류
        group_scenarios: Dict[str, List[ScenarioResult]] = {}
        for r in results:
            gid = r.group_id or r.scenario_id.split("-")[0]
            if gid not in group_scenarios:
                group_scenarios[gid] = []
            group_scenarios[gid].append(r)

        # GroupResult 생성
        group_results = []
        for gid in sorted(group_scenarios.keys()):
            scenarios = group_scenarios[gid]
            info = group_info.get(gid, ("Unknown", "알 수 없음", "", "❓"))

            passed = sum(1 for s in scenarios if s.passed)
            failed = len(scenarios) - passed

            group_results.append(GroupResult(
                id=gid,
                name=info[0],
                name_ko=info[1],
                description_ko=info[2],
                emoji=info[3],
                scenarios=scenarios,
                passed=passed,
                failed=failed,
                pass_rate=(passed / len(scenarios) * 100) if scenarios else 0,
            ))

        return group_results

    def _calculate_statistics(
        self,
        results: List[ScenarioResult],
        group_results: List[GroupResult],
    ) -> dict:
        """통계 계산.

        Args:
            results: 시나리오 결과 목록
            group_results: 그룹 결과 목록

        Returns:
            통계 딕셔너리
        """
        total = len(results)
        passed = sum(1 for r in results if r.passed)

        severity_counts = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 0,
            Severity.MEDIUM: 0,
            Severity.LOW: 0,
        }

        detection_methods = {}
        anomalies_detected = 0

        for r in results:
            severity_counts[r.detection_result.severity] += 1
            method = r.detection_result.detection_method
            detection_methods[method] = detection_methods.get(method, 0) + 1
            if r.detection_result.is_anomaly:
                anomalies_detected += 1

        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
            "severity_counts": severity_counts,
            "detection_methods": detection_methods,
            "anomalies_detected": anomalies_detected,
            "detection_rate": (anomalies_detected / total * 100) if total > 0 else 0,
            "group_count": len(group_results),
            "group_results": group_results,
        }

    def _build_html(
        self,
        results: List[ScenarioResult],
        group_results: List[GroupResult],
        stats: dict,
    ) -> str:
        """HTML 컨텐츠 생성.

        Args:
            results: 시나리오 결과 목록
            group_results: 그룹 결과 목록
            stats: 통계 딕셔너리

        Returns:
            HTML 문자열
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 그룹별 섹션 생성
        group_sections = "\n".join(
            self._build_group_section(g) for g in group_results
        )

        # 그룹 네비게이션 생성
        group_nav = self._build_group_nav(group_results)

        # 탐지 방법 비교 테이블 (그룹 7만)
        detection_matrix = ""
        group_7 = next((g for g in group_results if g.id == "7"), None)
        if group_7:
            detection_matrix = self._build_detection_matrix(group_7.scenarios)

        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BDP Compact - 비용 이상 탐지 시나리오 리포트</title>
    <style>
{self._get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <h1>BDP Compact 비용 이상 탐지 시나리오 리포트</h1>
            <p class="subtitle">{stats['group_count']}개 그룹, {stats['total']}개 시나리오 시뮬레이션 결과</p>
            <p class="timestamp">생성 시간: {timestamp}</p>
        </header>

        <!-- Group Navigation -->
        <nav class="group-nav">
            {group_nav}
        </nav>

        <!-- Dashboard -->
        <section class="dashboard">
            <h2>대시보드</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{stats['total']}</div>
                    <div class="stat-label">전체 시나리오</div>
                </div>
                <div class="stat-card success">
                    <div class="stat-value">{stats['passed']}</div>
                    <div class="stat-label">통과</div>
                </div>
                <div class="stat-card danger">
                    <div class="stat-value">{stats['failed']}</div>
                    <div class="stat-label">실패</div>
                </div>
                <div class="stat-card info">
                    <div class="stat-value">{stats['pass_rate']:.0f}%</div>
                    <div class="stat-label">정확도</div>
                </div>
            </div>

            <div class="stats-grid">
                <div class="stat-card critical">
                    <div class="stat-value">{stats['severity_counts'][Severity.CRITICAL]}</div>
                    <div class="stat-label">CRITICAL</div>
                </div>
                <div class="stat-card high">
                    <div class="stat-value">{stats['severity_counts'][Severity.HIGH]}</div>
                    <div class="stat-label">HIGH</div>
                </div>
                <div class="stat-card medium">
                    <div class="stat-value">{stats['severity_counts'][Severity.MEDIUM]}</div>
                    <div class="stat-label">MEDIUM</div>
                </div>
                <div class="stat-card low">
                    <div class="stat-value">{stats['severity_counts'][Severity.LOW]}</div>
                    <div class="stat-label">LOW</div>
                </div>
            </div>

            <div class="detection-methods">
                <h3>탐지 방법 분포</h3>
                <div class="method-tags">
                    {self._build_method_tags(stats['detection_methods'])}
                </div>
            </div>

            <!-- Group Summary -->
            <div class="group-summary">
                <h3>그룹별 결과</h3>
                <div class="group-summary-grid">
                    {self._build_group_summary(group_results)}
                </div>
            </div>
        </section>

        <!-- Group Sections -->
        {group_sections}

        <!-- Detection Method Comparison Matrix -->
        {detection_matrix}

        <!-- Footer -->
        <footer class="footer">
            <p>BDP Compact Agent - Cost Drift Detection System</p>
            <p>Generated by HTMLReportGenerator</p>
        </footer>
    </div>

    <script>
        // 접이식 카드 토글
        document.querySelectorAll('.scenario-header').forEach(header => {{
            header.addEventListener('click', () => {{
                const card = header.closest('.scenario-card');
                card.classList.toggle('collapsed');
            }});
        }});
    </script>
</body>
</html>"""

    def _build_group_nav(self, group_results: List[GroupResult]) -> str:
        """그룹 네비게이션 생성."""
        links = []
        for g in group_results:
            status_class = "pass" if g.pass_rate >= 70 else "partial" if g.pass_rate >= 50 else "fail"
            links.append(
                f'<a href="#group-{g.id}" class="group-nav-link {status_class}">'
                f'{g.emoji} {g.name_ko} ({g.passed}/{len(g.scenarios)})'
                f'</a>'
            )
        return "\n".join(links)

    def _build_group_summary(self, group_results: List[GroupResult]) -> str:
        """그룹 요약 카드 생성."""
        cards = []
        for g in group_results:
            status_class = "pass" if g.pass_rate >= 70 else "partial" if g.pass_rate >= 50 else "fail"
            color = self.GROUP_COLORS.get(g.id, "#6c757d")
            cards.append(f"""
                <div class="group-summary-card {status_class}" style="border-left-color: {color};">
                    <div class="group-emoji">{g.emoji}</div>
                    <div class="group-info">
                        <div class="group-title">{g.name_ko}</div>
                        <div class="group-stats-inline">
                            <span class="passed">✅ {g.passed}</span>
                            <span class="failed">❌ {g.failed}</span>
                            <span class="rate">{g.pass_rate:.0f}%</span>
                        </div>
                    </div>
                </div>
            """)
        return "\n".join(cards)

    def _build_group_section(self, group: GroupResult) -> str:
        """그룹 섹션 HTML 생성."""
        color = self.GROUP_COLORS.get(group.id, "#6c757d")

        # 시나리오 카드들
        scenario_cards = "\n".join(
            self._build_scenario_card(s) for s in group.scenarios
        )

        return f"""
        <section class="scenario-group" id="group-{group.id}">
            <div class="group-header" style="border-left-color: {color};">
                <h2>{group.emoji} Group {group.id}: {group.name_ko} ({group.name})</h2>
                <div class="group-header-stats">
                    <span class="stat passed">✅ {group.passed} PASS</span>
                    <span class="stat failed">❌ {group.failed} FAIL</span>
                    <span class="stat rate">{group.pass_rate:.0f}%</span>
                </div>
            </div>
            <p class="group-description">{group.description_ko}</p>

            <div class="scenarios-grid">
                {scenario_cards}
            </div>
        </section>
        """

    def _build_scenario_card(self, result: ScenarioResult) -> str:
        """시나리오 카드 HTML 생성.

        Args:
            result: 시나리오 결과

        Returns:
            HTML 문자열
        """
        dr = result.detection_result
        severity_color = self.SEVERITY_COLORS.get(dr.severity, "#6c757d")
        expected_color = self.SEVERITY_COLORS.get(result.expected_severity, "#6c757d")
        pass_class = "pass" if result.passed else "fail"
        pass_text = "PASS" if result.passed else "FAIL"

        # 차트 이미지 (있는 경우)
        chart_html = ""
        if result.chart_url:
            chart_html = f"""
                <div class="chart-container">
                    <img src="{result.chart_url}" alt="비용 추이 차트" loading="lazy">
                </div>"""

        # 패턴 컨텍스트
        pattern_html = ""
        if dr.pattern_contexts:
            patterns = ", ".join(dr.pattern_contexts)
            pattern_html = f"""
                <tr>
                    <th>인식된 패턴</th>
                    <td>{patterns}</td>
                </tr>"""

        # 신뢰도 조정 표시
        confidence_html = f"{dr.confidence_score:.1%}"
        if dr.raw_confidence_score and dr.raw_confidence_score != dr.confidence_score:
            confidence_html = f"{dr.confidence_score:.1%} (원본: {dr.raw_confidence_score:.1%})"

        # 예상 탐지 방법
        expected_method_html = ""
        if result.expected_detection_method:
            expected_method_html = f"""
                <tr>
                    <th>예상 탐지 방법</th>
                    <td>{result.expected_detection_method}</td>
                </tr>"""

        # 패턴 인식기
        pattern_recognizer_html = ""
        if result.pattern_recognizer:
            pattern_recognizer_html = f"""
                <tr>
                    <th>패턴 인식기</th>
                    <td>{result.pattern_recognizer}</td>
                </tr>"""

        return f"""
        <div class="scenario-card">
            <div class="scenario-header">
                <div class="scenario-id">#{result.scenario_id}</div>
                <div class="scenario-title">
                    <h3>{result.scenario_name_ko}</h3>
                    <p class="scenario-service">{dr.service_name}</p>
                </div>
                <div class="scenario-status {pass_class}">{pass_text}</div>
            </div>

            <div class="scenario-description">
                <p>{result.description_ko}</p>
            </div>

            <div class="scenario-content">
                <!-- 입력 데이터 -->
                <div class="data-section">
                    <h4>입력 데이터</h4>
                    <table class="data-table">
                        <tr>
                            <th>서비스</th>
                            <td>{dr.service_name}</td>
                        </tr>
                        <tr>
                            <th>계정</th>
                            <td>{dr.account_name}</td>
                        </tr>
                        <tr>
                            <th>현재 비용</th>
                            <td>{self._format_cost(dr.current_cost)}</td>
                        </tr>
                        <tr>
                            <th>평균 비용</th>
                            <td>{self._format_cost(dr.historical_average)}</td>
                        </tr>
                        <tr>
                            <th>변화율</th>
                            <td class="{'increase' if dr.change_percent > 0 else 'decrease'}">{dr.change_percent:+.1f}%</td>
                        </tr>
                    </table>
                </div>

                <!-- 탐지 결과 -->
                <div class="data-section">
                    <h4>탐지 결과</h4>
                    <table class="data-table">
                        <tr>
                            <th>이상 탐지</th>
                            <td class="{'anomaly' if dr.is_anomaly else 'normal'}">{'이상 탐지됨' if dr.is_anomaly else '정상'}</td>
                        </tr>
                        <tr>
                            <th>실제 심각도</th>
                            <td><span class="severity-badge" style="background-color: {severity_color}">{dr.severity.value.upper()}</span></td>
                        </tr>
                        <tr>
                            <th>예상 심각도</th>
                            <td><span class="severity-badge" style="background-color: {expected_color}">{result.expected_severity.value.upper()}</span></td>
                        </tr>
                        <tr>
                            <th>신뢰도</th>
                            <td>{confidence_html}</td>
                        </tr>
                        <tr>
                            <th>탐지 방법</th>
                            <td>{dr.detection_method}</td>
                        </tr>
                        {expected_method_html}
                        <tr>
                            <th>추세</th>
                            <td>{dr.trend_direction}</td>
                        </tr>
                        <tr>
                            <th>스파이크 기간</th>
                            <td>{dr.spike_duration_days}일</td>
                        </tr>
                        {pattern_html}
                        {pattern_recognizer_html}
                    </table>
                </div>
            </div>

            {chart_html}

            <!-- 카카오톡 미리보기 -->
            <div class="kakao-section">
                <h4>카카오톡 알림 미리보기</h4>
                {self._build_kakao_preview(result)}
            </div>
        </div>"""

    def _build_kakao_preview(self, result: ScenarioResult) -> str:
        """카카오톡 미리보기 HTML 생성.

        Args:
            result: 시나리오 결과

        Returns:
            HTML 문자열
        """
        summary = result.alert_summary
        dr = result.detection_result

        # 차트 이미지 (있는 경우)
        chart_html = ""
        if result.chart_url:
            chart_html = f"""
                <div class="kakao-chart">
                    <img src="{result.chart_url}" alt="비용 추이">
                </div>"""

        return f"""
            <div class="kakao-preview">
                <div class="kakao-bubble">
                    <div class="kakao-title">{summary.title}</div>
                    <div class="kakao-divider"></div>
                    <div class="kakao-content">
                        {summary.message.replace(chr(10), '<br>')}
                    </div>
                    {chart_html}
                </div>
            </div>"""

    def _build_detection_matrix(self, scenarios: List[ScenarioResult]) -> str:
        """탐지 방법 비교 행렬 생성.

        Args:
            scenarios: 그룹 7 시나리오 결과 목록

        Returns:
            HTML 문자열
        """
        rows = []
        for s in scenarios:
            dr = s.detection_result
            method = dr.detection_method

            # 각 방법별 탐지 여부 판단 (단순화된 표시)
            ecod = "✓" if "ecod" in method.lower() else "△" if dr.is_anomaly else "✗"
            ratio = "✓" if "ratio" in method.lower() else "△" if dr.is_anomaly else "✗"
            stddev = "✓" if "stddev" in method.lower() else "△" if dr.is_anomaly else "✗"
            ensemble = "✓" if "ensemble" in method.lower() or dr.is_anomaly else "✗"

            result_class = "pass" if s.passed else "fail"
            result_text = "PASS" if s.passed else "FAIL"

            rows.append(f"""
                <tr>
                    <td>{s.scenario_id}: {s.scenario_name_ko}</td>
                    <td class="{'detected' if ecod == '✓' else 'partial' if ecod == '△' else 'not-detected'}">{ecod}</td>
                    <td class="{'detected' if ratio == '✓' else 'partial' if ratio == '△' else 'not-detected'}">{ratio}</td>
                    <td class="{'detected' if stddev == '✓' else 'partial' if stddev == '△' else 'not-detected'}">{stddev}</td>
                    <td class="{'detected' if ensemble == '✓' else 'partial' if ensemble == '△' else 'not-detected'}">{ensemble}</td>
                    <td class="{result_class}">{result_text}</td>
                </tr>
            """)

        return f"""
        <section class="detection-matrix-section">
            <h2>🔬 탐지 방법 비교 행렬</h2>
            <p class="section-description">Group 7 시나리오에서 각 탐지 방법의 성능을 비교합니다.</p>
            <table class="detection-matrix">
                <thead>
                    <tr>
                        <th>시나리오</th>
                        <th>ECOD</th>
                        <th>Ratio</th>
                        <th>StdDev</th>
                        <th>Ensemble</th>
                        <th>결과</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
            <div class="matrix-legend">
                <span class="legend-item"><span class="detected">✓</span> 주요 탐지</span>
                <span class="legend-item"><span class="partial">△</span> 부분 기여</span>
                <span class="legend-item"><span class="not-detected">✗</span> 미탐지</span>
            </div>
        </section>
        """

    def _build_method_tags(self, methods: dict) -> str:
        """탐지 방법 태그 HTML 생성.

        Args:
            methods: 탐지 방법별 카운트

        Returns:
            HTML 문자열
        """
        tags = []
        for method, count in sorted(methods.items(), key=lambda x: -x[1]):
            tags.append(f'<span class="method-tag">{method}: {count}</span>')
        return " ".join(tags)

    def _format_cost(self, cost: float) -> str:
        """비용 포맷팅.

        Args:
            cost: 비용 값

        Returns:
            포맷팅된 문자열
        """
        if cost >= 100000000:  # 1억 이상
            return f"{cost / 100000000:.1f}억원"
        elif cost >= 10000:  # 1만 이상
            return f"{cost / 10000:.0f}만원"
        else:
            return f"{cost:,.0f}원"

    def _get_css_styles(self) -> str:
        """CSS 스타일 반환."""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        /* Header */
        .header {
            text-align: center;
            padding: 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 10px;
            margin-bottom: 20px;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .header .subtitle {
            font-size: 1.1rem;
            opacity: 0.9;
        }

        .header .timestamp {
            font-size: 0.9rem;
            opacity: 0.8;
            margin-top: 10px;
        }

        /* Group Navigation */
        .group-nav {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            background: white;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            position: sticky;
            top: 10px;
            z-index: 100;
        }

        .group-nav-link {
            padding: 8px 16px;
            border-radius: 20px;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s;
        }

        .group-nav-link.pass {
            background: #d4edda;
            color: #155724;
        }

        .group-nav-link.partial {
            background: #fff3cd;
            color: #856404;
        }

        .group-nav-link.fail {
            background: #f8d7da;
            color: #721c24;
        }

        .group-nav-link:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }

        /* Dashboard */
        .dashboard {
            background: white;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .dashboard h2 {
            margin-bottom: 20px;
            color: #333;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .stat-card {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            border-left: 4px solid #6c757d;
        }

        .stat-card.success { border-left-color: #28a745; }
        .stat-card.danger { border-left-color: #dc3545; }
        .stat-card.info { border-left-color: #17a2b8; }
        .stat-card.critical { border-left-color: #dc3545; }
        .stat-card.high { border-left-color: #fd7e14; }
        .stat-card.medium { border-left-color: #ffc107; }
        .stat-card.low { border-left-color: #28a745; }

        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: #333;
        }

        .stat-label {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }

        .detection-methods h3,
        .group-summary h3 {
            margin-bottom: 10px;
            font-size: 1rem;
            color: #666;
        }

        .method-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .method-tag {
            background: #e9ecef;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.85rem;
            color: #495057;
        }

        /* Group Summary */
        .group-summary {
            margin-top: 20px;
        }

        .group-summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
        }

        .group-summary-card {
            display: flex;
            align-items: center;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #6c757d;
        }

        .group-summary-card.pass { border-left-color: #28a745; }
        .group-summary-card.partial { border-left-color: #ffc107; }
        .group-summary-card.fail { border-left-color: #dc3545; }

        .group-emoji {
            font-size: 1.5rem;
            margin-right: 12px;
        }

        .group-info {
            flex: 1;
        }

        .group-title {
            font-weight: 600;
            font-size: 0.9rem;
        }

        .group-stats-inline {
            display: flex;
            gap: 10px;
            font-size: 0.8rem;
            margin-top: 4px;
        }

        .group-stats-inline .passed { color: #28a745; }
        .group-stats-inline .failed { color: #dc3545; }
        .group-stats-inline .rate { color: #6c757d; font-weight: 600; }

        /* Scenario Groups */
        .scenario-group {
            margin-bottom: 40px;
        }

        .scenario-group .group-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px;
            background: white;
            border-radius: 10px 10px 0 0;
            border-left: 5px solid #667eea;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .scenario-group .group-header h2 {
            font-size: 1.3rem;
            color: #333;
        }

        .group-header-stats {
            display: flex;
            gap: 15px;
            font-weight: 600;
        }

        .group-header-stats .passed { color: #28a745; }
        .group-header-stats .failed { color: #dc3545; }
        .group-header-stats .rate { color: #6c757d; }

        .group-description {
            padding: 15px 20px;
            background: #e3f2fd;
            color: #0d47a1;
            font-size: 0.95rem;
            border-radius: 0 0 10px 10px;
            margin-bottom: 20px;
        }

        .scenarios-grid {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* Scenario Cards */
        .scenario-card {
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .scenario-header {
            display: flex;
            align-items: center;
            padding: 20px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
            cursor: pointer;
        }

        .scenario-id {
            font-size: 1.2rem;
            font-weight: bold;
            color: #6c757d;
            margin-right: 15px;
        }

        .scenario-title {
            flex: 1;
        }

        .scenario-title h3 {
            font-size: 1.1rem;
            color: #333;
        }

        .scenario-service {
            font-size: 0.9rem;
            color: #6c757d;
        }

        .scenario-status {
            padding: 8px 20px;
            border-radius: 5px;
            font-weight: bold;
            font-size: 0.9rem;
        }

        .scenario-status.pass {
            background: #d4edda;
            color: #155724;
        }

        .scenario-status.fail {
            background: #f8d7da;
            color: #721c24;
        }

        .scenario-description {
            padding: 15px 20px;
            background: #fff3cd;
            border-bottom: 1px solid #ffeeba;
        }

        .scenario-description p {
            font-size: 0.95rem;
            color: #856404;
        }

        .scenario-content {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            padding: 20px;
        }

        .data-section h4 {
            font-size: 0.95rem;
            color: #495057;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 2px solid #e9ecef;
        }

        .data-table {
            width: 100%;
            border-collapse: collapse;
        }

        .data-table th,
        .data-table td {
            padding: 8px 10px;
            text-align: left;
            font-size: 0.9rem;
            border-bottom: 1px solid #e9ecef;
        }

        .data-table th {
            color: #6c757d;
            font-weight: 500;
            width: 40%;
        }

        .data-table td.increase {
            color: #dc3545;
            font-weight: 500;
        }

        .data-table td.decrease {
            color: #28a745;
            font-weight: 500;
        }

        .data-table td.anomaly {
            color: #dc3545;
            font-weight: bold;
        }

        .data-table td.normal {
            color: #28a745;
        }

        .severity-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 3px;
            color: white;
            font-size: 0.8rem;
            font-weight: bold;
        }

        /* Chart */
        .chart-container {
            padding: 20px;
            text-align: center;
            background: #f8f9fa;
            border-top: 1px solid #e9ecef;
        }

        .chart-container img {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        /* Kakao Preview */
        .kakao-section {
            padding: 20px;
            background: #f8f9fa;
            border-top: 1px solid #e9ecef;
        }

        .kakao-section h4 {
            font-size: 0.95rem;
            color: #495057;
            margin-bottom: 15px;
        }

        .kakao-preview {
            display: flex;
            justify-content: center;
        }

        .kakao-bubble {
            background: #fee500;
            border-radius: 15px;
            padding: 15px;
            max-width: 350px;
            width: 100%;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }

        .kakao-title {
            font-weight: bold;
            font-size: 0.95rem;
            color: #3c1e1e;
            margin-bottom: 10px;
        }

        .kakao-divider {
            height: 1px;
            background: rgba(60, 30, 30, 0.2);
            margin: 10px 0;
        }

        .kakao-content {
            font-size: 0.9rem;
            color: #3c1e1e;
            line-height: 1.5;
            white-space: pre-wrap;
        }

        .kakao-chart {
            margin-top: 15px;
        }

        .kakao-chart img {
            width: 100%;
            border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }

        /* Detection Matrix */
        .detection-matrix-section {
            background: white;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .detection-matrix-section h2 {
            margin-bottom: 10px;
            color: #333;
        }

        .section-description {
            color: #6c757d;
            font-size: 0.95rem;
            margin-bottom: 20px;
        }

        .detection-matrix {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
        }

        .detection-matrix th,
        .detection-matrix td {
            padding: 12px 15px;
            text-align: center;
            border: 1px solid #e9ecef;
        }

        .detection-matrix th {
            background: #f8f9fa;
            font-weight: 600;
            color: #495057;
        }

        .detection-matrix td:first-child {
            text-align: left;
            font-weight: 500;
        }

        .detection-matrix td.detected {
            background: #d4edda;
            color: #155724;
            font-weight: bold;
        }

        .detection-matrix td.partial {
            background: #fff3cd;
            color: #856404;
        }

        .detection-matrix td.not-detected {
            background: #f8d7da;
            color: #721c24;
        }

        .detection-matrix td.pass {
            background: #28a745;
            color: white;
            font-weight: bold;
        }

        .detection-matrix td.fail {
            background: #dc3545;
            color: white;
            font-weight: bold;
        }

        .matrix-legend {
            display: flex;
            gap: 20px;
            font-size: 0.9rem;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .legend-item .detected { color: #155724; }
        .legend-item .partial { color: #856404; }
        .legend-item .not-detected { color: #721c24; }

        /* Footer */
        .footer {
            text-align: center;
            padding: 30px;
            color: #6c757d;
            font-size: 0.9rem;
        }

        .footer p {
            margin: 5px 0;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.5rem;
            }

            .group-nav {
                position: static;
            }

            .scenario-header {
                flex-direction: column;
                text-align: center;
            }

            .scenario-id {
                margin-right: 0;
                margin-bottom: 10px;
            }

            .scenario-status {
                margin-top: 10px;
            }

            .scenario-content {
                grid-template-columns: 1fr;
            }

            .group-header {
                flex-direction: column;
                gap: 10px;
            }
        }
"""


def generate_scenario_report(
    scenario_results: List[ScenarioResult],
    output_path: str = "reports/scenario_report.html",
    groups: Optional[List] = None,
) -> Path:
    """편의 함수: 시나리오 리포트 생성.

    Args:
        scenario_results: 시나리오 실행 결과 목록
        output_path: 출력 파일 경로
        groups: ScenarioGroup 목록

    Returns:
        생성된 HTML 파일 경로
    """
    generator = HTMLReportGenerator()
    return generator.generate_report(scenario_results, Path(output_path), groups)
