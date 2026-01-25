# Baseline Configuration Insertion Guide

RDS(MySQL)에 드리프트 탐지용 베이스라인 설정을 저장하는 가이드.

## 1. 데이터베이스 스키마

### 1.1 스키마 파일 위치

**원본 DDL 파일**: `src/agents/bdp_drift/conf/schema/drift_baselines.sql`

```bash
# MySQL/RDS 적용
mysql -u user -p database < src/agents/bdp_drift/conf/schema/drift_baselines.sql

# LocalStack MySQL 적용
docker exec mysql mysql -u root -p cd1_agent < src/agents/bdp_drift/conf/schema/drift_baselines.sql
```

### 1.2 테이블 구조

| 테이블 | 설명 |
|--------|------|
| `drift_baselines` | AWS 리소스별 기준 설정 저장 (Primary Key: resource_type + resource_id) |
| `drift_baseline_history` | 모든 베이스라인 변경 이력 추적 |

### 1.3 컬럼 설명

**drift_baselines**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `resource_type` | VARCHAR(64) | 리소스 타입 (glue, athena, emr, sagemaker, s3, mwaa, msk, lambda) |
| `resource_id` | VARCHAR(255) | 리소스 식별자 (함수명, 버킷명, 클러스터명 등) |
| `version` | INT | 베이스라인 버전 (자동 증가) |
| `config` | JSON | 베이스라인 설정 (JSON 형태) |
| `config_hash` | VARCHAR(64) | 설정의 SHA256 해시 (변경 감지용) |
| `resource_arn` | VARCHAR(512) | AWS ARN (선택) |
| `description` | TEXT | 베이스라인 설명 |
| `tags` | JSON | 태그 (JSON 형태) |
| `created_at` | TIMESTAMP | 생성 시각 |
| `updated_at` | TIMESTAMP | 수정 시각 |
| `created_by` | VARCHAR(128) | 생성자 |
| `updated_by` | VARCHAR(128) | 수정자 |

---

## 2. 지원 리소스 타입

| 타입 | 값 | 설명 | 주요 모니터링 필드 |
|------|---|------|------------------|
| Glue | `glue` | Glue Catalogue | columns, table_schema, parameters |
| Athena | `athena` | Athena 워크그룹 | encryption_configuration, engine_version |
| EMR | `emr` | EMR 클러스터 | release_label, instance_type, security_configuration |
| SageMaker | `sagemaker` | SageMaker 엔드포인트 | endpoint_config, instance_type |
| S3 | `s3` | S3 버킷 | encryption, public_access_block, versioning |
| MWAA | `mwaa` | MWAA 환경 | airflow_version, environment_class, execution_role |
| MSK | `msk` | MSK 클러스터 | kafka_version, number_of_broker_nodes |
| Lambda | `lambda` | Lambda 함수 | runtime, memory_size, timeout, layers, role |

---

## 3. BaselineStore API 사용법

### 3.1 기본 사용법

```python
from src.agents.bdp_drift.bdp_drift.services.baseline_store import BaselineStore
from src.agents.bdp_drift.bdp_drift.services.models import Baseline

# 프로바이더 선택: "mock", "sqlite", "mysql"
store = BaselineStore(provider="sqlite")

# 테이블 생성 (최초 1회)
store.ensure_tables()
```

### 3.2 베이스라인 생성

```python
# 단일 베이스라인 생성
baseline = store.create_baseline(
    resource_type="lambda",
    resource_id="my-data-processor",
    config={
        "function_name": "my-data-processor",
        "runtime": "python3.11",
        "handler": "handler.main",
        "memory_size": 256,
        "timeout": 30,
        "role": "arn:aws:iam::123456789012:role/lambda-execution-role",
        "environment": {
            "LOG_LEVEL": "INFO",
            "STAGE": "production",
        },
        "layers": [],
        "architectures": ["arm64"],
    },
    created_by="admin@company.com",
    resource_arn="arn:aws:lambda:ap-northeast-2:123456789012:function:my-data-processor",
    description="Production data processor Lambda",
    tags={"Environment": "production", "Team": "data-platform"},
)

print(f"Created baseline v{baseline.version}: {baseline.config_hash}")
```

### 3.3 베이스라인 조회

