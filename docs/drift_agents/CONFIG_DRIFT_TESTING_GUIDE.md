# BDP Drift Assertion Testing Guide

드리프트 탐지 결과의 assertion 및 검증 방법 가이드.

## 1. DriftResult 모델 구조

`DriftResult`는 드리프트 탐지의 최종 결과를 나타내는 데이터클래스입니다.

### 1.1 주요 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `resource_type` | `str` | 리소스 타입 (glue, athena, emr 등) |
| `resource_id` | `str` | 리소스 식별자 |
| `resource_arn` | `Optional[str]` | AWS ARN |
| `has_drift` | `bool` | 드리프트 존재 여부 |
| `severity` | `DriftSeverity` | 전체 드리프트 심각도 |
| `drift_fields` | `List[DriftField]` | 개별 드리프트 필드 목록 |
| `baseline_config` | `Dict[str, Any]` | 베이스라인 설정 |
| `current_config` | `Dict[str, Any]` | 현재 설정 |
| `baseline_version` | `int` | 베이스라인 버전 |
| `detection_timestamp` | `Optional[datetime]` | 탐지 시각 |
| `baseline_timestamp` | `Optional[datetime]` | 베이스라인 설정 시각 |
| `account_id` | `Optional[str]` | AWS 계정 ID |
| `account_name` | `Optional[str]` | AWS 계정 이름 |
| `confidence_score` | `float` | 탐지 신뢰도 (기본값: 1.0) |
| `detection_method` | `str` | 탐지 방법 (기본값: "direct_comparison") |

### 1.2 계산 속성 (Computed Properties)

| 속성 | 반환 타입 | 설명 |
|------|----------|------|
| `drift_count` | `int` | 전체 드리프트 필드 수 |
| `critical_count` | `int` | CRITICAL 심각도 드리프트 수 |
| `high_count` | `int` | HIGH 심각도 드리프트 수 |
| `monitored_fields` | `List[DriftField]` | MONITORED 카테고리 필드 목록 |
| `discovered_fields` | `List[DriftField]` | DISCOVERED 카테고리 필드 목록 |
| `monitored_count` | `int` | MONITORED 카테고리 필드 수 |
| `discovered_count` | `int` | DISCOVERED 카테고리 필드 수 |

---

## 2. DriftField 모델 구조

`DriftField`는 개별 필드의 드리프트 정보를 나타냅니다.

### 2.1 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `field_name` | `str` | 드리프트 발생 필드명 (중첩 경로 포함, 예: "encryption_configuration.sse_s3") |
| `baseline_value` | `Any` | 베이스라인 값 |
| `current_value` | `Any` | 현재 값 |
| `severity` | `DriftSeverity` | 필드별 심각도 |
| `category` | `DriftCategory` | 드리프트 분류 (기본값: MONITORED) |
| `description` | `Optional[str]` | 변경 설명 |
| `impact` | `Optional[str]` | 변경 영향도 |
| `recommendation` | `Optional[str]` | 권장 조치 |

### 2.2 DriftCategory 차이점

| 카테고리 | 의미 | 발생 조건 | 심각도 계산 포함 |
|----------|------|----------|-----------------|
| `MONITORED` | 베이스라인에 있던 필드의 변경 | 기존 필드 값이 변경됨 | ✅ Yes |
| `DISCOVERED` | 베이스라인에 없던 필드 추가/삭제 | 새 필드 추가 또는 기존 필드 삭제 | ❌ No |

**중요**: 전체 `severity`는 `MONITORED` 카테고리 필드만으로 계산됩니다. `DISCOVERED` 필드만 있는 경우 `severity`는 `LOW`입니다.

---

## 3. Severity 분류 기준

### 3.1 심각도 레벨

| Severity | 의미 | 대응 필요성 |
|----------|------|------------|
| `CRITICAL` | 즉시 조치 필요 | 데이터 무결성/보안 위험 |
| `HIGH` | 빠른 확인 필요 | 서비스 동작 영향 가능 |
| `MEDIUM` | 모니터링 필요 | 성능/용량 변화 |
| `LOW` | 참고용 | 메타데이터 변경 |

### 3.2 필드별 심각도 매핑

