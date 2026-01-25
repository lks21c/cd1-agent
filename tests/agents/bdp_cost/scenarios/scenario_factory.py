"""
Scenario Factory for BDP Compact Cost Anomaly Detection Testing.

7개 그룹, 35개의 다양한 비용 이상 시나리오를 정의하고 테스트 데이터를 생성합니다.

그룹 목록:
1. 급등 패턴 (Sudden Spike) - 6개
2. 점진적 변화 (Gradual Change) - 5개
3. 비용 감소 (Cost Reduction) - 4개
4. 주기적 패턴 (Cyclic Patterns) - 6개
5. 서비스 프로파일 (Service Profile) - 4개
6. 엣지 케이스 (Edge Cases) - 6개
7. 탐지 방법 비교 (Detection Method Comparison) - 4개
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.agents.bdp_cost.services.anomaly_detector import Severity
from src.agents.bdp_cost.services.cost_explorer_provider import ServiceCostData


@dataclass
class ScenarioDefinition:
    """시나리오 정의."""

    id: str  # "1-1", "2-3", ...
    group_id: str  # "1", "2", ...
    group_name: str  # "Sudden Spike"
    name: str  # "Minor Spike"
    name_ko: str  # "경미한 급등"
    description_ko: str  # 상세 설명
    service_name: str  # "Amazon S3"
    expected_severity: Severity  # CRITICAL, HIGH, MEDIUM, LOW
    expected_detection_method: str  # "ecod", "ratio", "stddev", "ensemble"
    pattern_recognizer: Optional[str]  # "DayOfWeek", "Trend", etc.
    base_cost: float  # 250000 (원)
    spike_percent: float  # +200 (%)
    spike_duration: int  # 3 (일)
    pattern_type: str  # "sudden_spike", "gradual", "reduction", "weekend", etc.
    # 신규 필드
    daily_increase_rate: Optional[float] = None  # 점진적 변화용 (일 증가율 %)
    is_edge_case: bool = False
    edge_case_type: Optional[str] = None  # "insufficient_data", "zero_cost", etc.


@dataclass
class ScenarioGroup:
    """시나리오 그룹 정의."""

    id: str  # "1", "2", ...
    name: str  # "Sudden Spike"
    name_ko: str  # "급등 패턴"
    description_ko: str  # 그룹 설명
    emoji: str  # "📈"
    scenarios: List[ScenarioDefinition] = field(default_factory=list)


class ScenarioFactory:
    """
    시나리오 생성 팩토리.

    7개 그룹, 35개 테스트 시나리오를 정의하고, 각 시나리오에 대한
    ServiceCostData를 생성합니다.
    """

    DEFAULT_ACCOUNT_ID = "111111111111"
    DEFAULT_ACCOUNT_NAME = "bdp-prod"
    DEFAULT_DAYS = 14

    # 그룹 정의
    _GROUPS: Dict[str, ScenarioGroup] = {}

    @classmethod
    def _init_groups(cls) -> None:
        """그룹 초기화."""
        if cls._GROUPS:
            return

        cls._GROUPS = {
            "1": ScenarioGroup(
                id="1",
                name="Sudden Spike",
                name_ko="급등 패턴",
                description_ko="다양한 크기와 기간의 급격한 비용 상승 패턴을 검증합니다.",
                emoji="📈",
            ),
            "2": ScenarioGroup(
                id="2",
                name="Gradual Change",
                name_ko="점진적 변화",
                description_ko="일정 기간에 걸쳐 꾸준히 증가하는 패턴을 검증합니다.",
                emoji="📊",
            ),
            "3": ScenarioGroup(
                id="3",
                name="Cost Reduction",
                name_ko="비용 감소",
                description_ko="비용이 급감하는 이상 패턴 (서비스 장애, 삭제 등)을 검증합니다.",
                emoji="📉",
            ),
            "4": ScenarioGroup(
                id="4",
                name="Cyclic Patterns",
                name_ko="주기적 패턴",
                description_ko="DayOfWeek, MonthCycle 패턴 인식기를 검증합니다.",
                emoji="🔄",
            ),
            "5": ScenarioGroup(
                id="5",
                name="Service Profile",
                name_ko="서비스 프로파일",
                description_ko="spike-normal 서비스 특성 (Lambda, Glue 등)을 검증합니다.",
                emoji="🎯",
            ),
            "6": ScenarioGroup(
                id="6",
                name="Edge Cases",
                name_ko="엣지 케이스",
                description_ko="특수 상황 및 경계값 테스트를 수행합니다.",
                emoji="⚠️",
            ),
            "7": ScenarioGroup(
                id="7",
                name="Detection Method Comparison",
                name_ko="탐지 방법 비교",
                description_ko="각 탐지 방법(ECOD, Ratio, StdDev)의 특성을 검증합니다.",
                emoji="🔬",
            ),
        }

    @classmethod
    def get_all_groups(cls) -> List[ScenarioGroup]:
        """모든 그룹 정의 반환.

        Returns:
            7개의 ScenarioGroup 목록 (시나리오 포함)
        """
        cls._init_groups()
        scenarios = cls.get_all_scenarios()

        # 각 그룹에 시나리오 할당
        for group in cls._GROUPS.values():
            group.scenarios = [s for s in scenarios if s.group_id == group.id]

        return list(cls._GROUPS.values())

    @classmethod
    def get_scenarios_by_group(cls, group_id: str) -> List[ScenarioDefinition]:
        """특정 그룹의 시나리오 반환.

        Args:
            group_id: 그룹 ID (예: "1", "2", ...)

        Returns:
            해당 그룹의 ScenarioDefinition 목록
        """
        return [s for s in cls.get_all_scenarios() if s.group_id == group_id]

    @classmethod
    def get_all_scenarios(cls) -> List[ScenarioDefinition]:
        """모든 시나리오 정의 반환.

        Returns:
            34개의 ScenarioDefinition 목록
        """
        scenarios = []

        # =========================================================================
        # Group 1: 급등 패턴 (Sudden Spike) - 6개
        # =========================================================================
        scenarios.extend([
            # 1-1: 경미한 급등
            ScenarioDefinition(
                id="1-1",
                group_id="1",
                group_name="Sudden Spike",
                name="Minor Spike",
                name_ko="경미한 급등",
                description_ko="S3 비용이 2일간 60% 상승. 일시적 데이터 업로드 증가 의심.",
                service_name="Amazon S3",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=120000,
                spike_percent=60,
                spike_duration=2,
                pattern_type="sudden_spike",
            ),
            # 1-2: 중간 급등
            ScenarioDefinition(
                id="1-2",
                group_id="1",
                group_name="Sudden Spike",
                name="Moderate Spike",
                name_ko="중간 급등",
                description_ko="RDS 비용이 3일간 100% 상승. 인스턴스 타입 변경 또는 Multi-AZ 활성화 의심.",
                service_name="Amazon RDS",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=300000,
                spike_percent=100,
                spike_duration=3,
                pattern_type="sudden_spike",
            ),
            # 1-3: 심각한 급등
            ScenarioDefinition(
                id="1-3",
                group_id="1",
                group_name="Sudden Spike",
                name="Severe Spike",
                name_ko="심각한 급등",
                description_ko="EC2 비용이 2일간 200% 급등. 대규모 인스턴스 시작 또는 Reserved Instance 만료 의심.",
                service_name="Amazon EC2",
                expected_severity=Severity.CRITICAL,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=500000,
                spike_percent=200,
                spike_duration=2,
                pattern_type="sudden_spike",
            ),
            # 1-4: 극단적 급등
            ScenarioDefinition(
                id="1-4",
                group_id="1",
                group_name="Sudden Spike",
                name="Extreme Spike",
                name_ko="극단적 급등",
                description_ko="Lambda 호출량이 1일만에 400% 폭증. 무한 루프 또는 DDoS 공격 의심.",
                service_name="AWS Lambda",
                expected_severity=Severity.CRITICAL,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=80000,
                spike_percent=400,
                spike_duration=1,
                pattern_type="sudden_spike",
            ),
            # 1-5: 단기 스파이크
            ScenarioDefinition(
                id="1-5",
                group_id="1",
                group_name="Sudden Spike",
                name="Short Spike",
                name_ko="단기 스파이크",
                description_ko="Athena 쿼리 비용이 1일간 150% 상승. 대량 데이터 스캔 의심.",
                service_name="Amazon Athena",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=250000,
                spike_percent=150,
                spike_duration=1,
                pattern_type="sudden_spike",
            ),
            # 1-6: 장기 스파이크
            ScenarioDefinition(
                id="1-6",
                group_id="1",
                group_name="Sudden Spike",
                name="Long Spike",
                name_ko="장기 스파이크",
                description_ko="EKS 비용이 5일간 180% 상승. 클러스터 확장 또는 과도한 워크로드 의심.",
                service_name="Amazon EKS",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=350000,
                spike_percent=180,
                spike_duration=5,
                pattern_type="sudden_spike",
            ),
        ])

        # =========================================================================
        # Group 2: 점진적 변화 (Gradual Change) - 5개
        # =========================================================================
        scenarios.extend([
            # 2-1: 완만한 증가
            ScenarioDefinition(
                id="2-1",
                group_id="2",
                group_name="Gradual Change",
                name="Gentle Increase",
                name_ko="완만한 증가",
                description_ko="S3 비용이 7일간 일 2%씩 증가. 데이터 적재량 점진적 증가 패턴.",
                service_name="Amazon S3",
                expected_severity=Severity.LOW,
                expected_detection_method="ratio",
                pattern_recognizer="Trend",
                base_cost=100000,
                spike_percent=14,  # 7 * 2%
                spike_duration=7,
                pattern_type="gradual",
                daily_increase_rate=2.0,
            ),
            # 2-2: 중간 증가
            ScenarioDefinition(
                id="2-2",
                group_id="2",
                group_name="Gradual Change",
                name="Moderate Increase",
                name_ko="중간 증가",
                description_ko="CloudWatch 비용이 7일간 일 4%씩 증가. 로그/메트릭 증가 추세.",
                service_name="Amazon CloudWatch",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ensemble",
                pattern_recognizer="Trend",
                base_cost=50000,
                spike_percent=28,  # 7 * 4%
                spike_duration=7,
                pattern_type="gradual",
                daily_increase_rate=4.0,
            ),
            # 2-3: 가파른 증가
            ScenarioDefinition(
                id="2-3",
                group_id="2",
                group_name="Gradual Change",
                name="Steep Increase",
                name_ko="가파른 증가",
                description_ko="DynamoDB 비용이 7일간 일 12%씩 증가. 트래픽 급증 추세. (84% 누적 증가)",
                service_name="Amazon DynamoDB",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer="Trend",
                base_cost=80000,
                spike_percent=84,  # 7 * 12%
                spike_duration=7,
                pattern_type="gradual",
                daily_increase_rate=12.0,
            ),
            # 2-4: 지속적 상승
            ScenarioDefinition(
                id="2-4",
                group_id="2",
                group_name="Gradual Change",
                name="Persistent Rise",
                name_ko="지속적 상승",
                description_ko="EBS 비용이 10일간 일 3%씩 증가. 스토리지 확장 패턴.",
                service_name="Amazon EBS",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ensemble",
                pattern_recognizer="Trend",
                base_cost=150000,
                spike_percent=30,  # 10 * 3%
                spike_duration=10,
                pattern_type="gradual",
                daily_increase_rate=3.0,
            ),
            # 2-5: 안정 트렌드
            ScenarioDefinition(
                id="2-5",
                group_id="2",
                group_name="Gradual Change",
                name="Stable Trend",
                name_ko="안정 트렌드",
                description_ko="RDS 비용이 7일간 일 1%씩 증가. 정상적인 성장 패턴.",
                service_name="Amazon RDS",
                expected_severity=Severity.LOW,
                expected_detection_method="ratio",
                pattern_recognizer="Trend",
                base_cost=300000,
                spike_percent=7,  # 7 * 1%
                spike_duration=7,
                pattern_type="gradual",
                daily_increase_rate=1.0,
            ),
        ])

        # =========================================================================
        # Group 3: 비용 감소 (Cost Reduction) - 4개
        # =========================================================================
        scenarios.extend([
            # 3-1: 급격한 감소
            ScenarioDefinition(
                id="3-1",
                group_id="3",
                group_name="Cost Reduction",
                name="Sharp Decrease",
                name_ko="급격한 감소",
                description_ko="Kinesis 비용이 2일간 60% 감소. 스트림 삭제 또는 샤드 축소 의심.",
                service_name="Amazon Kinesis",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=100000,
                spike_percent=-60,
                spike_duration=2,
                pattern_type="reduction",
            ),
            # 3-2: 완전 중단
            ScenarioDefinition(
                id="3-2",
                group_id="3",
                group_name="Cost Reduction",
                name="Complete Stop",
                name_ko="완전 중단",
                description_ko="ElastiCache 비용이 3일간 90% 감소. 서비스 장애 또는 클러스터 삭제 의심.",
                service_name="Amazon ElastiCache",
                expected_severity=Severity.CRITICAL,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=200000,
                spike_percent=-90,
                spike_duration=3,
                pattern_type="reduction",
            ),
            # 3-3: 점진적 감소
            ScenarioDefinition(
                id="3-3",
                group_id="3",
                group_name="Cost Reduction",
                name="Gradual Decrease",
                name_ko="점진적 감소",
                description_ko="SQS 비용이 5일간 일 5%씩 감소. 트래픽 감소 또는 최적화 진행 중.",
                service_name="Amazon SQS",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ensemble",
                pattern_recognizer="Trend",
                base_cost=60000,
                spike_percent=-25,  # 5 * -5%
                spike_duration=5,
                pattern_type="gradual_reduction",
                daily_increase_rate=-5.0,
            ),
            # 3-4: 부분 감소
            ScenarioDefinition(
                id="3-4",
                group_id="3",
                group_name="Cost Reduction",
                name="Partial Decrease",
                name_ko="부분 감소",
                description_ko="SNS 비용이 2일간 40% 감소. 알림 구독 해제 또는 트래픽 감소.",
                service_name="Amazon SNS",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=40000,
                spike_percent=-40,
                spike_duration=2,
                pattern_type="reduction",
            ),
        ])

        # =========================================================================
        # Group 4: 주기적 패턴 (Cyclic Patterns) - 5개
        # =========================================================================
        scenarios.extend([
            # 4-1: 주말 패턴
            ScenarioDefinition(
                id="4-1",
                group_id="4",
                group_name="Cyclic Patterns",
                name="Weekend Pattern",
                name_ko="주말 패턴",
                description_ko="DynamoDB 비용이 주말마다 50% 상승. 배치 처리 패턴.",
                service_name="Amazon DynamoDB",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ensemble",
                pattern_recognizer="DayOfWeek",
                base_cost=80000,
                spike_percent=50,
                spike_duration=2,
                pattern_type="weekend",
            ),
            # 4-2: 평일 패턴
            ScenarioDefinition(
                id="4-2",
                group_id="4",
                group_name="Cyclic Patterns",
                name="Weekday Pattern",
                name_ko="평일 패턴",
                description_ko="Lambda 비용이 평일에 80% 상승. 업무 시간 트래픽 패턴. (패턴 빈도가 높아 정상으로 인식될 수 있음)",
                service_name="AWS Lambda",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ensemble",
                pattern_recognizer="DayOfWeek",
                base_cost=80000,
                spike_percent=80,
                spike_duration=5,
                pattern_type="weekday",
            ),
            # 4-3: 월말 버스트
            ScenarioDefinition(
                id="4-3",
                group_id="4",
                group_name="Cyclic Patterns",
                name="Month-End Burst",
                name_ko="월말 버스트",
                description_ko="Glue 비용이 월말에 180% 버스트. 정기 ETL 배치 처리.",
                service_name="AWS Glue",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer="MonthCycle",
                base_cost=150000,
                spike_percent=180,
                spike_duration=3,
                pattern_type="month_end",
            ),
            # 4-4: 월초 버스트 (증가형)
            ScenarioDefinition(
                id="4-4",
                group_id="4",
                group_name="Cyclic Patterns",
                name="Month-Start Burst",
                name_ko="월초 버스트",
                description_ko="Batch 비용이 월초에 200% 버스트 (증가형). 월간 보고서 생성.",
                service_name="AWS Batch",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer="MonthCycle",
                base_cost=100000,
                spike_percent=200,
                spike_duration=2,
                pattern_type="month_start_rising",
            ),
            # 4-5: 격주 패턴 (1주 정상 → 2주 스파이크)
            ScenarioDefinition(
                id="4-5",
                group_id="4",
                group_name="Cyclic Patterns",
                name="Biweekly Pattern",
                name_ko="격주 패턴",
                description_ko="EMR 비용이 1주차 정상 → 2주차 전체 80% 상승. 격주 정기 데이터 처리 스케줄.",
                service_name="Amazon EMR",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=200000,
                spike_percent=80,
                spike_duration=2,
                pattern_type="biweekly",
            ),
            # 4-6: 월간 예외 스파이크
            ScenarioDefinition(
                id="4-6",
                group_id="4",
                group_name="Cyclic Patterns",
                name="Monthly Exception Spike",
                name_ko="월간 예외 스파이크",
                description_ko="Redshift 비용이 3주간 동일 패턴 후 4주차에 150% 예외적 스파이크. 월말 정산, 분기 보고 등 반영.",
                service_name="Amazon Redshift",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer="MonthCycle",
                base_cost=200000,
                spike_percent=150,
                spike_duration=2,
                pattern_type="monthly_exception",
            ),
        ])

        # =========================================================================
        # Group 5: 서비스 프로파일 (Service Profile) - 4개
        # spike-normal 서비스의 실제 운영 패턴 반영
        # =========================================================================
        scenarios.extend([
            # 5-1: Lambda 간헐적 스파이크
            ScenarioDefinition(
                id="5-1",
                group_id="5",
                group_name="Service Profile",
                name="Lambda Intermittent Spike",
                name_ko="Lambda 간헐적 스파이크",
                description_ko="Lambda 비용이 14일 중 3-4회 간헐적으로 200% 급등. 이벤트 기반 서비스 특성.",
                service_name="AWS Lambda",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer="ServiceProfile",
                base_cost=80000,
                spike_percent=200,
                spike_duration=1,
                pattern_type="intermittent_spike",
            ),
            # 5-2: Glue 배치 버스트
            ScenarioDefinition(
                id="5-2",
                group_id="5",
                group_name="Service Profile",
                name="Glue Batch Burst",
                name_ko="Glue 배치 버스트",
                description_ko="Glue 비용이 배치 작업 패턴 (시작 스파이크 → 유지 → 종료 스파이크). ETL 작업 실행.",
                service_name="AWS Glue",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer="ServiceProfile",
                base_cost=150000,
                spike_percent=250,
                spike_duration=3,
                pattern_type="batch_burst",
            ),
            # 5-3: Step Functions 워크플로우 패턴
            ScenarioDefinition(
                id="5-3",
                group_id="5",
                group_name="Service Profile",
                name="Step Functions Workflow",
                name_ko="Step Functions 워크플로우",
                description_ko="Step Functions 비용이 불규칙 워크플로우 실행 패턴. 180% 스파이크.",
                service_name="AWS Step Functions",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer="ServiceProfile",
                base_cost=50000,
                spike_percent=180,
                spike_duration=2,
                pattern_type="workflow_pattern",
            ),
            # 5-4: Athena 쿼리 폭증
            ScenarioDefinition(
                id="5-4",
                group_id="5",
                group_name="Service Profile",
                name="Athena Query Burst",
                name_ko="Athena 쿼리 폭증",
                description_ko="Athena 비용이 급등 후 급락 (V자/역V자 패턴). 대량 분석 쿼리 실행.",
                service_name="Amazon Athena",
                expected_severity=Severity.CRITICAL,
                expected_detection_method="ensemble",
                pattern_recognizer="ServiceProfile",
                base_cost=250000,
                spike_percent=300,
                spike_duration=2,
                pattern_type="query_burst",
            ),
        ])

        # =========================================================================
        # Group 6: 엣지 케이스 (Edge Cases) - 6개
        # =========================================================================
        scenarios.extend([
            # 6-1: 데이터 부족
            ScenarioDefinition(
                id="6-1",
                group_id="6",
                group_name="Edge Cases",
                name="Insufficient Data",
                name_ko="데이터 부족",
                description_ko="5일치 데이터만 있는 신규 서비스. 분석 불충분.",
                service_name="Amazon S3",
                expected_severity=Severity.LOW,
                expected_detection_method="insufficient_data",
                pattern_recognizer=None,
                base_cost=50000,
                spike_percent=20,
                spike_duration=1,
                pattern_type="insufficient_data",
                is_edge_case=True,
                edge_case_type="insufficient_data",
            ),
            # 6-2: 제로 비용
            ScenarioDefinition(
                id="6-2",
                group_id="6",
                group_name="Edge Cases",
                name="Zero Cost",
                name_ko="제로 비용",
                description_ko="Glacier 비용이 0원에서 0원. 사용량 없는 서비스.",
                service_name="Amazon Glacier",
                expected_severity=Severity.LOW,
                expected_detection_method="ratio",
                pattern_recognizer=None,
                base_cost=0,
                spike_percent=0,
                spike_duration=1,
                pattern_type="zero_cost",
                is_edge_case=True,
                edge_case_type="zero_cost",
            ),
            # 6-3: 극소 비용
            ScenarioDefinition(
                id="6-3",
                group_id="6",
                group_name="Edge Cases",
                name="Minimal Cost",
                name_ko="극소 비용",
                description_ko="Route 53 비용이 100원에서 500원 (400% 변화). 극소 비용이지만 변화율이 높아 CRITICAL로 탐지됨. 절대값 임계치 필요성 검증.",
                service_name="Amazon Route 53",
                expected_severity=Severity.CRITICAL,
                expected_detection_method="ratio",
                pattern_recognizer=None,
                base_cost=100,
                spike_percent=400,
                spike_duration=2,
                pattern_type="sudden_spike",
                is_edge_case=True,
                edge_case_type="minimal_cost",
            ),
            # 6-4: 진동 패턴
            ScenarioDefinition(
                id="6-4",
                group_id="6",
                group_name="Edge Cases",
                name="Oscillating Pattern",
                name_ko="진동 패턴",
                description_ko="EC2 비용이 ±30% 반복 변동. 불안정한 워크로드 패턴.",
                service_name="Amazon EC2",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=500000,
                spike_percent=30,
                spike_duration=1,
                pattern_type="oscillating",
                is_edge_case=True,
                edge_case_type="oscillating",
            ),
            # 6-5: 이상치 후 복구
            ScenarioDefinition(
                id="6-5",
                group_id="6",
                group_name="Edge Cases",
                name="Spike Then Recovery",
                name_ko="이상치 후 복구",
                description_ko="RDS 비용이 250% 급등 (4일간 유지) 후 빠른 복구. 스파이크 기간이 길어 탐지 가능.",
                service_name="Amazon RDS",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=300000,
                spike_percent=250,
                spike_duration=4,
                pattern_type="spike_recovery",
                is_edge_case=True,
                edge_case_type="spike_recovery",
            ),
            # 6-6: 점진 후 스파이크
            ScenarioDefinition(
                id="6-6",
                group_id="6",
                group_name="Edge Cases",
                name="Gradual Then Spike",
                name_ko="점진 후 스파이크",
                description_ko="EKS 비용이 일 3%씩 증가 후 100% 급등. 복합 패턴.",
                service_name="Amazon EKS",
                expected_severity=Severity.HIGH,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=350000,
                spike_percent=100,
                spike_duration=2,
                pattern_type="gradual_then_spike",
                is_edge_case=True,
                edge_case_type="gradual_then_spike",
                daily_increase_rate=3.0,
            ),
        ])

        # =========================================================================
        # Group 7: 탐지 방법 비교 (Detection Method Comparison) - 4개
        # =========================================================================
        scenarios.extend([
            # 7-1: ECOD 우세
            ScenarioDefinition(
                id="7-1",
                group_id="7",
                group_name="Detection Method Comparison",
                name="ECOD Dominant",
                name_ko="ECOD 우세",
                description_ko="분포 극단값 케이스. ECOD가 가장 잘 탐지.",
                service_name="Amazon Redshift",
                expected_severity=Severity.HIGH,
                expected_detection_method="ecod",
                pattern_recognizer=None,
                base_cost=400000,
                spike_percent=150,
                spike_duration=1,
                pattern_type="ecod_dominant",
            ),
            # 7-2: Ratio 우세
            ScenarioDefinition(
                id="7-2",
                group_id="7",
                group_name="Detection Method Comparison",
                name="Ratio Dominant",
                name_ko="Ratio 우세",
                description_ko="평균 대비 명확한 변화. Ratio가 가장 잘 탐지.",
                service_name="Amazon CloudFront",
                expected_severity=Severity.MEDIUM,
                expected_detection_method="ratio",
                pattern_recognizer=None,
                base_cost=180000,
                spike_percent=80,
                spike_duration=3,
                pattern_type="ratio_dominant",
            ),
            # 7-3: StdDev 우세
            ScenarioDefinition(
                id="7-3",
                group_id="7",
                group_name="Detection Method Comparison",
                name="StdDev Dominant",
                name_ko="StdDev 우세",
                description_ko="높은 표준편차 케이스. StdDev가 가장 잘 탐지.",
                service_name="Amazon SageMaker",
                expected_severity=Severity.HIGH,
                expected_detection_method="stddev",
                pattern_recognizer=None,
                base_cost=500000,
                spike_percent=120,
                spike_duration=2,
                pattern_type="stddev_dominant",
            ),
            # 7-4: Ensemble 합의
            ScenarioDefinition(
                id="7-4",
                group_id="7",
                group_name="Detection Method Comparison",
                name="Ensemble Agreement",
                name_ko="Ensemble 합의",
                description_ko="모든 탐지 방법이 동의하는 명확한 이상치.",
                service_name="Amazon OpenSearch",
                expected_severity=Severity.CRITICAL,
                expected_detection_method="ensemble",
                pattern_recognizer=None,
                base_cost=250000,
                spike_percent=200,
                spike_duration=3,
                pattern_type="sudden_spike",
            ),
        ])

        return scenarios

    @classmethod
    def generate_cost_data(
        cls,
        scenario: ScenarioDefinition,
        account_id: str = None,
        account_name: str = None,
        days: int = None,
    ) -> ServiceCostData:
        """시나리오에 맞는 비용 데이터 생성.

        Args:
            scenario: 시나리오 정의
            account_id: 계정 ID (기본: DEFAULT_ACCOUNT_ID)
            account_name: 계정 이름 (기본: DEFAULT_ACCOUNT_NAME)
            days: 데이터 일수 (기본: DEFAULT_DAYS)

        Returns:
            ServiceCostData 객체
        """
        account_id = account_id or cls.DEFAULT_ACCOUNT_ID
        account_name = account_name or cls.DEFAULT_ACCOUNT_NAME
        days = days or cls.DEFAULT_DAYS

        # 엣지 케이스: 데이터 부족
        if scenario.edge_case_type == "insufficient_data":
            days = 5

        end_date = datetime.utcnow()
        timestamps = [
            (end_date - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
            for i in range(days)
        ]

        # 패턴 타입에 따른 비용 데이터 생성
        pattern_generators = {
            "sudden_spike": cls._generate_sudden_spike,
            "gradual": cls._generate_gradual_increase,
            "reduction": cls._generate_reduction,
            "gradual_reduction": cls._generate_gradual_reduction,
            "weekend": cls._generate_weekend_pattern,
            "weekday": cls._generate_weekday_pattern,
            "month_end": cls._generate_month_end_pattern,
            "month_start": cls._generate_month_start_pattern,
            "month_start_rising": cls._generate_month_start_rising_pattern,
            "biweekly": cls._generate_biweekly_pattern,
            "monthly_exception": cls._generate_monthly_exception_pattern,
            "normal": cls._generate_normal_variation,
            # Edge cases
            "insufficient_data": cls._generate_normal_variation,
            "zero_cost": cls._generate_zero_cost_pattern,
            "oscillating": cls._generate_oscillating_pattern,
            "spike_recovery": cls._generate_spike_recovery_pattern,
            "gradual_then_spike": cls._generate_gradual_then_spike_pattern,
            # Detection method comparison
            "ecod_dominant": cls._generate_ecod_dominant_pattern,
            "ratio_dominant": cls._generate_ratio_dominant_pattern,
            "stddev_dominant": cls._generate_stddev_dominant_pattern,
            # Service profile patterns
            "intermittent_spike": cls._generate_intermittent_spike,
            "batch_burst": cls._generate_batch_burst,
            "workflow_pattern": cls._generate_workflow_pattern,
            "query_burst": cls._generate_query_burst,
        }

        generator = pattern_generators.get(
            scenario.pattern_type,
            cls._generate_sudden_spike,
        )

        # 타임스탬프가 필요한 패턴들
        patterns_need_timestamps = {
            "weekend", "weekday", "month_end", "month_start", "month_start_rising",
            "biweekly", "monthly_exception"
        }

        if scenario.pattern_type in patterns_need_timestamps:
            costs = generator(scenario, days, timestamps)
        else:
            costs = generator(scenario, days)

        return ServiceCostData(
            service_name=scenario.service_name,
            account_id=account_id,
            account_name=account_name,
            current_cost=costs[-1],
            historical_costs=costs,
            timestamps=timestamps,
            currency="KRW",
        )

    # =========================================================================
    # 기존 패턴 생성기
    # =========================================================================

    @classmethod
    def _generate_sudden_spike(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """급격한 스파이크 패턴 생성."""
        import random

        base = scenario.base_cost
        spike_days = scenario.spike_duration
        spike_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []
        # 정상 기간
        for _ in range(days - spike_days):
            variance = random.uniform(-0.05, 0.05)
            costs.append(base * (1 + variance))

        # 스파이크 기간 (점진적 상승)
        for i in range(spike_days):
            progress = (i + 1) / spike_days
            multiplier = 1 + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_gradual_increase(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """점진적 증가 패턴 생성."""
        import random

        base = scenario.base_cost
        daily_rate = scenario.daily_increase_rate or (scenario.spike_percent / scenario.spike_duration)

        costs = []
        for i in range(days):
            if i < days - scenario.spike_duration:
                # 정상 기간
                variance = random.uniform(-0.03, 0.03)
                costs.append(base * (1 + variance))
            else:
                # 점진적 증가 기간
                progress_days = i - (days - scenario.spike_duration)
                multiplier = 1 + (daily_rate / 100 * (progress_days + 1))
                variance = random.uniform(-0.02, 0.02)
                costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_reduction(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """비용 감소 패턴 생성."""
        import random

        base = scenario.base_cost
        spike_days = scenario.spike_duration
        reduction_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []
        # 정상 기간
        for _ in range(days - spike_days):
            variance = random.uniform(-0.05, 0.05)
            costs.append(base * (1 + variance))

        # 감소 기간
        for i in range(spike_days):
            progress = (i + 1) / spike_days
            multiplier = 1 + (reduction_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_gradual_reduction(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """점진적 감소 패턴 생성."""
        import random

        base = scenario.base_cost
        daily_rate = scenario.daily_increase_rate or (scenario.spike_percent / scenario.spike_duration)

        costs = []
        for i in range(days):
            if i < days - scenario.spike_duration:
                variance = random.uniform(-0.03, 0.03)
                costs.append(base * (1 + variance))
            else:
                progress_days = i - (days - scenario.spike_duration)
                multiplier = 1 + (daily_rate / 100 * (progress_days + 1))
                variance = random.uniform(-0.02, 0.02)
                costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_weekend_pattern(
        cls, scenario: ScenarioDefinition, days: int, timestamps: List[str]
    ) -> List[float]:
        """주말 패턴 생성."""
        import random

        base = scenario.base_cost
        spike_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []
        for ts in timestamps:
            dt = datetime.strptime(ts, "%Y-%m-%d")
            is_weekend = dt.weekday() >= 5  # Saturday(5), Sunday(6)

            if is_weekend:
                variance = random.uniform(-0.05, 0.05)
                costs.append(base * spike_multiplier * (1 + variance))
            else:
                variance = random.uniform(-0.05, 0.05)
                costs.append(base * (1 + variance))

        return costs

    @classmethod
    def _generate_weekday_pattern(
        cls, scenario: ScenarioDefinition, days: int, timestamps: List[str]
    ) -> List[float]:
        """평일 패턴 생성."""
        import random

        base = scenario.base_cost
        spike_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []
        for ts in timestamps:
            dt = datetime.strptime(ts, "%Y-%m-%d")
            is_weekday = dt.weekday() < 5  # Monday-Friday

            if is_weekday:
                variance = random.uniform(-0.05, 0.05)
                costs.append(base * spike_multiplier * (1 + variance))
            else:
                variance = random.uniform(-0.05, 0.05)
                costs.append(base * (1 + variance))

        return costs

    @classmethod
    def _generate_month_end_pattern(
        cls, scenario: ScenarioDefinition, days: int, timestamps: List[str]
    ) -> List[float]:
        """월말 패턴 생성."""
        import random

        base = scenario.base_cost
        spike_days = scenario.spike_duration
        spike_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []
        # 정상 기간
        for _ in range(days - spike_days):
            variance = random.uniform(-0.05, 0.05)
            costs.append(base * (1 + variance))

        # 월말 버스트 기간
        for i in range(spike_days):
            progress = (i + 1) / spike_days
            multiplier = 1 + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_month_start_pattern(
        cls, scenario: ScenarioDefinition, days: int, timestamps: List[str]
    ) -> List[float]:
        """월초 패턴 생성."""
        import random

        base = scenario.base_cost
        spike_days = scenario.spike_duration
        spike_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []

        # 월초 버스트 (처음 spike_days일)
        for i in range(min(spike_days, days)):
            progress = (spike_days - i) / spike_days  # 점점 감소
            multiplier = 1 + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        # 정상 기간
        for _ in range(days - spike_days):
            variance = random.uniform(-0.05, 0.05)
            costs.append(base * (1 + variance))

        return costs

    @classmethod
    def _generate_biweekly_pattern(
        cls, scenario: ScenarioDefinition, days: int, timestamps: List[str]
    ) -> List[float]:
        """격주 패턴 생성.

        1주차(0-6일): 정상 비용
        2주차(7-13일): 전체 스파이크 (+80%)

        이 패턴은 4-6 월간 예외 스파이크(12일 정상 + 2일 스파이크)와
        시각적으로 명확히 구분됩니다.
        """
        import random

        base = scenario.base_cost
        spike_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []
        for i, ts in enumerate(timestamps):
            # 2주차(day 7 이상)에 전체 스파이크
            if i >= 7:
                variance = random.uniform(-0.05, 0.05)
                costs.append(base * spike_multiplier * (1 + variance))
            else:
                # 1주차는 정상
                variance = random.uniform(-0.05, 0.05)
                costs.append(base * (1 + variance))

        return costs

    @classmethod
    def _generate_normal_variation(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """정상 변동 패턴 생성."""
        import random

        base = scenario.base_cost
        max_variance = min(scenario.spike_percent / 100, 0.1) if scenario.spike_percent > 0 else 0.1

        costs = []
        for _ in range(days):
            variance = random.uniform(-max_variance, max_variance)
            costs.append(max(0, base * (1 + variance)))

        return costs

    # =========================================================================
    # 신규 패턴 생성기 (엣지 케이스)
    # =========================================================================

    @classmethod
    def _generate_zero_cost_pattern(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """제로 비용 패턴 생성."""
        return [0.0] * days

    @classmethod
    def _generate_oscillating_pattern(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """진동 패턴 생성."""
        import random

        base = scenario.base_cost
        variance = scenario.spike_percent / 100

        costs = []
        for i in range(days):
            # 짝수일: 높음, 홀수일: 낮음
            if i % 2 == 0:
                multiplier = 1 + variance * random.uniform(0.8, 1.0)
            else:
                multiplier = 1 - variance * random.uniform(0.8, 1.0)
            costs.append(base * multiplier)

        return costs

    @classmethod
    def _generate_spike_recovery_pattern(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """스파이크 후 부분 복구 패턴 생성.

        스파이크가 유지된 상태에서 부분적으로만 복구되어 탐지 가능.
        """
        import random

        base = scenario.base_cost
        spike_multiplier = 1 + (scenario.spike_percent / 100)
        spike_days = scenario.spike_duration

        costs = []

        # 정상 기간 (처음)
        normal_days = days - spike_days
        for _ in range(max(0, normal_days)):
            variance = random.uniform(-0.05, 0.05)
            costs.append(base * (1 + variance))

        # 스파이크 기간 (마지막 spike_days일에 높은 값 유지)
        # 점진적 상승 후 높은 수준 유지
        for i in range(spike_days):
            progress = (i + 1) / spike_days
            # 최소 70%의 스파이크 유지
            multiplier = 1 + (spike_multiplier - 1) * max(0.7, progress)
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs[:days]

    @classmethod
    def _generate_gradual_then_spike_pattern(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """점진적 증가 후 스파이크 패턴 생성."""
        import random

        base = scenario.base_cost
        daily_rate = scenario.daily_increase_rate or 3.0
        spike_multiplier = 1 + (scenario.spike_percent / 100)
        spike_days = scenario.spike_duration

        costs = []

        # 점진적 증가 기간
        gradual_days = days - spike_days
        for i in range(gradual_days):
            multiplier = 1 + (daily_rate / 100 * i)
            variance = random.uniform(-0.02, 0.02)
            costs.append(base * multiplier * (1 + variance))

        # 스파이크 기간
        gradual_end_multiplier = 1 + (daily_rate / 100 * gradual_days)
        for i in range(spike_days):
            progress = (i + 1) / spike_days
            multiplier = gradual_end_multiplier + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs

    # =========================================================================
    # 탐지 방법 비교용 패턴 생성기
    # =========================================================================

    @classmethod
    def _generate_ecod_dominant_pattern(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """ECOD 우세 패턴 (분포 극단값).

        정규분포에서 벗어나는 극단값을 생성.
        """
        import random

        base = scenario.base_cost

        costs = []
        # 대부분 일정한 값
        for _ in range(days - 1):
            variance = random.uniform(-0.02, 0.02)
            costs.append(base * (1 + variance))

        # 마지막 값만 극단적
        spike_multiplier = 1 + (scenario.spike_percent / 100)
        costs.append(base * spike_multiplier)

        return costs

    @classmethod
    def _generate_ratio_dominant_pattern(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """Ratio 우세 패턴 (평균 대비 명확한 변화).

        일정한 기준선에서 명확한 비율 증가.
        """
        import random

        base = scenario.base_cost
        spike_days = scenario.spike_duration
        spike_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []
        # 매우 안정적인 기준선
        for _ in range(days - spike_days):
            variance = random.uniform(-0.01, 0.01)
            costs.append(base * (1 + variance))

        # 명확한 증가
        for _ in range(spike_days):
            variance = random.uniform(-0.01, 0.01)
            costs.append(base * spike_multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_stddev_dominant_pattern(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """StdDev 우세 패턴 (높은 변동성 + 극단값).

        변동성이 높은 데이터에서 Z-score가 높은 극단값.
        """
        import random

        base = scenario.base_cost

        costs = []
        # 변동성이 있는 기준선
        for _ in range(days - 2):
            variance = random.uniform(-0.15, 0.15)
            costs.append(base * (1 + variance))

        # 마지막 값들: 극단적으로 높음 (높은 Z-score)
        spike_multiplier = 1 + (scenario.spike_percent / 100)
        for _ in range(2):
            variance = random.uniform(-0.02, 0.02)
            costs.append(base * spike_multiplier * (1 + variance))

        return costs

    # =========================================================================
    # 신규 패턴 생성기 (주기적 패턴)
    # =========================================================================

    @classmethod
    def _generate_month_start_rising_pattern(
        cls, scenario: ScenarioDefinition, days: int, timestamps: List[str]
    ) -> List[float]:
        """월초 증가형 패턴 생성 (정상 → 스파이크).

        기존 month_start는 감소형(스파이크→정상)이었으나,
        탐지가 어려워 증가형으로 변경.
        """
        import random

        base = scenario.base_cost
        spike_days = scenario.spike_duration
        spike_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []

        # 정상 기간 (처음)
        for _ in range(days - spike_days):
            variance = random.uniform(-0.05, 0.05)
            costs.append(base * (1 + variance))

        # 월초 버스트 (마지막 spike_days일) - 점진적 상승
        for i in range(spike_days):
            progress = (i + 1) / spike_days
            multiplier = 1 + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_monthly_exception_pattern(
        cls, scenario: ScenarioDefinition, days: int, timestamps: List[str]
    ) -> List[float]:
        """월간 예외 스파이크 패턴 생성.

        3주간 동일한 패턴 후 4주차에 예외적 스파이크.
        월말 정산, 분기 보고서 등의 업무 패턴 반영.
        """
        import random

        base = scenario.base_cost
        spike_days = scenario.spike_duration
        spike_multiplier = 1 + (scenario.spike_percent / 100)

        costs = []

        # 14일 기준: 처음 11-12일은 정상, 마지막 2-3일은 스파이크
        normal_days = days - spike_days

        # 정상 기간 (3주 동일 패턴 시뮬레이션)
        for _ in range(normal_days):
            variance = random.uniform(-0.05, 0.05)
            costs.append(base * (1 + variance))

        # 4주차 예외적 스파이크
        for i in range(spike_days):
            progress = (i + 1) / spike_days
            multiplier = 1 + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs

    # =========================================================================
    # 신규 패턴 생성기 (서비스 프로파일)
    # =========================================================================

    @classmethod
    def _generate_intermittent_spike(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """간헐적 스파이크 패턴 생성 (Lambda 등 이벤트 기반 서비스).

        마지막 2-3일에 스파이크를 배치하여 탐지 가능하도록 함.
        이벤트 기반 서비스의 실제 운영 패턴 반영.
        """
        import random

        base = scenario.base_cost
        spike_multiplier = 1 + (scenario.spike_percent / 100)
        spike_duration = max(2, scenario.spike_duration)

        costs = []

        # 처음에 1-2회 간헐적 스파이크 (히스토리에 패턴 추가)
        early_spike_day = random.randint(2, 5)

        # 정상 기간 (처음)
        for i in range(days - spike_duration):
            if i == early_spike_day:
                # 중간 정도의 스파이크 (패턴 히스토리)
                variance = random.uniform(-0.05, 0.05)
                costs.append(base * (spike_multiplier * 0.6) * (1 + variance))
            else:
                variance = random.uniform(-0.05, 0.05)
                costs.append(base * (1 + variance))

        # 마지막 spike_duration일에 큰 스파이크 (탐지 대상)
        for i in range(spike_duration):
            progress = (i + 1) / spike_duration
            multiplier = 1 + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_batch_burst(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """배치 버스트 패턴 생성 (Glue 등 ETL 서비스).

        정상 기간 후 마지막에 급격한 스파이크.
        탐지가 확실하도록 마지막에 높은 값으로 끝남.
        """
        import random

        base = scenario.base_cost
        spike_multiplier = 1 + (scenario.spike_percent / 100)
        spike_duration = scenario.spike_duration

        costs = []

        # 정상 기간 (처음)
        normal_days = days - spike_duration
        for _ in range(normal_days):
            variance = random.uniform(-0.05, 0.05)
            costs.append(base * (1 + variance))

        # 스파이크 기간 (마지막 spike_duration일)
        for i in range(spike_duration):
            progress = (i + 1) / spike_duration
            multiplier = 1 + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_workflow_pattern(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """워크플로우 실행 패턴 생성 (Step Functions 등).

        불규칙한 스파이크 패턴.
        워크플로우 실행이 불규칙하게 발생하는 패턴 반영.
        """
        import random

        base = scenario.base_cost
        spike_multiplier = 1 + (scenario.spike_percent / 100)
        duration = scenario.spike_duration

        costs = []

        # 정상 기간 (처음)
        normal_days = days - duration
        for _ in range(normal_days):
            variance = random.uniform(-0.05, 0.05)
            # 가끔 작은 스파이크 (워크플로우 짧은 실행)
            if random.random() < 0.2:
                small_spike = random.uniform(1.2, 1.5)
                costs.append(base * small_spike * (1 + variance))
            else:
                costs.append(base * (1 + variance))

        # 주요 스파이크 기간 (대량 워크플로우 실행)
        for i in range(duration):
            progress = (i + 1) / duration
            multiplier = 1 + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.05, 0.05)
            costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def _generate_query_burst(
        cls, scenario: ScenarioDefinition, days: int
    ) -> List[float]:
        """쿼리 폭증 패턴 생성 (Athena 등 쿼리 기반 서비스).

        정상 → 급등 패턴으로 마지막에 높은 스파이크.
        대량 쿼리 실행이 최근에 발생하여 탐지 대상이 됨.
        """
        import random

        base = scenario.base_cost
        spike_multiplier = 1 + (scenario.spike_percent / 100)
        duration = scenario.spike_duration

        costs = []

        # 정상 기간 (처음) - 가끔 작은 스파이크
        normal_days = days - duration
        for i in range(normal_days):
            if i == normal_days // 2:
                # 중간에 작은 스파이크 (쿼리 패턴 히스토리)
                variance = random.uniform(-0.03, 0.03)
                costs.append(base * 1.5 * (1 + variance))
            else:
                variance = random.uniform(-0.05, 0.05)
                costs.append(base * (1 + variance))

        # 마지막 duration일에 급등 (대량 쿼리 실행)
        for i in range(duration):
            progress = (i + 1) / duration
            multiplier = 1 + (spike_multiplier - 1) * progress
            variance = random.uniform(-0.03, 0.03)
            costs.append(base * multiplier * (1 + variance))

        return costs

    @classmethod
    def generate_all_cost_data(
        cls,
        account_id: str = None,
        account_name: str = None,
        days: int = None,
    ) -> List[ServiceCostData]:
        """모든 시나리오에 대한 비용 데이터 생성.

        Args:
            account_id: 계정 ID
            account_name: 계정 이름
            days: 데이터 일수

        Returns:
            35개의 ServiceCostData 목록
        """
        scenarios = cls.get_all_scenarios()
        return [
            cls.generate_cost_data(scenario, account_id, account_name, days)
            for scenario in scenarios
        ]
