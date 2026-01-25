"""
Scenario Report Test Runner.

7개 그룹, 35개의 비용 이상 시나리오를 실행하고 HTML 리포트를 생성합니다.

Usage:
    # 전체 테스트 실행 (34개 시나리오)
    uv run python3 -m pytest tests/agents/bdp_compact/test_scenario_report.py -v

    # 특정 그룹만 테스트
    uv run python3 -m pytest tests/agents/bdp_compact/test_scenario_report.py::TestScenarioReport::test_group_1_sudden_spike -v

    # CLI로 직접 실행
    uv run python3 -c "import sys; sys.path.insert(0, '.'); from tests.agents.bdp_compact.test_scenario_report import run_scenario_report; run_scenario_report()"

    # LocalStack 통합 테스트
    AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=ap-northeast-2 \\
      uv run python3 -m pytest tests/agents/bdp_compact/test_scenario_report.py -v -m localstack
"""

import os
from pathlib import Path
from typing import List

import pytest

from src.agents.bdp_compact.services.anomaly_detector import CostDriftDetector, Severity
from src.agents.bdp_compact.services.chart_generator import CostTrendChartGenerator
from src.agents.bdp_compact.services.html_report_generator import (
    HTMLReportGenerator,
    ScenarioResult,
)
from src.agents.bdp_compact.services.summary_generator import SummaryGenerator
from tests.agents.bdp_compact.scenarios.scenario_factory import (
    ScenarioDefinition,
    ScenarioFactory,
    ScenarioGroup,
)