```python
# CRITICAL - 데이터 무결성/보안 관련
CRITICAL_FIELDS = [
    "table_schema",
    "columns",
    "encryption_configuration",
    "s3_encryption",
    "server_side_encryption",
    "endpoint_config",
    "iam_role",
    "role_arn",
    "execution_role",
    "kms_key",
    "security_configuration",
    "public_access_block",
]

# HIGH - 버전/런타임 관련
HIGH_FIELDS = [
    "release_label",
    "runtime",
    "airflow_version",
    "kafka_version",
    "instance_type",
    "instance_class",
    "engine_type",
    "handler",
    "layers",
]

# MEDIUM - 용량/스케일 관련
MEDIUM_FIELDS = [
    "memory_size",
    "timeout",
    "min_workers",
    "max_workers",
    "min_capacity",
    "max_capacity",
    "number_of_broker_nodes",
    "volume_size",
    "environment_class",
]

# LOW - 메타데이터 관련
LOW_FIELDS = [
    "tags",
    "description",
    "comment",
    "parameters",
]
```

### 3.3 패턴 기반 심각도 결정

직접 매핑되지 않은 필드는 패턴 매칭으로 심각도를 결정합니다:

```python
def get_field_severity(field_name: str) -> DriftSeverity:
    field_lower = field_name.lower()

    # CRITICAL 패턴
    if any(k in field_lower for k in ["encrypt", "kms", "security", "iam", "role", "public"]):
        return DriftSeverity.CRITICAL

    # HIGH 패턴
    if any(k in field_lower for k in ["version", "runtime", "instance", "type"]):
        return DriftSeverity.HIGH

    # MEDIUM 패턴
    if any(k in field_lower for k in ["size", "capacity", "worker", "memory", "timeout"]):
        return DriftSeverity.MEDIUM

    # LOW 패턴
    if any(k in field_lower for k in ["tag", "description", "comment", "name"]):
        return DriftSeverity.LOW

    # 기본값
    return DriftSeverity.MEDIUM
```

---

## 4. Assertion 패턴 표준

### 4.1 드리프트 없음 검증

```python
def test_no_drift_scenario():
    """베이스라인과 현재 설정이 동일한 경우."""
    result = detector.detect(resource_type, resource_id)

    # 기본 검증
    assert result.has_drift is False
    assert result.drift_count == 0
    assert result.severity == DriftSeverity.LOW

    # 필드 검증
    assert len(result.drift_fields) == 0
    assert result.monitored_count == 0
    assert result.discovered_count == 0

    # 설정 검증
    assert result.baseline_config == result.current_config
```

### 4.2 드리프트 있음 검증

```python
def test_drift_detected_scenario():
    """드리프트가 탐지된 경우."""
    result = detector.detect(resource_type, resource_id)

    # 기본 검증
    assert result.has_drift is True
    assert result.drift_count > 0
    assert len(result.drift_fields) == result.drift_count

    # 심각도 검증 (하나 이상의 MONITORED 필드가 있어야 함)
    if result.monitored_count > 0:
        assert result.severity != DriftSeverity.LOW

    # 카테고리 수 일관성 검증
    assert result.monitored_count + result.discovered_count == result.drift_count
```

### 4.3 CRITICAL 드리프트 검증

```python
def test_critical_drift_scenario():
    """CRITICAL 심각도 드리프트 검증."""
    result = detector.detect(resource_type, resource_id)

    # 심각도 검증
    assert result.severity == DriftSeverity.CRITICAL
    assert result.critical_count > 0

    # 필드 레벨 검증
    assert any(f.severity == DriftSeverity.CRITICAL for f in result.drift_fields)

    # CRITICAL 필드가 MONITORED 카테고리여야 함
    critical_fields = [f for f in result.drift_fields if f.severity == DriftSeverity.CRITICAL]
    assert all(f.category == DriftCategory.MONITORED for f in critical_fields)
```

### 4.4 카테고리별 검증

```python
def test_category_classification():
    """MONITORED vs DISCOVERED 카테고리 분류 검증."""
    result = detector.detect(resource_type, resource_id)

    # 카테고리 수 일관성
    assert result.monitored_count + result.discovered_count == result.drift_count

    # MONITORED 필드 검증 (기존 필드 값 변경)
    for field in result.monitored_fields:
        assert field.category == DriftCategory.MONITORED
        assert field.baseline_value is not None
        assert field.current_value is not None
        assert field.baseline_value != field.current_value

    # DISCOVERED 필드 검증 (추가 또는 삭제)
    for field in result.discovered_fields:
        assert field.category == DriftCategory.DISCOVERED
        # 추가된 필드: baseline_value is None
        # 삭제된 필드: current_value is None
        assert field.baseline_value is None or field.current_value is None
```

### 4.5 리소스 존재하지 않음 검증