```python
# 단일 조회
baseline = store.get_baseline("lambda", "my-data-processor")
if baseline:
    print(f"Version: {baseline.version}")
    print(f"Config: {baseline.config}")

# 타입별 목록 조회
lambda_baselines = store.list_baselines(resource_type="lambda")
for b in lambda_baselines:
    print(f"{b.resource_id}: v{b.version}")

# 전체 목록 조회
all_baselines = store.list_baselines()
```

### 3.4 베이스라인 업데이트

```python
# 설정 변경
updated = store.update_baseline(
    resource_type="lambda",
    resource_id="my-data-processor",
    config={
        "function_name": "my-data-processor",
        "runtime": "python3.11",
        "handler": "handler.main",
        "memory_size": 512,  # 변경됨
        "timeout": 60,       # 변경됨
        "role": "arn:aws:iam::123456789012:role/lambda-execution-role",
        "environment": {
            "LOG_LEVEL": "INFO",
            "STAGE": "production",
        },
        "layers": [],
        "architectures": ["arm64"],
    },
    updated_by="admin@company.com",
    reason="메모리 및 타임아웃 증가 - JIRA-123",
)

if updated:
    print(f"Updated to v{updated.version}")
```

### 3.5 버전 이력 조회

```python
# 변경 이력 조회
history = store.get_version_history("lambda", "my-data-processor")
for h in history:
    print(f"v{h.version} ({h.change_type}): {h.change_reason}")
    print(f"  Changed by: {h.changed_by} at {h.changed_at}")

# 특정 버전 조회
v1_baseline = store.get_baseline_at_version("lambda", "my-data-processor", 1)

# 버전 비교
diff = store.compare_versions("lambda", "my-data-processor", 1, 2)
print(f"Differences: {diff['differences']}")
```

### 3.6 롤백

```python
# 이전 버전으로 롤백
rolled_back = store.rollback_to_version(
    resource_type="lambda",
    resource_id="my-data-processor",
    version=1,
    rolled_back_by="admin@company.com",
)

if rolled_back:
    print(f"Rolled back to v{rolled_back.version}")
```

---

## 4. 직접 SQL Insertion

### 4.1 Python에서 해시 계산

```python
import hashlib
import json

def compute_config_hash(config: dict) -> str:
    """설정의 SHA256 해시 계산."""
    config_str = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(config_str.encode()).hexdigest()

# 사용 예시
config = {"runtime": "python3.11", "memory_size": 256}
config_hash = compute_config_hash(config)
print(f"Hash: {config_hash}")
```

### 4.2 단일 INSERT

```sql
-- 베이스라인 삽입
INSERT INTO drift_baselines (
    resource_type,
    resource_id,
    version,
    config,
    config_hash,
    resource_arn,
    description,
    tags,
    created_by,
    updated_by
) VALUES (
    'lambda',
    'my-data-processor',
    1,
    '{"function_name": "my-data-processor", "runtime": "python3.11", "memory_size": 256, "timeout": 30}',
    'a1b2c3d4e5f6...',  -- SHA256 해시
    'arn:aws:lambda:ap-northeast-2:123456789012:function:my-data-processor',
    'Production data processor Lambda',
    '{"Environment": "production", "Team": "data-platform"}',
    'admin@company.com',
    'admin@company.com'
);

-- 이력 동시 삽입
INSERT INTO drift_baseline_history (
    id,
    resource_type,
    resource_id,
    version,
    change_type,
    previous_config,
    current_config,
    config_hash,
    change_reason,
    changed_by
) VALUES (
    UUID(),
    'lambda',
    'my-data-processor',
    1,
    'CREATE',
    NULL,
    '{"function_name": "my-data-processor", "runtime": "python3.11", "memory_size": 256, "timeout": 30}',
    'a1b2c3d4e5f6...',
    'Initial baseline creation',
    'admin@company.com'
);
```

### 4.3 UPSERT (INSERT or UPDATE)