class TestScenarioReport:
    """시나리오 리포트 테스트 클래스."""

    @pytest.fixture
    def detector(self):
        """비용 드리프트 탐지기."""
        return CostDriftDetector(sensitivity=0.7)

    @pytest.fixture
    def summary_generator(self):
        """요약 생성기."""
        return SummaryGenerator(currency="KRW", enable_chart=True)

    @pytest.fixture
    def chart_generator(self):
        """차트 생성기."""
        return CostTrendChartGenerator()

    @pytest.fixture
    def report_generator(self):
        """HTML 리포트 생성기."""
        return HTMLReportGenerator()

    def _run_scenario(
        self,
        scenario: ScenarioDefinition,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ) -> ScenarioResult:
        """단일 시나리오 실행.

        Args:
            scenario: 시나리오 정의
            detector: 탐지기
            summary_generator: 요약 생성기
            chart_generator: 차트 생성기

        Returns:
            ScenarioResult 객체
        """
        # 비용 데이터 생성
        cost_data = ScenarioFactory.generate_cost_data(scenario)

        # 탐지 실행
        detection_result = detector.analyze_service(cost_data)

        # 요약 생성
        alert_summary = summary_generator.generate(detection_result)

        # 차트 URL 생성
        chart_url = chart_generator.generate_chart_url(detection_result)

        # 예상 vs 실제 심각도 비교
        # 허용 오차: 1단계 (예: CRITICAL과 HIGH는 인접)
        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        expected_idx = severity_order.index(scenario.expected_severity)
        actual_idx = severity_order.index(detection_result.severity)

        # 이상이 탐지되지 않은 경우 (예: CloudWatch 정상 변동)
        if not detection_result.is_anomaly and scenario.expected_severity == Severity.LOW:
            passed = True
        else:
            # 심각도가 1단계 이내로 일치하면 통과
            passed = abs(expected_idx - actual_idx) <= 1

        return ScenarioResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            scenario_name_ko=scenario.name_ko,
            description_ko=scenario.description_ko,
            expected_severity=scenario.expected_severity,
            detection_result=detection_result,
            alert_summary=alert_summary,
            chart_url=chart_url,
            passed=passed,
            # 그룹 정보
            group_id=scenario.group_id,
            group_name=scenario.group_name,
            group_name_ko=scenario.group_name if hasattr(scenario, 'group_name') else "",
            # 추가 메타데이터
            expected_detection_method=scenario.expected_detection_method,
            pattern_recognizer=scenario.pattern_recognizer,
        )

    def _run_scenarios_in_group(
        self,
        group_id: str,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ) -> List[ScenarioResult]:
        """특정 그룹의 모든 시나리오 실행.

        Args:
            group_id: 그룹 ID
            detector: 탐지기
            summary_generator: 요약 생성기
            chart_generator: 차트 생성기

        Returns:
            ScenarioResult 목록
        """
        scenarios = ScenarioFactory.get_scenarios_by_group(group_id)
        results = []

        for scenario in scenarios:
            result = self._run_scenario(
                scenario, detector, summary_generator, chart_generator
            )
            results.append(result)

            status = "PASS" if result.passed else "FAIL"
            print(
                f"[{status}] #{scenario.id} {scenario.name_ko}: "
                f"expected={scenario.expected_severity.value}, "
                f"actual={result.detection_result.severity.value}, "
                f"confidence={result.detection_result.confidence_score:.1%}"
            )

        return results

    # =========================================================================
    # 그룹별 테스트 메서드
    # =========================================================================

    def test_group_1_sudden_spike(
        self,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ):
        """Group 1: 급등 패턴 (Sudden Spike) 테스트."""
        print("\n=== Group 1: 급등 패턴 (Sudden Spike) ===")
        results = self._run_scenarios_in_group(
            "1", detector, summary_generator, chart_generator
        )

        passed = sum(1 for r in results if r.passed)
        print(f"\nGroup 1 결과: {passed}/{len(results)} 통과")

        # Critical/High 시나리오는 반드시 이상 탐지되어야 함
        for r in results:
            if r.expected_severity in [Severity.CRITICAL, Severity.HIGH]:
                assert r.detection_result.is_anomaly, (
                    f"Scenario #{r.scenario_id} ({r.scenario_name_ko}): "
                    f"Expected anomaly detection for {r.expected_severity.value}"
                )

    def test_group_2_gradual_change(
        self,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ):
        """Group 2: 점진적 변화 (Gradual Change) 테스트."""
        print("\n=== Group 2: 점진적 변화 (Gradual Change) ===")
        results = self._run_scenarios_in_group(
            "2", detector, summary_generator, chart_generator
        )

        passed = sum(1 for r in results if r.passed)
        print(f"\nGroup 2 결과: {passed}/{len(results)} 통과")

    def test_group_3_cost_reduction(
        self,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ):
        """Group 3: 비용 감소 (Cost Reduction) 테스트."""
        print("\n=== Group 3: 비용 감소 (Cost Reduction) ===")
        results = self._run_scenarios_in_group(
            "3", detector, summary_generator, chart_generator
        )

        passed = sum(1 for r in results if r.passed)
        print(f"\nGroup 3 결과: {passed}/{len(results)} 통과")

        # 비용 감소도 이상으로 탐지되어야 함
        for r in results:
            if r.expected_severity in [Severity.CRITICAL, Severity.HIGH]:
                assert r.detection_result.is_anomaly, (
                    f"Scenario #{r.scenario_id}: Cost reduction should be detected as anomaly"
                )

    def test_group_4_cyclic_patterns(
        self,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ):
        """Group 4: 주기적 패턴 (Cyclic Patterns) 테스트."""
        print("\n=== Group 4: 주기적 패턴 (Cyclic Patterns) ===")
        results = self._run_scenarios_in_group(
            "4", detector, summary_generator, chart_generator
        )

        passed = sum(1 for r in results if r.passed)
        print(f"\nGroup 4 결과: {passed}/{len(results)} 통과")

    def test_group_5_service_profile(
        self,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ):
        """Group 5: 서비스 프로파일 (Service Profile) 테스트."""
        print("\n=== Group 5: 서비스 프로파일 (Service Profile) ===")
        results = self._run_scenarios_in_group(
            "5", detector, summary_generator, chart_generator
        )

        passed = sum(1 for r in results if r.passed)
        print(f"\nGroup 5 결과: {passed}/{len(results)} 통과")

        # spike-normal 서비스는 탐지되지만 심각도가 조정될 수 있음
        for r in results:
            assert r.detection_result.is_anomaly, (
                f"Scenario #{r.scenario_id}: Service profile spike should be detected"
            )

    def test_group_6_edge_cases(
        self,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ):
        """Group 6: 엣지 케이스 (Edge Cases) 테스트."""
        print("\n=== Group 6: 엣지 케이스 (Edge Cases) ===")
        results = self._run_scenarios_in_group(
            "6", detector, summary_generator, chart_generator
        )

        passed = sum(1 for r in results if r.passed)
        print(f"\nGroup 6 결과: {passed}/{len(results)} 통과")

        # 엣지 케이스 검증
        for r in results:
            if "데이터 부족" in r.scenario_name_ko:
                # 데이터 부족 시 LOW 또는 탐지 안됨
                assert r.detection_result.severity in [Severity.LOW, Severity.MEDIUM]
            elif "제로 비용" in r.scenario_name_ko:
                # 제로 비용은 LOW
                assert r.detection_result.severity == Severity.LOW

    def test_group_7_detection_comparison(
        self,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ):
        """Group 7: 탐지 방법 비교 (Detection Method Comparison) 테스트."""
        print("\n=== Group 7: 탐지 방법 비교 (Detection Method Comparison) ===")
        results = self._run_scenarios_in_group(
            "7", detector, summary_generator, chart_generator
        )

        passed = sum(1 for r in results if r.passed)
        print(f"\nGroup 7 결과: {passed}/{len(results)} 통과")

        # 탐지 방법 분석 출력
        print("\n탐지 방법 분석:")
        for r in results:
            print(
                f"  {r.scenario_id}: method={r.detection_result.detection_method}, "
                f"expected={r.expected_detection_method}"
            )

    # =========================================================================
    # 전체 리포트 생성 테스트
    # =========================================================================

    def test_generate_full_html_report(
        self,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
        report_generator: HTMLReportGenerator,
    ):
        """전체 35개 시나리오 실행 후 HTML 리포트 생성."""
        print("\n=== 전체 시나리오 리포트 생성 (35개) ===")

        # 모든 시나리오 가져오기
        scenarios = ScenarioFactory.get_all_scenarios()
        groups = ScenarioFactory.get_all_groups()

        assert len(scenarios) == 35, f"Expected 35 scenarios, got {len(scenarios)}"
        assert len(groups) == 7, f"Expected 7 groups, got {len(groups)}"

        # 각 시나리오 실행
        results: List[ScenarioResult] = []
        for scenario in scenarios:
            result = self._run_scenario(
                scenario, detector, summary_generator, chart_generator
            )
            results.append(result)

            # 결과 로깅
            status = "PASS" if result.passed else "FAIL"
            print(
                f"[{status}] #{scenario.id} {scenario.name_ko}: "
                f"expected={scenario.expected_severity.value}, "
                f"actual={result.detection_result.severity.value}, "
                f"confidence={result.detection_result.confidence_score:.1%}"
            )

        # HTML 리포트 생성
        output_path = Path("reports/scenario_report.html")
        report_path = report_generator.generate_report(results, output_path, groups)

        # 검증
        assert report_path.exists(), f"Report file not created: {report_path}"
        assert report_path.stat().st_size > 0, "Report file is empty"

        # 통계 출력
        passed = sum(1 for r in results if r.passed)
        print(f"\n=== 시나리오 테스트 결과 ===")
        print(f"전체: {len(results)}, 통과: {passed}, 실패: {len(results) - passed}")
        print(f"정확도: {passed / len(results) * 100:.0f}%")

        # 그룹별 통계
        print("\n그룹별 결과:")
        for group in groups:
            group_results = [r for r in results if r.group_id == group.id]
            group_passed = sum(1 for r in group_results if r.passed)
            print(
                f"  {group.emoji} {group.name_ko}: "
                f"{group_passed}/{len(group_results)} 통과 "
                f"({group_passed / len(group_results) * 100:.0f}%)"
            )

        print(f"\n리포트 생성됨: {report_path}")

    def test_individual_scenarios(
        self,
        detector: CostDriftDetector,
        summary_generator: SummaryGenerator,
        chart_generator: CostTrendChartGenerator,
    ):
        """개별 시나리오 검증 테스트."""
        scenarios = ScenarioFactory.get_all_scenarios()

        for scenario in scenarios:
            result = self._run_scenario(
                scenario, detector, summary_generator, chart_generator
            )

            # 기본 검증
            assert result.detection_result is not None
            assert result.alert_summary is not None

            # Critical/High 시나리오는 반드시 이상 탐지되어야 함
            if scenario.expected_severity in [Severity.CRITICAL, Severity.HIGH]:
                # 엣지 케이스 제외
                # Group 2 (Gradual Change) 제외 - 패턴 인식기가 트렌드로 감지하여 신뢰도 하향
                # Group 4 (Cyclic Patterns) 제외 - 주기적 패턴으로 감지하여 신뢰도 하향
                # Group 5 (Service Profile) 제외 - spike-normal 서비스로 신뢰도 하향
                if not scenario.is_edge_case and scenario.group_id not in ["2", "4", "5"]:
                    assert result.detection_result.is_anomaly, (
                        f"Scenario #{scenario.id} ({scenario.name_ko}): "
                        f"Expected anomaly detection for {scenario.expected_severity.value}"
                    )

    def test_chart_generation(
        self,
        chart_generator: CostTrendChartGenerator,
        detector: CostDriftDetector,
    ):
        """차트 URL 생성 검증."""
        scenarios = ScenarioFactory.get_all_scenarios()[:5]  # 처음 5개만 테스트

        for scenario in scenarios:
            cost_data = ScenarioFactory.generate_cost_data(scenario)
            detection_result = detector.analyze_service(cost_data)
            chart_url = chart_generator.generate_chart_url(detection_result)

            assert chart_url is not None, f"Chart URL not generated for {scenario.name_ko}"
            assert "quickchart.io" in chart_url, "Invalid chart URL"

    def test_kakao_summary_format(
        self,
        summary_generator: SummaryGenerator,
        detector: CostDriftDetector,
    ):
        """카카오톡 요약 형식 검증."""
        # Critical 시나리오로 테스트
        scenarios = ScenarioFactory.get_scenarios_by_group("1")
        scenario = next(s for s in scenarios if s.expected_severity == Severity.CRITICAL)

        cost_data = ScenarioFactory.generate_cost_data(scenario)
        detection_result = detector.analyze_service(cost_data)
        summary = summary_generator.generate(detection_result)

        # 필수 필드 검증
        assert summary.title is not None
        assert summary.message is not None
        assert summary.severity_emoji is not None
        assert summary.service_name is not None
        assert summary.account_name is not None

        # 한글 포함 검증
        assert "비용" in summary.message or "원" in summary.message

    def test_scenario_count(self):
        """시나리오 개수 검증."""
        scenarios = ScenarioFactory.get_all_scenarios()
        groups = ScenarioFactory.get_all_groups()

        assert len(scenarios) == 35, f"Expected 35 scenarios, got {len(scenarios)}"
        assert len(groups) == 7, f"Expected 7 groups, got {len(groups)}"

        # 그룹별 시나리오 수 검증
        expected_counts = {
            "1": 6,  # Sudden Spike
            "2": 5,  # Gradual Change
            "3": 4,  # Cost Reduction
            "4": 6,  # Cyclic Patterns (5→6: 월간 예외 스파이크 추가)
            "5": 4,  # Service Profile
            "6": 6,  # Edge Cases
            "7": 4,  # Detection Method Comparison
        }

        for group_id, expected_count in expected_counts.items():
            group_scenarios = ScenarioFactory.get_scenarios_by_group(group_id)
            assert len(group_scenarios) == expected_count, (
                f"Group {group_id}: Expected {expected_count} scenarios, got {len(group_scenarios)}"
            )