```python
def test_resource_not_exists_scenario():
    """리소스가 삭제된 경우 CRITICAL 드리프트."""
    result = detector.detect(resource_type, resource_id)

    assert result.has_drift is True
    assert result.severity == DriftSeverity.CRITICAL

    # 특수 필드 검증
    assert any(f.field_name == "_resource_exists" for f in result.drift_fields)

    resource_field = next(f for f in result.drift_fields if f.field_name == "_resource_exists")
    assert resource_field.baseline_value is True
    assert resource_field.current_value is False
    assert resource_field.severity == DriftSeverity.CRITICAL
```

---

## 5. 테스트 시나리오 템플릿

### 5.1 No Drift 시나리오

```python
class TestNoDriftScenario:
    """베이스라인 == 현재 설정."""

    def test_identical_configs(self, detector, baseline_store, config_fetcher):
        """동일한 설정에서 드리프트 없음 확인."""
        config = {
            "runtime": "python3.9",
            "memory_size": 256,
            "timeout": 30,
        }

        # 베이스라인 설정
        baseline_store.create_baseline(
            resource_type="lambda",
            resource_id="test-function",
            config=config,
            created_by="test",
        )

        # 현재 설정 (동일)
        config_fetcher.set_mock_config("lambda", "test-function", config)

        # 검증
        result = detector.detect("lambda", "test-function")

        assert result.has_drift is False
        assert result.drift_count == 0
        assert result.severity == DriftSeverity.LOW
```

### 5.2 Single Field Drift 시나리오

```python
class TestSingleFieldDrift:
    """단일 필드 변경."""

    def test_memory_size_change(self, detector, baseline_store, config_fetcher):
        """메모리 크기 변경 (MEDIUM severity)."""
        baseline_config = {"memory_size": 256, "timeout": 30}
        current_config = {"memory_size": 512, "timeout": 30}

        baseline_store.create_baseline(
            resource_type="lambda",
            resource_id="test-function",
            config=baseline_config,
            created_by="test",
        )
        config_fetcher.set_mock_config("lambda", "test-function", current_config)

        result = detector.detect("lambda", "test-function")

        assert result.has_drift is True
        assert result.drift_count == 1
        assert result.severity == DriftSeverity.MEDIUM

        field = result.drift_fields[0]
        assert field.field_name == "memory_size"
        assert field.baseline_value == 256
        assert field.current_value == 512
        assert field.category == DriftCategory.MONITORED
```

### 5.3 Multi-Field Drift 시나리오

```python
class TestMultiFieldDrift:
    """복수 필드 변경."""

    def test_multiple_changes(self, detector, baseline_store, config_fetcher):
        """여러 필드 동시 변경."""
        baseline_config = {
            "runtime": "python3.9",
            "memory_size": 256,
            "timeout": 30,
        }
        current_config = {
            "runtime": "python3.11",  # HIGH
            "memory_size": 512,       # MEDIUM
            "timeout": 60,            # MEDIUM
        }

        baseline_store.create_baseline(
            resource_type="lambda",
            resource_id="test-function",
            config=baseline_config,
            created_by="test",
        )
        config_fetcher.set_mock_config("lambda", "test-function", current_config)

        result = detector.detect("lambda", "test-function")

        assert result.has_drift is True
        assert result.drift_count == 3
        assert result.severity == DriftSeverity.HIGH  # 최고 심각도

        # 필드별 검증
        field_names = {f.field_name for f in result.drift_fields}
        assert field_names == {"runtime", "memory_size", "timeout"}
```

### 5.4 Critical Drift 시나리오

```python
class TestCriticalDrift:
    """보안 관련 필드 변경."""

    def test_encryption_config_change(self, detector, baseline_store, config_fetcher):
        """암호화 설정 변경 (CRITICAL severity)."""
        baseline_config = {
            "encryption_configuration": {"sse_s3": {"enabled": True}},
            "memory_size": 256,
        }
        current_config = {
            "encryption_configuration": {"sse_s3": {"enabled": False}},  # CRITICAL!
            "memory_size": 256,
        }

        baseline_store.create_baseline(
            resource_type="athena",
            resource_id="test-workgroup",
            config=baseline_config,
            created_by="test",
        )
        config_fetcher.set_mock_config("athena", "test-workgroup", current_config)

        result = detector.detect("athena", "test-workgroup")

        assert result.has_drift is True
        assert result.severity == DriftSeverity.CRITICAL
        assert result.critical_count >= 1

        # 암호화 필드 검증
        encryption_fields = [
            f for f in result.drift_fields
            if "encryption" in f.field_name.lower()
        ]
        assert len(encryption_fields) > 0
        assert all(f.severity == DriftSeverity.CRITICAL for f in encryption_fields)
```