```sql
-- 베이스라인 UPSERT (MySQL)
INSERT INTO drift_baselines (
    resource_type,
    resource_id,
    version,
    config,
    config_hash,
    resource_arn,
    description,
    created_by,
    updated_by
) VALUES (
    'lambda',
    'my-data-processor',
    1,
    '{"runtime": "python3.11", "memory_size": 256}',
    'a1b2c3d4...',
    'arn:aws:lambda:...',
    'Data processor',
    'admin',
    'admin'
)
ON DUPLICATE KEY UPDATE
    version = version + 1,
    config = VALUES(config),
    config_hash = VALUES(config_hash),
    updated_at = CURRENT_TIMESTAMP,
    updated_by = VALUES(updated_by);
```

---

## 5. Bulk Import 패턴

### 5.1 Python 스크립트를 통한 Bulk Import

```python
"""
Baseline Bulk Import Script

Usage:
    python scripts/import_baselines.py --input baselines.json --provider mysql
"""

import json
import argparse
from typing import List, Dict, Any

from src.agents.bdp_drift.bdp_drift.services.baseline_store import BaselineStore


def load_baselines_from_json(filepath: str) -> List[Dict[str, Any]]:
    """JSON 파일에서 베이스라인 로드."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def import_baselines(
    store: BaselineStore,
    baselines: List[Dict[str, Any]],
    created_by: str,
) -> Dict[str, int]:
    """베이스라인 Bulk Import.

    Returns:
        {"created": n, "updated": n, "skipped": n, "failed": n}
    """
    stats = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}

    for item in baselines:
        try:
            resource_type = item["resource_type"]
            resource_id = item["resource_id"]
            config = item["config"]

            # 기존 베이스라인 확인
            existing = store.get_baseline(resource_type, resource_id)

            if existing is None:
                # 새로 생성
                store.create_baseline(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    config=config,
                    created_by=created_by,
                    resource_arn=item.get("resource_arn"),
                    description=item.get("description"),
                    tags=item.get("tags"),
                )
                stats["created"] += 1

            else:
                # 변경 여부 확인
                from src.agents.bdp_drift.bdp_drift.services.models import Baseline
                new_hash = Baseline.compute_hash(config)

                if new_hash == existing.config_hash:
                    stats["skipped"] += 1
                else:
                    store.update_baseline(
                        resource_type=resource_type,
                        resource_id=resource_id,
                        config=config,
                        updated_by=created_by,
                        reason=item.get("update_reason", "Bulk import update"),
                    )
                    stats["updated"] += 1

        except Exception as e:
            print(f"Failed to import {item.get('resource_id')}: {e}")
            stats["failed"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Import baselines to database")
    parser.add_argument("--input", required=True, help="Input JSON file")
    parser.add_argument("--provider", default="sqlite", help="Database provider")
    parser.add_argument("--created-by", default="bulk-import", help="Creator identifier")
    args = parser.parse_args()

    store = BaselineStore(provider=args.provider)
    store.ensure_tables()

    baselines = load_baselines_from_json(args.input)
    stats = import_baselines(store, baselines, args.created_by)

    print(f"Import complete: {stats}")


if __name__ == "__main__":
    main()
```

### 5.2 Import용 JSON 형식

