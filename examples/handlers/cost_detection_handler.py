"""
Cost Detection Handler for CD1 Agent.

이 핸들러는 AWS Cost Explorer를 통해 비용 이상을 감지합니다.
- Cross-Account AssumeRole 지원
- 복합 이상 탐지 (비율/표준편차/추세 분석)
- DynamoDB 기반 이력 관리 및 추적
- EventBridge 이벤트 발행
"""
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from .base_handler import BaseHandler, lambda_handler_wrapper, HandlerError
from ..services.cost_explorer_client import CostExplorerClient, AccountConfig
from ..services.cost_anomaly_detector import (
    CostAnomalyDetector,
    AnomalyThresholds,
    AnomalyResult,
    Severity,
    transform_costs_for_detection
)
from ..services.aws_client import AWSClient


class ThresholdsConfig(BaseModel):
    """이상 탐지 임계값 설정."""
    ratio_threshold: float = Field(default=0.5, description="비율 기반 임계값 (50% 증가)")
    stddev_multiplier: float = Field(default=2.0, description="표준편차 배수 (2σ)")
    trend_consecutive_days: int = Field(default=3, ge=2, le=7, description="추세 연속 일수")
    severity_high_threshold: float = Field(default=0.8, description="HIGH 심각도 임계값")
    severity_medium_threshold: float = Field(default=0.5, description="MEDIUM 심각도 임계값")


class CrossAccountConfig(BaseModel):
    """Cross-Account 설정."""
    role_arn: str = Field(..., description="AssumeRole ARN")
    account_alias: str = Field(default="", description="계정 별칭")
    external_id: Optional[str] = Field(default=None, description="External ID")


class CostDetectionInput(BaseModel):
    """Cost Detection Lambda 입력 모델."""
    start_date: Optional[str] = Field(
        default=None,
        description="시작 날짜 (YYYY-MM-DD), 기본값: 14일 전"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="종료 날짜 (YYYY-MM-DD), 기본값: 오늘"
    )
    granularity: str = Field(
        default="DAILY",
        pattern="^(DAILY|MONTHLY|HOURLY)$",
        description="시간 단위"
    )
    group_by: List[str] = Field(
        default=["SERVICE"],
        description="그룹화 기준 (SERVICE, LINKED_ACCOUNT 등)"
    )
    cross_accounts: Optional[List[CrossAccountConfig]] = Field(
        default=None,
        description="Cross-Account 설정 목록"
    )
    thresholds: Optional[ThresholdsConfig] = Field(
        default=None,
        description="이상 탐지 임계값"
    )
    target_date: Optional[str] = Field(
        default=None,
        description="분석 대상 날짜 (기본: 최근 날짜)"
    )
    min_cost_threshold: float = Field(
        default=1.0,
        ge=0,
        description="분석 대상 최소 비용 ($)"
    )


class AnomalyDetail(BaseModel):
    """개별 이상 현상 상세."""
    anomaly_id: str
    service_name: str
    severity: str
    confidence_score: float
    current_cost: float
    previous_cost: float
    cost_change_ratio: float
    detected_methods: List[str]
    analysis: str
    date: str


class AccountSummary(BaseModel):
    """계정별 요약."""
    account_id: str
    account_alias: str
    total_cost: float
    anomaly_count: int
    high_severity_count: int
    medium_severity_count: int
    top_anomalies: List[AnomalyDetail]


class CostDetectionOutput(BaseModel):
    """Cost Detection Lambda 출력 모델."""
    anomalies_detected: bool
    total_anomaly_count: int
    high_severity_count: int
    medium_severity_count: int
    accounts_analyzed: int
    account_summaries: List[AccountSummary]
    all_anomalies: List[AnomalyDetail]
    analysis_period: Dict[str, str]
    execution_time_ms: int