### 5.5 Discovered Only 시나리오

```python
class TestDiscoveredOnlyDrift:
    """새 필드 추가/삭제만 있는 경우."""

    def test_new_field_added(self, detector, baseline_store, config_fetcher):
        """새 필드 추가 (DISCOVERED category, LOW overall severity)."""
        baseline_config = {"memory_size": 256}
        current_config = {"memory_size": 256, "new_field": "new_value"}

        baseline_store.create_baseline(
            resource_type="lambda",
            resource_id="test-function",
            config=baseline_config,
            created_by="test",
        )
        config_fetcher.set_mock_config("lambda", "test-function", current_config)

        result = detector.detect("lambda", "test-function")

        assert result.has_drift is True
        assert result.drift_count == 1
        assert result.severity == DriftSeverity.LOW  # DISCOVERED만 있으면 LOW

        assert result.monitored_count == 0
        assert result.discovered_count == 1

        field = result.drift_fields[0]
        assert field.category == DriftCategory.DISCOVERED
        assert field.baseline_value is None
        assert field.current_value == "new_value"

    def test_field_deleted(self, detector, baseline_store, config_fetcher):
        """필드 삭제 (DISCOVERED category)."""
        baseline_config = {"memory_size": 256, "old_field": "old_value"}
        current_config = {"memory_size": 256}

        baseline_store.create_baseline(
            resource_type="lambda",
            resource_id="test-function",
            config=baseline_config,
            created_by="test",
        )
        config_fetcher.set_mock_config("lambda", "test-function", current_config)

        result = detector.detect("lambda", "test-function")

        assert result.has_drift is True
        assert result.discovered_count == 1

        field = result.drift_fields[0]
        assert field.category == DriftCategory.DISCOVERED
        assert field.baseline_value == "old_value"
        assert field.current_value is None
```

---

## 6. Handler 응답 검증

### 6.1 Handler 응답 구조

```python
# Lambda Handler 응답 구조
{
    "statusCode": 200,
    "body": {
        "success": True,
        "status": "success",
        "summary": {
            "total_resources": int,
            "total_drifts": int,
            "resources_with_drift": int,
            "by_severity": {
                "critical": int,
                "high": int,
                "medium": int,
                "low": int,
            },
            "by_resource_type": {
                "lambda": int,
                "glue": int,
                # ...
            },
        },
        "results": [
            # DriftResult.to_dict() 목록
        ],
        "detection_timestamp": str,  # ISO format
    }
}
```

### 6.2 Handler 응답 검증 패턴

```python
def test_handler_response_structure(handler, event):
    """Handler 응답 구조 검증."""
    response = handler.process(event)

    # HTTP 상태 코드
    assert response["statusCode"] == 200

    # Body 구조
    body = response["body"]
    assert body["success"] is True
    assert body["status"] == "success"

    # Summary 구조
    summary = body["summary"]
    assert "total_resources" in summary
    assert "total_drifts" in summary
    assert "resources_with_drift" in summary
    assert "by_severity" in summary
    assert "by_resource_type" in summary

    # Severity breakdown
    by_severity = summary["by_severity"]
    assert set(by_severity.keys()) == {"critical", "high", "medium", "low"}
    assert all(isinstance(v, int) for v in by_severity.values())

    # 합계 검증
    assert summary["total_drifts"] == sum(by_severity.values())


def test_handler_drift_count_verification(handler, event):
    """Handler 드리프트 카운트 검증."""
    response = handler.process(event)
    body = response["body"]

    expected_count = 5  # 예상 드리프트 수
    expected_critical = 1

    assert body["summary"]["total_drifts"] == expected_count
    assert body["summary"]["by_severity"]["critical"] == expected_critical


def test_handler_results_match_summary(handler, event):
    """Results와 Summary 일치 검증."""
    response = handler.process(event)
    body = response["body"]

    # Results에서 직접 계산
    results = body["results"]
    calculated_total = sum(r["drift_count"] for r in results)
    calculated_with_drift = sum(1 for r in results if r["has_drift"])

    # Summary와 비교
    assert body["summary"]["total_drifts"] == calculated_total
    assert body["summary"]["resources_with_drift"] == calculated_with_drift
```

### 6.3 에러 응답 검증

```python
def test_handler_validation_error(handler):
    """유효하지 않은 입력 검증."""
    invalid_event = {"invalid_field": "value"}

    response = handler.process(invalid_event)

    assert response["statusCode"] == 400
    assert response["body"]["success"] is False
    assert "error" in response["body"]


def test_handler_resource_not_found(handler):
    """리소스를 찾을 수 없는 경우."""
    event = {
        "resource_type": "lambda",
        "resource_id": "non-existent-function",
    }

    response = handler.process(event)

    # 리소스 없음은 CRITICAL 드리프트로 처리
    body = response["body"]
    assert body["summary"]["by_severity"]["critical"] > 0
```