```json
[
    {
        "resource_type": "lambda",
        "resource_id": "data-processor-prod",
        "resource_arn": "arn:aws:lambda:ap-northeast-2:123456789012:function:data-processor-prod",
        "description": "Production data processor",
        "tags": {"Environment": "production", "Team": "data-platform"},
        "config": {
            "function_name": "data-processor-prod",
            "runtime": "python3.11",
            "handler": "handler.main",
            "memory_size": 512,
            "timeout": 60,
            "role": "arn:aws:iam::123456789012:role/lambda-role",
            "environment": {
                "LOG_LEVEL": "INFO",
                "STAGE": "production"
            },
            "layers": [],
            "architectures": ["arm64"]
        }
    },
    {
        "resource_type": "s3",
        "resource_id": "data-lake-raw-prod",
        "resource_arn": "arn:aws:s3:::data-lake-raw-prod",
        "description": "Raw data lake bucket",
        "config": {
            "name": "data-lake-raw-prod",
            "versioning": "Enabled",
            "encryption": {
                "SSEAlgorithm": "aws:kms",
                "KMSMasterKeyID": "alias/data-lake-key"
            },
            "public_access_block": {
                "BlockPublicAcls": true,
                "IgnorePublicAcls": true,
                "BlockPublicPolicy": true,
                "RestrictPublicBuckets": true
            }
        }
    },
    {
        "resource_type": "athena",
        "resource_id": "analytics-workgroup",
        "resource_arn": "arn:aws:athena:ap-northeast-2:123456789012:workgroup/analytics-workgroup",
        "description": "Analytics team workgroup",
        "config": {
            "name": "analytics-workgroup",
            "state": "ENABLED",
            "result_configuration": {
                "OutputLocation": "s3://athena-results/analytics/",
                "EncryptionConfiguration": {
                    "EncryptionOption": "SSE_S3"
                }
            },
            "enforce_work_group_configuration": true,
            "engine_version": {
                "SelectedEngineVersion": "Athena engine version 3"
            }
        }
    },
    {
        "resource_type": "glue",
        "resource_id": "analytics/user_events",
        "resource_arn": "arn:aws:glue:ap-northeast-2:123456789012:table/analytics/user_events",
        "description": "User events table",
        "config": {
            "name": "user_events",
            "database": "analytics",
            "columns": [
                {"name": "event_id", "type": "string"},
                {"name": "user_id", "type": "string"},
                {"name": "event_type", "type": "string"},
                {"name": "timestamp", "type": "timestamp"},
                {"name": "properties", "type": "map<string,string>"}
            ],
            "partition_keys": [
                {"name": "year", "type": "int"},
                {"name": "month", "type": "int"},
                {"name": "day", "type": "int"}
            ],
            "table_type": "EXTERNAL_TABLE",
            "storage_descriptor": {
                "location": "s3://data-lake-processed/user_events/",
                "input_format": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                "output_format": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
            }
        }
    }
]
```

### 5.3 AWS 리소스에서 직접 Import

```python
"""
AWS 리소스에서 현재 설정을 가져와 베이스라인으로 저장.
"""

from src.agents.bdp_drift.bdp_drift.services.baseline_store import BaselineStore
from src.agents.bdp_drift.bdp_drift.services.config_fetcher import ConfigFetcher
from src.agents.bdp_drift.bdp_drift.services.drift_detector import DriftDetector


def import_from_aws(
    resource_type: str,
    resource_id: str,
    created_by: str,
    description: str = None,
) -> None:
    """AWS 리소스에서 현재 설정을 베이스라인으로 저장."""

    store = BaselineStore(provider="mysql")
    store.ensure_tables()

    fetcher = ConfigFetcher(use_mock=False)  # 실제 AWS 호출
    detector = DriftDetector(store, fetcher)

    baseline = detector.create_baseline_from_current(
        resource_type=resource_type,
        resource_id=resource_id,
        created_by=created_by,
        description=description,
    )

    if baseline:
        print(f"Created baseline: {resource_type}/{resource_id} v{baseline.version}")
    else:
        print(f"Failed to create baseline for {resource_type}/{resource_id}")


def import_all_from_aws(resource_type: str, created_by: str) -> None:
    """특정 타입의 모든 AWS 리소스를 베이스라인으로 저장."""

    store = BaselineStore(provider="mysql")
    store.ensure_tables()

    fetcher = ConfigFetcher(use_mock=False)
    detector = DriftDetector(store, fetcher)

    # 모든 리소스 목록 조회
    resources = fetcher.list_resources(resource_type)
    print(f"Found {len(resources)} {resource_type} resources")

    for resource_id in resources:
        baseline = detector.create_baseline_from_current(
            resource_type=resource_type,
            resource_id=resource_id,
            created_by=created_by,
            description=f"Auto-imported from AWS",
        )

        if baseline:
            print(f"  ✓ {resource_id}")
        else:
            print(f"  ✗ {resource_id} (failed)")


# 사용 예시
if __name__ == "__main__":
    # 단일 리소스 import
    import_from_aws(
        resource_type="lambda",
        resource_id="my-function",
        created_by="import-script",
        description="Imported from production",
    )

    # 모든 Lambda 함수 import
    import_all_from_aws("lambda", "import-script")
```

---

## 6. Config 검증

### 6.1 필수 필드 검증