class CostDetectionHandler(BaseHandler[CostDetectionInput]):
    """비용 이상을 감지하는 핸들러."""

    def __init__(self):
        super().__init__(CostDetectionInput)
        self.aws_client = AWSClient()

        # 테이블 이름
        self.history_table = os.environ.get('COST_HISTORY_TABLE', 'bdp-cost-history')
        self.anomaly_table = os.environ.get('COST_ANOMALY_TABLE', 'bdp-cost-anomaly-tracking')

        # EventBridge 이벤트 버스
        self.event_bus = os.environ.get('EVENT_BUS_NAME', 'default')
        self.event_source = 'bdp.cost-detection'

    def process(self, input_data: CostDetectionInput, context: Any) -> Dict:
        """메인 비용 이상 감지 프로세스."""
        start_time = datetime.utcnow()

        # 날짜 범위 설정
        end_date = input_data.end_date or datetime.utcnow().strftime("%Y-%m-%d")
        start_date = input_data.start_date or (
            datetime.utcnow() - timedelta(days=14)
        ).strftime("%Y-%m-%d")

        self.logger.info(
            "cost_detection_start",
            start_date=start_date,
            end_date=end_date,
            granularity=input_data.granularity
        )

        # Cross-Account 설정 변환
        account_configs = None
        if input_data.cross_accounts:
            account_configs = [
                AccountConfig(
                    role_arn=acc.role_arn,
                    account_alias=acc.account_alias,
                    external_id=acc.external_id
                )
                for acc in input_data.cross_accounts
            ]

        # Cost Explorer 클라이언트 초기화
        cost_client = CostExplorerClient(account_configs=account_configs)

        # 이상 탐지기 초기화
        thresholds = None
        if input_data.thresholds:
            thresholds = AnomalyThresholds(
                ratio_threshold=input_data.thresholds.ratio_threshold,
                stddev_multiplier=input_data.thresholds.stddev_multiplier,
                trend_consecutive_days=input_data.thresholds.trend_consecutive_days,
                severity_high_threshold=input_data.thresholds.severity_high_threshold,
                severity_medium_threshold=input_data.thresholds.severity_medium_threshold
            )
        detector = CostAnomalyDetector(thresholds=thresholds)

        # 모든 계정의 비용 데이터 조회
        all_accounts_costs = cost_client.get_all_accounts_costs(
            start_date=start_date,
            end_date=end_date,
            granularity=input_data.granularity,
            group_by=input_data.group_by
        )

        # 결과 수집
        account_summaries = []
        all_anomalies = []
        total_high = 0
        total_medium = 0

        for account_id, account_data in all_accounts_costs.items():
            if "error" in account_data:
                self.logger.warning(
                    "account_cost_query_failed",
                    account_id=account_id,
                    error=account_data["error"]
                )
                continue

            costs_data = account_data["data"]
            account_alias = account_data["account_alias"]

            # 비용 데이터 변환 (서비스별로 재구성)
            costs_by_service = transform_costs_for_detection(
                costs_data["costs_by_date"]
            )

            # 최소 비용 필터링
            filtered_costs = {
                service: dates
                for service, dates in costs_by_service.items()
                if max(dates.values()) >= input_data.min_cost_threshold
            }

            # 이상 탐지 수행
            anomaly_results = detector.detect_all_services(
                costs_data=filtered_costs,
                target_date=input_data.target_date
            )

            # 결과 변환
            account_anomalies = []
            high_count = 0
            medium_count = 0

            for result in anomaly_results:
                anomaly_detail = self._create_anomaly_detail(result, account_id)
                account_anomalies.append(anomaly_detail)
                all_anomalies.append(anomaly_detail)

                if result.severity == Severity.HIGH:
                    high_count += 1
                    total_high += 1
                elif result.severity == Severity.MEDIUM:
                    medium_count += 1
                    total_medium += 1

                # DynamoDB에 이상 현상 저장
                self._save_anomaly(anomaly_detail, account_id)

                # EventBridge 이벤트 발행
                self._publish_event(anomaly_detail, account_id, account_alias)

            # 계정 요약 생성
            account_summary = AccountSummary(
                account_id=account_id,
                account_alias=account_alias,
                total_cost=costs_data["total_cost"],
                anomaly_count=len(account_anomalies),
                high_severity_count=high_count,
                medium_severity_count=medium_count,
                top_anomalies=account_anomalies[:5]  # 상위 5개만
            )
            account_summaries.append(account_summary)

            # 비용 이력 저장
            self._save_cost_history(account_id, costs_data, len(anomaly_results))

        # 실행 시간 계산
        execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        # 결과 생성
        output = CostDetectionOutput(
            anomalies_detected=len(all_anomalies) > 0,
            total_anomaly_count=len(all_anomalies),
            high_severity_count=total_high,
            medium_severity_count=total_medium,
            accounts_analyzed=len(account_summaries),
            account_summaries=account_summaries,
            all_anomalies=all_anomalies,
            analysis_period={
                "start_date": start_date,
                "end_date": end_date,
                "granularity": input_data.granularity
            },
            execution_time_ms=execution_time
        )

        self.logger.info(
            "cost_detection_complete",
            anomaly_count=len(all_anomalies),
            high_severity=total_high,
            medium_severity=total_medium,
            execution_time_ms=execution_time
        )

        return output.model_dump()

    def _create_anomaly_detail(
        self,
        result: AnomalyResult,
        account_id: str
    ) -> AnomalyDetail:
        """AnomalyResult를 AnomalyDetail로 변환."""
        anomaly_id = f"{account_id}-{result.service_name}-{result.date}-{uuid.uuid4().hex[:8]}"

        return AnomalyDetail(
            anomaly_id=anomaly_id,
            service_name=result.service_name,
            severity=result.severity.value,
            confidence_score=result.confidence_score,
            current_cost=result.current_cost,
            previous_cost=result.previous_cost,
            cost_change_ratio=result.cost_change_ratio,
            detected_methods=result.detected_methods,
            analysis=result.analysis,
            date=result.date
        )

    def _save_anomaly(self, anomaly: AnomalyDetail, account_id: str) -> None:
        """DynamoDB에 이상 현상 저장."""
        try:
            ttl = int((datetime.utcnow() + timedelta(days=90)).timestamp())

            self.aws_client.dynamodb.put_item(
                table_name=self.anomaly_table,
                item={
                    'anomaly_id': anomaly.anomaly_id,
                    'account_id': account_id,
                    'service_name': anomaly.service_name,
                    'severity': anomaly.severity,
                    'confidence_score': str(anomaly.confidence_score),
                    'current_cost': str(anomaly.current_cost),
                    'previous_cost': str(anomaly.previous_cost),
                    'cost_change_ratio': str(anomaly.cost_change_ratio),
                    'detected_methods': anomaly.detected_methods,
                    'analysis': anomaly.analysis,
                    'date': anomaly.date,
                    'created_at': datetime.utcnow().isoformat(),
                    'ttl': ttl
                }
            )
        except Exception as e:
            self.logger.warning(
                "anomaly_save_failed",
                anomaly_id=anomaly.anomaly_id,
                error=str(e)
            )

    def _save_cost_history(
        self,
        account_id: str,
        costs_data: Dict,
        anomaly_count: int
    ) -> None:
        """DynamoDB에 비용 이력 저장."""
        try:
            # 서비스별 비용 상위 5개 추출
            service_totals = {}
            for date_costs in costs_data["costs_by_date"].values():
                for service, cost in date_costs.items():
                    service_totals[service] = service_totals.get(service, 0) + cost

            top_services = sorted(
                service_totals.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            ttl = int((datetime.utcnow() + timedelta(days=365)).timestamp())
            today = datetime.utcnow().strftime("%Y-%m-%d")

            self.aws_client.dynamodb.put_item(
                table_name=self.history_table,
                item={
                    'account_id': account_id,
                    'date': today,
                    'total_cost': str(costs_data["total_cost"]),
                    'top_services': json.dumps(dict(top_services)),
                    'anomaly_count': anomaly_count,
                    'created_at': datetime.utcnow().isoformat(),
                    'ttl': ttl
                }
            )
        except Exception as e:
            self.logger.warning(
                "cost_history_save_failed",
                account_id=account_id,
                error=str(e)
            )

    def _publish_event(
        self,
        anomaly: AnomalyDetail,
        account_id: str,
        account_alias: str
    ) -> None:
        """EventBridge에 이벤트 발행."""
        try:
            # 심각도에 따른 이벤트 타입
            if anomaly.severity == "high":
                detail_type = "COST_ALERT_HIGH"
            elif anomaly.severity == "medium":
                detail_type = "COST_ALERT_MEDIUM"
            else:
                detail_type = "COST_ANOMALY_DETECTED"

            event_detail = {
                "anomaly_id": anomaly.anomaly_id,
                "account_id": account_id,
                "account_alias": account_alias,
                "service_name": anomaly.service_name,
                "severity": anomaly.severity,
                "confidence_score": anomaly.confidence_score,
                "current_cost": anomaly.current_cost,
                "previous_cost": anomaly.previous_cost,
                "cost_change_percent": anomaly.cost_change_ratio * 100,
                "detected_methods": anomaly.detected_methods,
                "analysis": anomaly.analysis,
                "date": anomaly.date,
                "detected_at": datetime.utcnow().isoformat()
            }

            self.aws_client.eventbridge.put_events(
                entries=[{
                    'Source': self.event_source,
                    'DetailType': detail_type,
                    'Detail': json.dumps(event_detail),
                    'EventBusName': self.event_bus
                }]
            )

            self.logger.info(
                "event_published",
                detail_type=detail_type,
                anomaly_id=anomaly.anomaly_id
            )
        except Exception as e:
            self.logger.warning(
                "event_publish_failed",
                anomaly_id=anomaly.anomaly_id,
                error=str(e)
            )


# Lambda 진입점
handler_instance = CostDetectionHandler()


@lambda_handler_wrapper
def lambda_handler(event: Dict, context: Any, log) -> Dict:
    return handler_instance.handle(event, context)


# 로컬 테스트
if __name__ == "__main__":
    import os

    # Mock 모드로 테스트
    os.environ['AWS_MOCK'] = 'true'

    test_event = {
        "start_date": "2024-01-01",
        "end_date": "2024-01-15",
        "granularity": "DAILY",
        "group_by": ["SERVICE"],
        "thresholds": {
            "ratio_threshold": 0.3,
            "stddev_multiplier": 2.0
        }
    }

    # Context mock
    class MockContext:
        aws_request_id = "test-request-id"

    result = lambda_handler(test_event, MockContext())
    print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))