---

## 7. 테스트 Fixture 예시

```python
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from src.agents.bdp_drift.bdp_drift.services.models import (
    Baseline,
    DriftCategory,
    DriftField,
    DriftResult,
    DriftSeverity,
)
from src.agents.bdp_drift.bdp_drift.services.drift_detector import DriftDetector
from src.agents.bdp_drift.bdp_drift.services.baseline_store import BaselineStore
from src.agents.bdp_drift.bdp_drift.services.config_fetcher import ConfigFetcher


@pytest.fixture
def mock_baseline_store():
    """Mock BaselineStore fixture."""
    store = MagicMock(spec=BaselineStore)
    store._baselines = {}

    def create_baseline(resource_type, resource_id, config, created_by, **kwargs):
        key = f"{resource_type}/{resource_id}"
        baseline = Baseline(
            resource_type=resource_type,
            resource_id=resource_id,
            version=1,
            config=config,
            config_hash=Baseline.compute_hash(config),
            created_by=created_by,
            created_at=datetime.utcnow(),
            **kwargs,
        )
        store._baselines[key] = baseline
        return baseline

    def get_baseline(resource_type, resource_id):
        key = f"{resource_type}/{resource_id}"
        return store._baselines.get(key)

    store.create_baseline = create_baseline
    store.get_baseline = get_baseline

    return store


@pytest.fixture
def mock_config_fetcher():
    """Mock ConfigFetcher fixture."""
    fetcher = MagicMock(spec=ConfigFetcher)
    fetcher._configs = {}

    def set_mock_config(resource_type, resource_id, config):
        key = f"{resource_type}/{resource_id}"
        fetcher._configs[key] = config

    def fetch_config(resource_type, resource_id):
        key = f"{resource_type}/{resource_id}"
        config = fetcher._configs.get(key)
        if config is None:
            return None

        from src.agents.bdp_drift.bdp_drift.services.config_fetcher import ResourceConfig
        return ResourceConfig(
            resource_type=resource_type,
            resource_id=resource_id,
            config=config,
            resource_arn=f"arn:aws:{resource_type}:region:account:{resource_id}",
        )

    fetcher.set_mock_config = set_mock_config
    fetcher.fetch_config = fetch_config

    return fetcher


@pytest.fixture
def detector(mock_baseline_store, mock_config_fetcher):
    """DriftDetector fixture with mocks."""
    return DriftDetector(
        baseline_store=mock_baseline_store,
        config_fetcher=mock_config_fetcher,
    )


@pytest.fixture
def sample_drift_result():
    """Sample DriftResult for testing."""
    return DriftResult(
        resource_type="lambda",
        resource_id="test-function",
        resource_arn="arn:aws:lambda:us-east-1:123456789012:function:test-function",
        has_drift=True,
        severity=DriftSeverity.HIGH,
        drift_fields=[
            DriftField(
                field_name="runtime",
                baseline_value="python3.9",
                current_value="python3.11",
                severity=DriftSeverity.HIGH,
                category=DriftCategory.MONITORED,
            ),
            DriftField(
                field_name="memory_size",
                baseline_value=256,
                current_value=512,
                severity=DriftSeverity.MEDIUM,
                category=DriftCategory.MONITORED,
            ),
        ],
        baseline_version=1,
        detection_timestamp=datetime.utcnow(),
    )
```

---

## 8. 참조

### 8.1 관련 파일

| 파일 | 설명 |
|------|------|
| `src/agents/bdp_drift/bdp_drift/services/models.py` | DriftResult, DriftField 모델 정의 |
| `src/agents/bdp_drift/bdp_drift/services/drift_detector.py` | 드리프트 탐지 로직, Severity 매핑 |
| `src/agents/bdp_drift/bdp_drift/services/baseline_store.py` | 베이스라인 저장소 |
| `src/agents/bdp_drift/bdp_drift/services/config_fetcher.py` | AWS 설정 조회 |

### 8.2 검증 명령어

```bash
# 테스트 실행
pytest tests/agents/bdp_drift/ -v

# 특정 시나리오 실행
pytest tests/agents/bdp_drift/test_drift_scenarios.py -k "critical" -v

# 커버리지 확인
pytest tests/agents/bdp_drift/ --cov=src/agents/bdp_drift --cov-report=term-missing
```
