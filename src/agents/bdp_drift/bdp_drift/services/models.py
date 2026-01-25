"""
BDP Drift Agent Models.

데이터 모델 및 열거형 정의.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ResourceType(str, Enum):
    """지원 리소스 타입."""

    # Primary (데이터레이크 핵심)
    GLUE = "glue"           # Glue Catalogue
    ATHENA = "athena"       # Athena 워크그룹
    EMR = "emr"             # EMR 클러스터/서버리스
    SAGEMAKER = "sagemaker" # SageMaker 엔드포인트/파이프라인/노트북

    # Secondary (인프라 지원)
    S3 = "s3"               # S3 버킷
    MWAA = "mwaa"           # MWAA 환경
    MSK = "msk"             # MSK 클러스터
    LAMBDA = "lambda"       # Lambda 함수


class DriftSeverity(str, Enum):
    """드리프트 심각도."""

    CRITICAL = "critical"   # 즉시 조치 필요
    HIGH = "high"           # 빠른 확인 필요
    MEDIUM = "medium"       # 모니터링 필요
    LOW = "low"             # 참고용


class ChangeType(str, Enum):
    """변경 타입."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


@dataclass
class Baseline:
    """베이스라인 설정."""

    resource_type: str
    resource_id: str
    version: int
    config: Dict[str, Any]
    config_hash: str
    resource_arn: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    @staticmethod
    def compute_hash(config: Dict[str, Any]) -> str:
        """설정의 SHA256 해시 계산.

        Args:
            config: 설정 딕셔너리

        Returns:
            SHA256 해시 문자열
        """
        config_str = json.dumps(config, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(config_str.encode()).hexdigest()


@dataclass
class BaselineCreate:
    """베이스라인 생성 요청."""

    resource_type: str
    resource_id: str
    config: Dict[str, Any]
    resource_arn: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[Dict[str, str]] = None


@dataclass
class BaselineHistory:
    """베이스라인 변경 이력."""

    id: str
    resource_type: str
    resource_id: str
    version: int
    change_type: str
    previous_config: Optional[Dict[str, Any]]
    current_config: Dict[str, Any]
    config_hash: str
    change_reason: Optional[str] = None
    changed_at: Optional[datetime] = None
    changed_by: Optional[str] = None


@dataclass
class DriftField:
    """개별 필드 드리프트."""

    field_name: str
    baseline_value: Any
    current_value: Any
    severity: DriftSeverity
    description: Optional[str] = None


@dataclass
class DriftResult:
    """드리프트 탐지 결과."""

    resource_type: str
    resource_id: str
    resource_arn: Optional[str]
    has_drift: bool
    severity: DriftSeverity
    drift_fields: List[DriftField] = field(default_factory=list)
    baseline_config: Dict[str, Any] = field(default_factory=dict)
    current_config: Dict[str, Any] = field(default_factory=dict)
    baseline_version: int = 0
    detection_timestamp: Optional[datetime] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    confidence_score: float = 1.0
    detection_method: str = "direct_comparison"

    @property
    def drift_count(self) -> int:
        """드리프트 필드 수."""
        return len(self.drift_fields)

    @property
    def critical_count(self) -> int:
        """CRITICAL 드리프트 수."""
        return len([f for f in self.drift_fields if f.severity == DriftSeverity.CRITICAL])

    @property
    def high_count(self) -> int:
        """HIGH 드리프트 수."""
        return len([f for f in self.drift_fields if f.severity == DriftSeverity.HIGH])

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_arn": self.resource_arn,
            "has_drift": self.has_drift,
            "severity": self.severity.value,
            "drift_count": self.drift_count,
            "drift_fields": [
                {
                    "field_name": f.field_name,
                    "baseline_value": f.baseline_value,
                    "current_value": f.current_value,
                    "severity": f.severity.value,
                    "description": f.description,
                }
                for f in self.drift_fields
            ],
            "baseline_version": self.baseline_version,
            "detection_timestamp": (
                self.detection_timestamp.isoformat()
                if self.detection_timestamp
                else None
            ),
            "account_id": self.account_id,
            "account_name": self.account_name,
            "confidence_score": self.confidence_score,
        }


# Severity 매핑 (필드별 심각도)
FIELD_SEVERITY_MAPPING: Dict[str, DriftSeverity] = {
    # CRITICAL - 데이터 무결성/보안
    "table_schema": DriftSeverity.CRITICAL,
    "columns": DriftSeverity.CRITICAL,
    "encryption_configuration": DriftSeverity.CRITICAL,
    "s3_encryption": DriftSeverity.CRITICAL,
    "server_side_encryption": DriftSeverity.CRITICAL,
    "endpoint_config": DriftSeverity.CRITICAL,
    "iam_role": DriftSeverity.CRITICAL,
    "role_arn": DriftSeverity.CRITICAL,
    "execution_role": DriftSeverity.CRITICAL,
    "kms_key": DriftSeverity.CRITICAL,
    "security_configuration": DriftSeverity.CRITICAL,
    "public_access_block": DriftSeverity.CRITICAL,

    # HIGH - 버전/런타임
    "release_label": DriftSeverity.HIGH,
    "runtime": DriftSeverity.HIGH,
    "airflow_version": DriftSeverity.HIGH,
    "kafka_version": DriftSeverity.HIGH,
    "instance_type": DriftSeverity.HIGH,
    "instance_class": DriftSeverity.HIGH,
    "engine_type": DriftSeverity.HIGH,
    "handler": DriftSeverity.HIGH,
    "layers": DriftSeverity.HIGH,

    # MEDIUM - 용량/스케일
    "memory_size": DriftSeverity.MEDIUM,
    "timeout": DriftSeverity.MEDIUM,
    "min_workers": DriftSeverity.MEDIUM,
    "max_workers": DriftSeverity.MEDIUM,
    "min_capacity": DriftSeverity.MEDIUM,
    "max_capacity": DriftSeverity.MEDIUM,
    "number_of_broker_nodes": DriftSeverity.MEDIUM,
    "volume_size": DriftSeverity.MEDIUM,
    "environment_class": DriftSeverity.MEDIUM,

    # LOW - 메타데이터
    "tags": DriftSeverity.LOW,
    "description": DriftSeverity.LOW,
    "comment": DriftSeverity.LOW,
    "parameters": DriftSeverity.LOW,
}


def get_field_severity(field_name: str) -> DriftSeverity:
    """필드명에 대한 심각도 반환.

    Args:
        field_name: 필드명

    Returns:
        심각도 (기본값: MEDIUM)
    """
    # 직접 매핑 확인
    if field_name in FIELD_SEVERITY_MAPPING:
        return FIELD_SEVERITY_MAPPING[field_name]

    # 패턴 매칭
    field_lower = field_name.lower()

    if any(k in field_lower for k in ["encrypt", "kms", "security", "iam", "role", "public"]):
        return DriftSeverity.CRITICAL

    if any(k in field_lower for k in ["version", "runtime", "instance", "type"]):
        return DriftSeverity.HIGH

    if any(k in field_lower for k in ["size", "capacity", "worker", "memory", "timeout"]):
        return DriftSeverity.MEDIUM

    if any(k in field_lower for k in ["tag", "description", "comment", "name"]):
        return DriftSeverity.LOW

    return DriftSeverity.MEDIUM