```python
from typing import Dict, Any, List, Optional


# 리소스 타입별 필수 필드 정의
REQUIRED_FIELDS = {
    "lambda": ["function_name", "runtime", "handler", "memory_size", "timeout", "role"],
    "s3": ["name", "versioning"],
    "athena": ["name", "state", "result_configuration"],
    "glue": ["name"],
    "emr": ["release_label", "instance_type"],
    "sagemaker": ["endpoint_config"],
    "mwaa": ["airflow_version", "execution_role"],
    "msk": ["kafka_version", "number_of_broker_nodes"],
}


def validate_config(resource_type: str, config: Dict[str, Any]) -> List[str]:
    """베이스라인 설정 검증.

    Args:
        resource_type: 리소스 타입
        config: 설정 딕셔너리

    Returns:
        에러 메시지 목록 (빈 리스트면 유효)
    """
    errors = []

    # 필수 필드 검증
    required = REQUIRED_FIELDS.get(resource_type, [])
    for field in required:
        if field not in config or config[field] is None:
            errors.append(f"Missing required field: {field}")

    # 타입별 추가 검증
    if resource_type == "lambda":
        errors.extend(_validate_lambda_config(config))
    elif resource_type == "s3":
        errors.extend(_validate_s3_config(config))
    # ... 기타 리소스 타입

    return errors


def _validate_lambda_config(config: Dict[str, Any]) -> List[str]:
    """Lambda 설정 검증."""
    errors = []

    # memory_size 범위 검증
    if "memory_size" in config:
        memory = config["memory_size"]
        if not isinstance(memory, int) or memory < 128 or memory > 10240:
            errors.append(f"memory_size must be between 128 and 10240: {memory}")

    # timeout 범위 검증
    if "timeout" in config:
        timeout = config["timeout"]
        if not isinstance(timeout, int) or timeout < 1 or timeout > 900:
            errors.append(f"timeout must be between 1 and 900: {timeout}")

    # runtime 유효성 검증
    valid_runtimes = [
        "python3.9", "python3.10", "python3.11", "python3.12",
        "nodejs18.x", "nodejs20.x",
        "java11", "java17", "java21",
    ]
    if "runtime" in config and config["runtime"] not in valid_runtimes:
        errors.append(f"Invalid runtime: {config['runtime']}")

    return errors


def _validate_s3_config(config: Dict[str, Any]) -> List[str]:
    """S3 설정 검증."""
    errors = []

    # versioning 유효값 검증
    valid_versioning = ["Enabled", "Suspended", "Disabled"]
    if "versioning" in config and config["versioning"] not in valid_versioning:
        errors.append(f"Invalid versioning: {config['versioning']}")

    # public_access_block 검증
    if "public_access_block" in config:
        pab = config["public_access_block"]
        required_keys = ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"]
        for key in required_keys:
            if key not in pab:
                errors.append(f"Missing public_access_block field: {key}")

    return errors


# 사용 예시
config = {
    "function_name": "my-function",
    "runtime": "python3.11",
    "memory_size": 256,
    "timeout": 30,
    # handler와 role 누락
}

errors = validate_config("lambda", config)
if errors:
    print("Validation errors:")
    for e in errors:
        print(f"  - {e}")
else:
    print("Config is valid")
```

### 6.2 Import 전 검증 통합

```python
def import_baselines_with_validation(
    store: BaselineStore,
    baselines: List[Dict[str, Any]],
    created_by: str,
    strict: bool = True,
) -> Dict[str, Any]:
    """검증 포함 Bulk Import.

    Args:
        store: BaselineStore 인스턴스
        baselines: 베이스라인 목록
        created_by: 생성자
        strict: True면 검증 실패 시 중단

    Returns:
        {"imported": n, "skipped": n, "errors": [...]}
    """
    result = {"imported": 0, "skipped": 0, "errors": []}

    for item in baselines:
        resource_type = item.get("resource_type")
        resource_id = item.get("resource_id")
        config = item.get("config", {})

        # 검증
        errors = validate_config(resource_type, config)

        if errors:
            error_entry = {
                "resource": f"{resource_type}/{resource_id}",
                "errors": errors,
            }
            result["errors"].append(error_entry)

            if strict:
                continue  # 스킵하고 다음으로
            # strict=False면 경고만 하고 진행

        try:
            store.create_baseline(
                resource_type=resource_type,
                resource_id=resource_id,
                config=config,
                created_by=created_by,
                resource_arn=item.get("resource_arn"),
                description=item.get("description"),
                tags=item.get("tags"),
            )
            result["imported"] += 1

        except Exception as e:
            result["errors"].append({
                "resource": f"{resource_type}/{resource_id}",
                "errors": [str(e)],
            })
            result["skipped"] += 1

    return result
```

