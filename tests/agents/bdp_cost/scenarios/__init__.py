"""
BDP Compact Test Scenarios Package.

7개 그룹, 34개의 다양한 비용 이상 시나리오를 정의하고 테스트 데이터를 생성합니다.

Groups:
    1. 급등 패턴 (Sudden Spike) - 6개
    2. 점진적 변화 (Gradual Change) - 5개
    3. 비용 감소 (Cost Reduction) - 4개
    4. 주기적 패턴 (Cyclic Patterns) - 5개
    5. 서비스 프로파일 (Service Profile) - 4개
    6. 엣지 케이스 (Edge Cases) - 6개
    7. 탐지 방법 비교 (Detection Method Comparison) - 4개
"""

from tests.agents.bdp_cost.scenarios.scenario_factory import (
    ScenarioDefinition,
    ScenarioFactory,
    ScenarioGroup,
)

__all__ = [
    "ScenarioDefinition",
    "ScenarioFactory",
    "ScenarioGroup",
]