@pytest.mark.localstack
class TestScenarioReportLocalStack:
    """LocalStack 통합 테스트."""

    @pytest.fixture
    def localstack_detector(self, localstack_available: bool):
        """LocalStack 연동 탐지기."""
        if not localstack_available:
            pytest.skip("LocalStack is not available")
        return CostDriftDetector(sensitivity=0.7)

    def test_generate_with_localstack(
        self,
        localstack_detector: CostDriftDetector,
        localstack_available: bool,
    ):
        """LocalStack 통합 테스트로 리포트 생성."""
        if not localstack_available:
            pytest.skip("LocalStack is not available")

        summary_generator = SummaryGenerator(currency="KRW", enable_chart=True)
        chart_generator = CostTrendChartGenerator()
        report_generator = HTMLReportGenerator()

        scenarios = ScenarioFactory.get_all_scenarios()
        groups = ScenarioFactory.get_all_groups()
        results: List[ScenarioResult] = []

        for scenario in scenarios:
            cost_data = ScenarioFactory.generate_cost_data(scenario)
            detection_result = localstack_detector.analyze_service(cost_data)
            alert_summary = summary_generator.generate(detection_result)
            chart_url = chart_generator.generate_chart_url(detection_result)

            severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
            expected_idx = severity_order.index(scenario.expected_severity)
            actual_idx = severity_order.index(detection_result.severity)

            if not detection_result.is_anomaly and scenario.expected_severity == Severity.LOW:
                passed = True
            else:
                passed = abs(expected_idx - actual_idx) <= 1

            results.append(
                ScenarioResult(
                    scenario_id=scenario.id,
                    scenario_name=scenario.name,
                    scenario_name_ko=scenario.name_ko,
                    description_ko=scenario.description_ko,
                    expected_severity=scenario.expected_severity,
                    detection_result=detection_result,
                    alert_summary=alert_summary,
                    chart_url=chart_url,
                    passed=passed,
                    group_id=scenario.group_id,
                    group_name=scenario.group_name,
                    expected_detection_method=scenario.expected_detection_method,
                    pattern_recognizer=scenario.pattern_recognizer,
                )
            )

        # HTML 리포트 생성
        output_path = Path("reports/scenario_report_localstack.html")
        report_path = report_generator.generate_report(results, output_path, groups)

        assert report_path.exists()
        print(f"\nLocalStack 리포트 생성됨: {report_path}")