---

## 7. 환경 설정

### 7.1 환경 변수

```bash
# Provider 선택 (mock, sqlite, mysql)
export DRIFT_PROVIDER=mysql

# SQLite 경로 (sqlite 사용 시)
export BASELINE_SQLITE_PATH=/path/to/baselines.db

# MySQL 연결 정보 (mysql 사용 시)
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=drift_user
export MYSQL_PASSWORD=secret
export MYSQL_DATABASE=cd1_agent
```

### 7.2 MySQL Provider 구현 예시

```python
"""MySQL Provider (BaselineStore에 추가 가능)."""

import mysql.connector
from mysql.connector import Error


class MySQLProvider(BaselineStoreProvider):
    """MySQL/RDS 프로바이더."""

    def __init__(
        self,
        host: str = None,
        port: int = 3306,
        user: str = None,
        password: str = None,
        database: str = None,
    ):
        self.config = {
            "host": host or os.getenv("MYSQL_HOST", "localhost"),
            "port": port or int(os.getenv("MYSQL_PORT", "3306")),
            "user": user or os.getenv("MYSQL_USER"),
            "password": password or os.getenv("MYSQL_PASSWORD"),
            "database": database or os.getenv("MYSQL_DATABASE", "cd1_agent"),
        }
        self._conn = None

    @property
    def conn(self):
        if self._conn is None or not self._conn.is_connected():
            self._conn = mysql.connector.connect(**self.config)
        return self._conn

    def ensure_tables(self) -> None:
        """테이블 생성."""
        cursor = self.conn.cursor()

        # drift_baselines 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drift_baselines (
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(255) NOT NULL,
                version INT NOT NULL DEFAULT 1,
                config JSON NOT NULL,
                config_hash VARCHAR(64) NOT NULL,
                resource_arn VARCHAR(512),
                description TEXT,
                tags JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_by VARCHAR(128),
                updated_by VARCHAR(128),
                PRIMARY KEY (resource_type, resource_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # drift_baseline_history 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drift_baseline_history (
                id VARCHAR(36) PRIMARY KEY,
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(255) NOT NULL,
                version INT NOT NULL,
                change_type ENUM('CREATE', 'UPDATE', 'DELETE') NOT NULL,
                previous_config JSON,
                current_config JSON NOT NULL,
                config_hash VARCHAR(64) NOT NULL,
                change_reason TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                changed_by VARCHAR(128) NOT NULL,
                INDEX idx_resource (resource_type, resource_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        self.conn.commit()

    # ... 나머지 메서드 구현 (get_baseline, create_baseline, etc.)
```

---

## 8. 참조

### 8.1 관련 파일

| 파일 | 설명 |
|------|------|
| `src/agents/bdp_drift/conf/schema/drift_baselines.sql` | **베이스라인 DDL 스키마 (원본)** |
| `src/agents/bdp_drift/bdp_drift/services/baseline_store.py` | BaselineStore 구현 |
| `src/agents/bdp_drift/bdp_drift/services/config_fetcher.py` | AWS 설정 조회 |
| `src/agents/bdp_drift/bdp_drift/services/models.py` | 데이터 모델 정의 |

### 8.2 CLI 명령어

```bash
# Import 실행
python scripts/import_baselines.py --input baselines.json --provider mysql

# 베이스라인 목록 조회
python -c "
from src.agents.bdp_drift.bdp_drift.services.baseline_store import BaselineStore
store = BaselineStore(provider='mysql')
for b in store.list_baselines():
    print(f'{b.resource_type}/{b.resource_id}: v{b.version}')
"

# 드리프트 탐지 실행
python -c "
from src.agents.bdp_drift.bdp_drift.services.drift_detector import create_detector
detector = create_detector(baseline_provider='mysql', use_mock_fetcher=False)
results = detector.detect_all()
for r in results:
    if r.has_drift:
        print(f'{r.resource_type}/{r.resource_id}: {r.severity.value} ({r.drift_count} drifts)')
"
```
