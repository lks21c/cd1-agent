#!/usr/bin/env python3
"""
Test script for BDP Drift HTML Report.

다양한 드리프트 시나리오를 포함한 HTML 리포트 생성 테스트.
8개 리소스 타입 × 다양한 필드 변경 시나리오.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.bdp_drift.bdp_drift.services.models import (
    DriftCategory,
    DriftField,
    DriftResult,
    DriftSeverity,
)
from src.agents.bdp_drift.bdp_drift.services.html_report_generator import (
    generate_drift_report,
)


def create_mock_drift_results() -> list[DriftResult]:
    """20개 이상의 다양한 DriftResult 생성."""
    now = datetime.utcnow()
    results = []

    # 다양한 baseline_timestamp 패턴
    from datetime import timedelta
    baseline_15d_ago = now - timedelta(days=15)
    baseline_7d_ago = now - timedelta(days=7)
    baseline_30d_ago = now - timedelta(days=30)
    baseline_1d_ago = now - timedelta(days=1)
    baseline_3h_ago = now - timedelta(hours=3)

    # ============================================================
    # 1. Glue Catalog - 스키마 변경 (CRITICAL) - 30일 전 베이스라인
    # ============================================================
    results.append(DriftResult(
        resource_type="glue",
        resource_id="database/sales_db/table/orders",
        resource_arn="arn:aws:glue:ap-northeast-2:123456789012:table/sales_db/orders",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            DriftField(
                field_name="columns",
                baseline_value=[
                    {"Name": "order_id", "Type": "bigint"},
                    {"Name": "amount", "Type": "string"},
                ],
                current_value=[
                    {"Name": "order_id", "Type": "bigint"},
                    {"Name": "amount", "Type": "bigint"},
                    {"Name": "created_at", "Type": "timestamp"},
                ],
                severity=DriftSeverity.CRITICAL,
                description="스키마 변경 감지: amount 컬럼 타입 변경 (string→bigint), created_at 컬럼 추가",
                impact="데이터 파이프라인 실패 가능성, 다운스트림 ETL 작업 및 Athena 쿼리 오류 위험",
                recommendation="즉시 ETL 작업 검토, 영향받는 쿼리 확인, 데이터 타입 호환성 검증 필요",
            ),
        ],
        baseline_version=3,
        detection_timestamp=now,
        baseline_timestamp=baseline_30d_ago,  # 30일 전 베이스라인
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 2. Glue Catalog - 테이블 타입 변경 (HIGH)
    results.append(DriftResult(
        resource_type="glue",
        resource_id="database/analytics_db/table/user_events",
        resource_arn="arn:aws:glue:ap-northeast-2:123456789012:table/analytics_db/user_events",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            DriftField(
                field_name="table_type",
                baseline_value="EXTERNAL_TABLE",
                current_value="VIRTUAL_VIEW",
                severity=DriftSeverity.HIGH,
                description="테이블 타입이 EXTERNAL_TABLE에서 VIRTUAL_VIEW로 변경됨",
                impact="S3 데이터 접근 방식 변경, 기존 쿼리 성능 저하 가능성",
                recommendation="테이블 타입 변경 사유 확인, 관련 ETL 파이프라인 영향도 분석",
            ),
        ],
        baseline_version=5,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 3. Glue Catalog - 파티션 키 변경 (CRITICAL)
    results.append(DriftResult(
        resource_type="glue",
        resource_id="database/logs_db/table/access_logs",
        resource_arn="arn:aws:glue:ap-northeast-2:123456789012:table/logs_db/access_logs",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            DriftField(
                field_name="partition_keys",
                baseline_value=[{"Name": "year", "Type": "string"}, {"Name": "month", "Type": "string"}],
                current_value=[{"Name": "dt", "Type": "string"}],
                severity=DriftSeverity.CRITICAL,
                description="파티션 키가 year/month에서 dt로 변경됨",
                impact="기존 파티션 데이터 접근 불가, 모든 파티션 재생성 필요",
                recommendation="긴급 롤백 검토, 파티션 마이그레이션 계획 수립, 다운스트림 시스템 알림",
            ),
        ],
        baseline_version=2,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # ============================================================
    # 4. Athena - 스캔 제한 변경 (MEDIUM) - 7일 전 베이스라인
    # ============================================================
    results.append(DriftResult(
        resource_type="athena",
        resource_id="workgroup/analytics-team",
        resource_arn="arn:aws:athena:ap-northeast-2:123456789012:workgroup/analytics-team",
        has_drift=True,
        severity=DriftSeverity.MEDIUM,
        drift_fields=[
            DriftField(
                field_name="bytes_scanned_cutoff",
                baseline_value=10737418240,  # 10GB
                current_value=107374182400,  # 100GB
                severity=DriftSeverity.MEDIUM,
                description="쿼리 스캔 제한이 10GB에서 100GB로 증가",
                impact="쿼리 비용 증가 가능성, 비효율적 쿼리 실행 허용",
                recommendation="스캔 제한 증가 사유 확인, 쿼리 최적화 교육 필요",
            ),
        ],
        baseline_version=1,
        detection_timestamp=now,
        baseline_timestamp=baseline_7d_ago,  # 7일 전 베이스라인
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 5. Athena - 암호화 설정 변경 (CRITICAL) - 15일 전 베이스라인
    results.append(DriftResult(
        resource_type="athena",
        resource_id="workgroup/secure-analytics",
        resource_arn="arn:aws:athena:ap-northeast-2:123456789012:workgroup/secure-analytics",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            DriftField(
                field_name="encryption_configuration",
                baseline_value={"EncryptionOption": "SSE_KMS", "KmsKey": "arn:aws:kms:..."},
                current_value=None,
                severity=DriftSeverity.CRITICAL,
                description="쿼리 결과 암호화가 비활성화됨",
                impact="민감 데이터 노출 위험, 규정 준수 위반 가능성",
                recommendation="즉시 암호화 설정 복원, 보안팀 알림, 감사 로그 검토",
            ),
            DriftField(
                field_name="enforce_workgroup_configuration",
                baseline_value=True,
                current_value=False,
                severity=DriftSeverity.HIGH,
                description="워크그룹 설정 강제가 비활성화됨",
                impact="사용자가 워크그룹 설정을 무시하고 쿼리 실행 가능",
                recommendation="강제 설정 복원, 워크그룹 정책 재검토",
            ),
        ],
        baseline_version=4,
        detection_timestamp=now,
        baseline_timestamp=baseline_15d_ago,  # 15일 전 베이스라인
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # ============================================================
    # 6. EMR - 버전 업그레이드 (HIGH)
    # ============================================================
    results.append(DriftResult(
        resource_type="emr",
        resource_id="cluster/j-1234567890ABC",
        resource_arn="arn:aws:elasticmapreduce:ap-northeast-2:123456789012:cluster/j-1234567890ABC",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            DriftField(
                field_name="release_label",
                baseline_value="emr-6.10.0",
                current_value="emr-7.0.0",
                severity=DriftSeverity.HIGH,
                description="EMR 버전이 6.10.0에서 7.0.0으로 업그레이드됨",
                impact="Spark/Hive API 호환성 문제 가능, 기존 스크립트 수정 필요",
                recommendation="업그레이드 릴리스 노트 검토, 기존 작업 호환성 테스트 수행",
            ),
        ],
        baseline_version=2,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 7. EMR - 인스턴스 타입 변경 (HIGH)
    results.append(DriftResult(
        resource_type="emr",
        resource_id="cluster/j-ABCDEF123456",
        resource_arn="arn:aws:elasticmapreduce:ap-northeast-2:123456789012:cluster/j-ABCDEF123456",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            DriftField(
                field_name="master_instance_type",
                baseline_value="m5.xlarge",
                current_value="m5.2xlarge",
                severity=DriftSeverity.MEDIUM,
                description="마스터 노드 인스턴스 타입 변경",
                impact="비용 증가, 리소스 할당 변경",
                recommendation="비용 영향 검토, 필요시 원복",
            ),
            DriftField(
                field_name="core_instance_type",
                baseline_value="r5.2xlarge",
                current_value="r5.4xlarge",
                severity=DriftSeverity.HIGH,
                description="코어 노드 인스턴스 타입이 2배 증가",
                impact="시간당 비용 2배 증가, 메모리 및 CPU 리소스 증가",
                recommendation="성능 요구사항 확인, 비용 최적화 검토",
            ),
        ],
        baseline_version=3,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 8. EMR - 보안 설정 변경 (CRITICAL)
    results.append(DriftResult(
        resource_type="emr",
        resource_id="cluster/j-SECURE123456",
        resource_arn="arn:aws:elasticmapreduce:ap-northeast-2:123456789012:cluster/j-SECURE123456",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            DriftField(
                field_name="security_configuration",
                baseline_value="emr-encryption-config",
                current_value=None,
                severity=DriftSeverity.CRITICAL,
                description="보안 구성이 제거됨 (암호화 비활성화)",
                impact="저장 데이터 및 전송 데이터 암호화 해제, 보안 규정 위반",
                recommendation="즉시 보안 구성 복원, 보안팀 에스컬레이션, 영향받는 데이터 식별",
            ),
        ],
        baseline_version=1,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # ============================================================
    # 9. S3 - 퍼블릭 액세스 변경 (CRITICAL) - 1일 전 베이스라인
    # ============================================================
    results.append(DriftResult(
        resource_type="s3",
        resource_id="bucket/datalake-raw-prod",
        resource_arn="arn:aws:s3:::datalake-raw-prod",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            DriftField(
                field_name="public_access_block",
                baseline_value={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
                current_value={
                    "BlockPublicAcls": False,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
                severity=DriftSeverity.CRITICAL,
                description="BlockPublicAcls가 비활성화됨 - 퍼블릭 ACL 설정 허용",
                impact="버킷 또는 객체에 퍼블릭 ACL 적용 가능, 데이터 노출 위험",
                recommendation="즉시 퍼블릭 액세스 차단 복원, 기존 ACL 감사, 보안팀 알림",
            ),
        ],
        baseline_version=5,
        detection_timestamp=now,
        baseline_timestamp=baseline_1d_ago,  # 1일 전 베이스라인
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 10. S3 - 암호화 변경 (CRITICAL)
    results.append(DriftResult(
        resource_type="s3",
        resource_id="bucket/datalake-curated-prod",
        resource_arn="arn:aws:s3:::datalake-curated-prod",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            DriftField(
                field_name="server_side_encryption",
                baseline_value={"SSEAlgorithm": "aws:kms", "KMSMasterKeyID": "arn:aws:kms:..."},
                current_value=None,
                severity=DriftSeverity.CRITICAL,
                description="기본 암호화가 비활성화됨",
                impact="새로 저장되는 객체가 암호화되지 않음, 규정 준수 위반",
                recommendation="즉시 암호화 설정 복원, 비암호화 객체 식별 및 암호화",
            ),
        ],
        baseline_version=3,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 11. S3 - 버전 관리 비활성화 (HIGH)
    results.append(DriftResult(
        resource_type="s3",
        resource_id="bucket/datalake-archive-prod",
        resource_arn="arn:aws:s3:::datalake-archive-prod",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            DriftField(
                field_name="versioning",
                baseline_value="Enabled",
                current_value="Suspended",
                severity=DriftSeverity.HIGH,
                description="버전 관리가 일시 중지됨",
                impact="객체 삭제 시 복구 불가, 덮어쓰기 시 이전 버전 손실",
                recommendation="버전 관리 재활성화, 중요 데이터 백업 확인",
            ),
        ],
        baseline_version=2,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # ============================================================
    # 12. SageMaker - 엔드포인트 설정 변경 (CRITICAL)
    # ============================================================
    results.append(DriftResult(
        resource_type="sagemaker",
        resource_id="endpoint/fraud-detection-prod",
        resource_arn="arn:aws:sagemaker:ap-northeast-2:123456789012:endpoint/fraud-detection-prod",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            DriftField(
                field_name="endpoint_config",
                baseline_value="fraud-detection-config-v2",
                current_value="fraud-detection-config-v3",
                severity=DriftSeverity.CRITICAL,
                description="엔드포인트 구성이 v2에서 v3로 변경됨",
                impact="모델 버전 변경, 예측 결과 변동 가능성, 비즈니스 영향",
                recommendation="모델 성능 검증, A/B 테스트 결과 확인, 변경 승인 기록 검토",
            ),
            DriftField(
                field_name="instance_count",
                baseline_value=4,
                current_value=2,
                severity=DriftSeverity.HIGH,
                description="인스턴스 수가 4개에서 2개로 감소",
                impact="처리 용량 50% 감소, 트래픽 증가 시 지연 발생 가능",
                recommendation="트래픽 패턴 분석, 오토스케일링 설정 검토",
            ),
        ],
        baseline_version=7,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-ml",
    ))

    # 13. SageMaker - IAM 역할 변경 (CRITICAL)
    results.append(DriftResult(
        resource_type="sagemaker",
        resource_id="notebook/data-science-team",
        resource_arn="arn:aws:sagemaker:ap-northeast-2:123456789012:notebook-instance/data-science-team",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            DriftField(
                field_name="execution_role",
                baseline_value="arn:aws:iam::123456789012:role/SageMakerNotebookRole",
                current_value="arn:aws:iam::123456789012:role/AdminRole",
                severity=DriftSeverity.CRITICAL,
                description="실행 역할이 관리자 역할로 변경됨",
                impact="과도한 권한 부여, 보안 위험 증가, 최소 권한 원칙 위반",
                recommendation="즉시 원래 역할로 복원, 변경 사유 조사, 접근 로그 검토",
            ),
        ],
        baseline_version=4,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-ml",
    ))

    # ============================================================
    # 14. MWAA - Airflow 버전 변경 (HIGH)
    # ============================================================
    results.append(DriftResult(
        resource_type="mwaa",
        resource_id="environment/data-pipeline-prod",
        resource_arn="arn:aws:airflow:ap-northeast-2:123456789012:environment/data-pipeline-prod",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            DriftField(
                field_name="airflow_version",
                baseline_value="2.5.1",
                current_value="2.7.3",
                severity=DriftSeverity.HIGH,
                description="Airflow 버전이 2.5.1에서 2.7.3으로 업그레이드됨",
                impact="DAG 호환성 문제 가능, 일부 오퍼레이터 동작 변경",
                recommendation="업그레이드 릴리스 노트 검토, DAG 호환성 테스트, 롤백 계획 준비",
            ),
        ],
        baseline_version=2,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 15. MWAA - 워커 수 변경 (MEDIUM)
    results.append(DriftResult(
        resource_type="mwaa",
        resource_id="environment/etl-scheduler-prod",
        resource_arn="arn:aws:airflow:ap-northeast-2:123456789012:environment/etl-scheduler-prod",
        has_drift=True,
        severity=DriftSeverity.MEDIUM,
        drift_fields=[
            DriftField(
                field_name="min_workers",
                baseline_value=2,
                current_value=1,
                severity=DriftSeverity.MEDIUM,
                description="최소 워커 수가 2에서 1로 감소",
                impact="동시 태스크 처리 능력 감소, 피크 시간대 병목 가능",
                recommendation="DAG 실행 패턴 분석, 필요시 워커 수 복원",
            ),
            DriftField(
                field_name="max_workers",
                baseline_value=10,
                current_value=5,
                severity=DriftSeverity.MEDIUM,
                description="최대 워커 수가 10에서 5로 감소",
                impact="스케일 아웃 한계 감소, 대량 작업 시 지연 발생 가능",
                recommendation="워크로드 요구사항 검토, 비용-성능 균형 분석",
            ),
        ],
        baseline_version=3,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # ============================================================
    # 16. MSK - Kafka 버전 변경 (HIGH)
    # ============================================================
    results.append(DriftResult(
        resource_type="msk",
        resource_id="cluster/event-streaming-prod",
        resource_arn="arn:aws:kafka:ap-northeast-2:123456789012:cluster/event-streaming-prod",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            DriftField(
                field_name="kafka_version",
                baseline_value="2.8.1",
                current_value="3.4.0",
                severity=DriftSeverity.HIGH,
                description="Kafka 버전이 2.8.1에서 3.4.0으로 업그레이드됨",
                impact="클라이언트 호환성 문제 가능, 프로듀서/컨슈머 라이브러리 업데이트 필요",
                recommendation="클라이언트 애플리케이션 호환성 테스트, 단계적 롤아웃",
            ),
        ],
        baseline_version=4,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-streaming",
    ))

    # 17. MSK - 브로커 수 변경 (MEDIUM)
    results.append(DriftResult(
        resource_type="msk",
        resource_id="cluster/log-aggregation-prod",
        resource_arn="arn:aws:kafka:ap-northeast-2:123456789012:cluster/log-aggregation-prod",
        has_drift=True,
        severity=DriftSeverity.MEDIUM,
        drift_fields=[
            DriftField(
                field_name="number_of_broker_nodes",
                baseline_value=6,
                current_value=3,
                severity=DriftSeverity.MEDIUM,
                description="브로커 노드 수가 6에서 3으로 감소",
                impact="가용성 감소, 파티션 리밸런싱 발생, 처리량 제한",
                recommendation="토픽 파티션 분산 확인, 가용성 요구사항 검토",
            ),
            DriftField(
                field_name="volume_size",
                baseline_value=500,
                current_value=250,
                severity=DriftSeverity.MEDIUM,
                description="EBS 볼륨 크기가 500GB에서 250GB로 감소",
                impact="저장 용량 감소, 리텐션 정책 조정 필요",
                recommendation="로그 리텐션 정책 검토, 스토리지 사용량 모니터링 강화",
            ),
        ],
        baseline_version=2,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-streaming",
    ))

    # ============================================================
    # 18. Lambda - 런타임 변경 (HIGH)
    # ============================================================
    results.append(DriftResult(
        resource_type="lambda",
        resource_id="function/data-processor-prod",
        resource_arn="arn:aws:lambda:ap-northeast-2:123456789012:function:data-processor-prod",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            DriftField(
                field_name="runtime",
                baseline_value="python3.9",
                current_value="python3.12",
                severity=DriftSeverity.HIGH,
                description="Python 런타임이 3.9에서 3.12로 변경됨",
                impact="일부 라이브러리 호환성 문제 가능, 성능 변화",
                recommendation="의존성 호환성 확인, 테스트 실행, 점진적 배포",
            ),
        ],
        baseline_version=8,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 19. Lambda - 핸들러 변경 (HIGH)
    results.append(DriftResult(
        resource_type="lambda",
        resource_id="function/event-trigger-prod",
        resource_arn="arn:aws:lambda:ap-northeast-2:123456789012:function:event-trigger-prod",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            DriftField(
                field_name="handler",
                baseline_value="app.handlers.main.handler",
                current_value="app.handlers.v2.new_handler",
                severity=DriftSeverity.HIGH,
                description="핸들러 경로가 변경됨",
                impact="함수 진입점 변경, 기존 로직과 다른 동작 가능",
                recommendation="새 핸들러 코드 검토, 기능 검증 테스트 수행",
            ),
            DriftField(
                field_name="layers",
                baseline_value=["arn:aws:lambda:...:layer/common-utils:5"],
                current_value=["arn:aws:lambda:...:layer/common-utils:7", "arn:aws:lambda:...:layer/monitoring:2"],
                severity=DriftSeverity.MEDIUM,
                description="Lambda 레이어 변경: 버전 업데이트 및 새 레이어 추가",
                impact="의존성 변경, 함수 크기 증가",
                recommendation="레이어 변경 사항 검토, 콜드 스타트 시간 측정",
            ),
        ],
        baseline_version=5,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 20. Lambda - 메모리 변경 (MEDIUM) - 15일 전 베이스라인 (핵심 테스트 케이스)
    results.append(DriftResult(
        resource_type="lambda",
        resource_id="function/batch-processor-prod",
        resource_arn="arn:aws:lambda:ap-northeast-2:123456789012:function:batch-processor-prod",
        has_drift=True,
        severity=DriftSeverity.MEDIUM,
        drift_fields=[
            DriftField(
                field_name="memory_size",
                baseline_value=1024,
                current_value=512,
                severity=DriftSeverity.MEDIUM,
                description="메모리가 1024MB에서 512MB로 감소",
                impact="처리 성능 저하 가능, 대용량 데이터 처리 시 OOM 위험",
                recommendation="메모리 사용량 모니터링, 필요시 메모리 복원",
            ),
            DriftField(
                field_name="timeout",
                baseline_value=300,
                current_value=60,
                severity=DriftSeverity.MEDIUM,
                description="타임아웃이 300초에서 60초로 감소",
                impact="장시간 작업 실패 가능성 증가",
                recommendation="실행 시간 분포 분석, 적절한 타임아웃 설정",
            ),
        ],
        baseline_version=6,
        detection_timestamp=now,
        baseline_timestamp=baseline_15d_ago,  # 15일 전 베이스라인 (핵심 테스트)
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 21. Lambda - IAM 역할 변경 (CRITICAL) - 3시간 전 베이스라인 (최근 변경)
    results.append(DriftResult(
        resource_type="lambda",
        resource_id="function/s3-processor-prod",
        resource_arn="arn:aws:lambda:ap-northeast-2:123456789012:function:s3-processor-prod",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            DriftField(
                field_name="role_arn",
                baseline_value="arn:aws:iam::123456789012:role/LambdaS3ReadRole",
                current_value="arn:aws:iam::123456789012:role/LambdaFullAccessRole",
                severity=DriftSeverity.CRITICAL,
                description="실행 역할이 S3 읽기 전용에서 전체 액세스로 변경됨",
                impact="과도한 권한 부여, 보안 위험 증가, 최소 권한 원칙 위반",
                recommendation="즉시 원래 역할로 복원, 권한 상승 원인 조사, 보안 감사",
            ),
        ],
        baseline_version=3,
        detection_timestamp=now,
        baseline_timestamp=baseline_3h_ago,  # 3시간 전 베이스라인 (최근 변경)
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 22. 드리프트 없는 정상 리소스 (테스트용)
    results.append(DriftResult(
        resource_type="s3",
        resource_id="bucket/datalake-staging",
        resource_arn="arn:aws:s3:::datalake-staging",
        has_drift=False,
        severity=DriftSeverity.LOW,
        drift_fields=[],
        baseline_version=2,
        detection_timestamp=now,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # ============================================================
    # DISCOVERED 필드 테스트 케이스 (모니터링 vs 발견 구분)
    # ============================================================

    # 23. Glue - MONITORED + DISCOVERED 혼합 케이스
    results.append(DriftResult(
        resource_type="glue",
        resource_id="database/test_db/table/mixed_changes",
        resource_arn="arn:aws:glue:ap-northeast-2:123456789012:table/test_db/mixed_changes",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            # MONITORED: 베이스라인에 있던 필드 값 변경
            DriftField(
                field_name="table_type",
                baseline_value="EXTERNAL_TABLE",
                current_value="MANAGED_TABLE",
                severity=DriftSeverity.HIGH,
                category=DriftCategory.MONITORED,
                description="테이블 타입이 EXTERNAL_TABLE에서 MANAGED_TABLE로 변경됨 (모니터링 대상)",
                impact="S3 데이터 관리 방식 변경, 데이터 삭제 시 실제 파일 삭제됨",
                recommendation="테이블 타입 변경 사유 확인, 백업 정책 검토",
            ),
            DriftField(
                field_name="retention",
                baseline_value=30,
                current_value=7,
                severity=DriftSeverity.MEDIUM,
                category=DriftCategory.MONITORED,
                description="데이터 보존 기간이 30일에서 7일로 감소 (모니터링 대상)",
                impact="오래된 데이터 조기 삭제, 데이터 복구 기간 단축",
                recommendation="보존 정책 변경 승인 확인, 필요시 복원",
            ),
            # DISCOVERED: 새로 추가된 필드
            DriftField(
                field_name="new_metadata_field",
                baseline_value=None,
                current_value={"owner": "data-team", "priority": "high"},
                severity=DriftSeverity.LOW,
                category=DriftCategory.DISCOVERED,
                description="필드가 추가되었습니다: new_metadata_field (발견됨)",
            ),
            # DISCOVERED: 삭제된 필드
            DriftField(
                field_name="deprecated_config",
                baseline_value={"legacy": True},
                current_value=None,
                severity=DriftSeverity.LOW,
                category=DriftCategory.DISCOVERED,
                description="필드가 삭제되었습니다: deprecated_config (발견됨)",
            ),
        ],
        baseline_version=4,
        detection_timestamp=now,
        baseline_timestamp=baseline_7d_ago,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 24. Lambda - DISCOVERED만 있는 케이스 (심각도 LOW로 유지되어야 함)
    results.append(DriftResult(
        resource_type="lambda",
        resource_id="function/discovery-only-test",
        resource_arn="arn:aws:lambda:ap-northeast-2:123456789012:function:discovery-only-test",
        has_drift=True,
        severity=DriftSeverity.LOW,  # DISCOVERED만 있으므로 LOW
        drift_fields=[
            DriftField(
                field_name="new_environment_var",
                baseline_value=None,
                current_value="DEBUG=true",
                severity=DriftSeverity.MEDIUM,  # 개별 심각도는 MEDIUM이지만 DISCOVERED이므로 전체 심각도에 영향 없음
                category=DriftCategory.DISCOVERED,
                description="필드가 추가되었습니다: new_environment_var",
            ),
            DriftField(
                field_name="old_tag",
                baseline_value="deprecated",
                current_value=None,
                severity=DriftSeverity.LOW,
                category=DriftCategory.DISCOVERED,
                description="필드가 삭제되었습니다: old_tag",
            ),
        ],
        baseline_version=2,
        detection_timestamp=now,
        baseline_timestamp=baseline_1d_ago,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    # 25. S3 - CRITICAL MONITORED + 여러 DISCOVERED
    results.append(DriftResult(
        resource_type="s3",
        resource_id="bucket/critical-with-discoveries",
        resource_arn="arn:aws:s3:::critical-with-discoveries",
        has_drift=True,
        severity=DriftSeverity.CRITICAL,
        drift_fields=[
            # CRITICAL MONITORED 필드
            DriftField(
                field_name="public_access_block",
                baseline_value={"BlockPublicAcls": True, "BlockPublicPolicy": True},
                current_value={"BlockPublicAcls": False, "BlockPublicPolicy": False},
                severity=DriftSeverity.CRITICAL,
                category=DriftCategory.MONITORED,
                description="퍼블릭 액세스 차단이 비활성화됨 (모니터링 대상)",
                impact="버킷 및 객체에 퍼블릭 액세스 허용, 데이터 노출 위험",
                recommendation="즉시 퍼블릭 액세스 차단 복원, 보안팀 알림",
            ),
            # 여러 DISCOVERED 필드들
            DriftField(
                field_name="new_lifecycle_rule",
                baseline_value=None,
                current_value={"ID": "archive-rule", "Status": "Enabled"},
                severity=DriftSeverity.LOW,
                category=DriftCategory.DISCOVERED,
                description="필드가 추가되었습니다: new_lifecycle_rule",
            ),
            DriftField(
                field_name="new_cors_config",
                baseline_value=None,
                current_value={"AllowedOrigins": ["*"]},
                severity=DriftSeverity.MEDIUM,
                category=DriftCategory.DISCOVERED,
                description="필드가 추가되었습니다: new_cors_config",
            ),
            DriftField(
                field_name="removed_notification",
                baseline_value={"LambdaFunctionArn": "arn:aws:lambda:..."},
                current_value=None,
                severity=DriftSeverity.LOW,
                category=DriftCategory.DISCOVERED,
                description="필드가 삭제되었습니다: removed_notification",
            ),
        ],
        baseline_version=6,
        detection_timestamp=now,
        baseline_timestamp=baseline_3h_ago,
        account_id="123456789012",
        account_name="prod-datalake",
    ))

    return results


def main():
    """메인 함수 - HTML 리포트 생성 및 브라우저에서 열기."""
    print("=" * 60)
    print("BDP Drift HTML Report Test")
    print("=" * 60)

    # Mock 데이터 생성
    print("\n1. Creating mock drift results...")
    results = create_mock_drift_results()
    print(f"   - Total results: {len(results)}")
    print(f"   - With drift: {len([r for r in results if r.has_drift])}")

    # 리소스 타입별 통계
    by_type = {}
    for r in results:
        if r.has_drift:
            by_type[r.resource_type] = by_type.get(r.resource_type, 0) + 1
    print("\n   Resource type distribution:")
    for rtype, count in sorted(by_type.items()):
        print(f"     - {rtype}: {count}")

    # HTML 리포트 생성
    print("\n2. Generating HTML report...")
    output_dir = project_root / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "drift_report_test.html"

    report_path = generate_drift_report(results, str(output_path))
    print(f"   - Report saved to: {report_path}")

    # Chrome에서 열기
    print("\n3. Opening in Chrome...")
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-a", "Google Chrome", str(output_path)], check=True)
        elif sys.platform == "linux":
            subprocess.run(["google-chrome", str(output_path)], check=True)
        elif sys.platform == "win32":
            os.startfile(str(output_path))
        print("   - Opened in browser successfully")
    except Exception as e:
        print(f"   - Could not open browser: {e}")
        print(f"   - Please open manually: {output_path}")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