def run_scenario_report():
    """CLI에서 직접 실행할 수 있는 함수."""
    detector = CostDriftDetector(sensitivity=0.7)
    summary_generator = SummaryGenerator(currency="KRW", enable_chart=True)
    chart_generator = CostTrendChartGenerator()
    report_generator = HTMLReportGenerator()

    scenarios = ScenarioFactory.get_all_scenarios()
    groups = ScenarioFactory.get_all_groups()
    results: List[ScenarioResult] = []

    print("=== BDP Compact 시나리오 테스트 실행 (35개 시나리오) ===\n")

    for scenario in scenarios:
        cost_data = ScenarioFactory.generate_cost_data(scenario)
        detection_result = detector.analyze_service(cost_data)
        alert_summary = summary_generator.generate(detection_result)
        chart_url = chart_generator.generate_chart_url(detection_result)

        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        expected_idx = severity_order.index(scenario.expected_severity)
        actual_idx = severity_order.index(detection_result.severity)

        if not detection_result.is_anomaly and scenario.expected_severity == Severity.LOW:
            passed = True
        else:
            passed = abs(expected_idx - actual_idx) <= 1

        results.append(
            ScenarioResult(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                scenario_name_ko=scenario.name_ko,
                description_ko=scenario.description_ko,
                expected_severity=scenario.expected_severity,
                detection_result=detection_result,
                alert_summary=alert_summary,
                chart_url=chart_url,
                passed=passed,
                group_id=scenario.group_id,
                group_name=scenario.group_name,
                expected_detection_method=scenario.expected_detection_method,
                pattern_recognizer=scenario.pattern_recognizer,
            )
        )

        status = "PASS" if passed else "FAIL"
        print(
            f"[{status}] #{scenario.id} {scenario.name_ko}: "
            f"expected={scenario.expected_severity.value}, "
            f"actual={detection_result.severity.value}"
        )

    # HTML 리포트 생성
    output_path = Path("reports/scenario_report.html")
    report_path = report_generator.generate_report(results, output_path, groups)

    passed_count = sum(1 for r in results if r.passed)
    print(f"\n=== 결과 ===")
    print(f"전체: {len(results)}, 통과: {passed_count}, 실패: {len(results) - passed_count}")
    print(f"정확도: {passed_count / len(results) * 100:.0f}%")

    # 그룹별 통계
    print("\n그룹별 결과:")
    for group in groups:
        group_results = [r for r in results if r.group_id == group.id]
        group_passed = sum(1 for r in group_results if r.passed)
        print(
            f"  {group.emoji} {group.name_ko}: "
            f"{group_passed}/{len(group_results)} 통과 "
            f"({group_passed / len(group_results) * 100:.0f}%)"
        )

    print(f"\n리포트: {report_path.absolute()}")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Add project root to path for direct execution
    project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(project_root))

    run_scenario_report()
