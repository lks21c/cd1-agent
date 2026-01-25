"""
Baseline Store - DB storage layer for drift baselines.

베이스라인 설정 저장소.
Provider 패턴으로 MySQL/SQLite/Mock 지원.
모든 변경 사항은 자동으로 history 테이블에 기록됨.
"""

import json
import logging
import os
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agents.bdp_drift.bdp_drift.services.models import (
    Baseline,
    BaselineCreate,
    BaselineHistory,
    ChangeType,
)

logger = logging.getLogger(__name__)


class BaselineStoreProvider(ABC):
    """베이스라인 저장소 추상 프로바이더."""

    @abstractmethod
    def ensure_tables(self) -> None:
        """테이블 생성 확인."""
        pass

    @abstractmethod
    def get_baseline(self, resource_type: str, resource_id: str) -> Optional[Baseline]:
        """베이스라인 조회."""
        pass

    @abstractmethod
    def list_baselines(self, resource_type: Optional[str] = None) -> List[Baseline]:
        """베이스라인 목록 조회."""
        pass

    @abstractmethod
    def create_baseline(
        self,
        baseline: BaselineCreate,
        created_by: str,
    ) -> Baseline:
        """베이스라인 생성."""
        pass

    @abstractmethod
    def update_baseline(
        self,
        resource_type: str,
        resource_id: str,
        config: Dict[str, Any],
        updated_by: str,
        reason: Optional[str] = None,
    ) -> Optional[Baseline]:
        """베이스라인 업데이트."""
        pass

    @abstractmethod
    def delete_baseline(self, resource_type: str, resource_id: str) -> bool:
        """베이스라인 삭제."""
        pass

    @abstractmethod
    def get_version_history(
        self,
        resource_type: str,
        resource_id: str,
    ) -> List[BaselineHistory]:
        """버전 이력 조회."""
        pass


class SQLiteProvider(BaselineStoreProvider):
    """SQLite 프로바이더 (유닛 테스트용)."""

    def __init__(self, db_path: str = ":memory:"):
        """SQLite 프로바이더 초기화.

        Args:
            db_path: 데이터베이스 파일 경로 (기본값: 인메모리)
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        logger.info(f"SQLite provider initialized: {db_path}")

    @property
    def conn(self) -> sqlite3.Connection:
        """SQLite 연결."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def ensure_tables(self) -> None:
        """테이블 생성."""
        # 항상 인라인 스키마 사용 (가장 안정적)
        self._create_inline_schema()

    def _create_inline_schema(self) -> None:
        """인라인 스키마 생성."""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drift_baselines (
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                config TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                resource_arn TEXT,
                description TEXT,
                tags TEXT,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                created_by TEXT,
                updated_by TEXT,
                PRIMARY KEY (resource_type, resource_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drift_baseline_history (
                id TEXT PRIMARY KEY,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                change_type TEXT NOT NULL,
                previous_config TEXT,
                current_config TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                change_reason TEXT,
                changed_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                changed_by TEXT NOT NULL
            )
        """)

        self.conn.commit()

    def get_baseline(self, resource_type: str, resource_id: str) -> Optional[Baseline]:
        """베이스라인 조회."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM drift_baselines
            WHERE resource_type = ? AND resource_id = ?
            """,
            (resource_type, resource_id),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_baseline(row)

    def list_baselines(self, resource_type: Optional[str] = None) -> List[Baseline]:
        """베이스라인 목록 조회."""
        cursor = self.conn.cursor()

        if resource_type:
            cursor.execute(
                "SELECT * FROM drift_baselines WHERE resource_type = ? ORDER BY resource_id",
                (resource_type,),
            )
        else:
            cursor.execute(
                "SELECT * FROM drift_baselines ORDER BY resource_type, resource_id"
            )

        return [self._row_to_baseline(row) for row in cursor.fetchall()]

    def create_baseline(
        self,
        baseline: BaselineCreate,
        created_by: str,
    ) -> Baseline:
        """베이스라인 생성."""
        config_hash = Baseline.compute_hash(baseline.config)
        now = datetime.utcnow().isoformat() + "Z"

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO drift_baselines
            (resource_type, resource_id, version, config, config_hash,
             resource_arn, description, tags, created_at, updated_at, created_by, updated_by)
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                baseline.resource_type,
                baseline.resource_id,
                json.dumps(baseline.config, ensure_ascii=False),
                config_hash,
                baseline.resource_arn,
                baseline.description,
                json.dumps(baseline.tags) if baseline.tags else None,
                now,
                now,
                created_by,
                created_by,
            ),
        )

        # 히스토리 기록
        history_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO drift_baseline_history
            (id, resource_type, resource_id, version, change_type,
             previous_config, current_config, config_hash, change_reason, changed_by)
            VALUES (?, ?, ?, 1, 'CREATE', NULL, ?, ?, 'Initial baseline creation', ?)
            """,
            (
                history_id,
                baseline.resource_type,
                baseline.resource_id,
                json.dumps(baseline.config, ensure_ascii=False),
                config_hash,
                created_by,
            ),
        )

        self.conn.commit()

        return Baseline(
            resource_type=baseline.resource_type,
            resource_id=baseline.resource_id,
            version=1,
            config=baseline.config,
            config_hash=config_hash,
            resource_arn=baseline.resource_arn,
            description=baseline.description,
            tags=baseline.tags,
            created_at=datetime.fromisoformat(now.rstrip("Z")),
            updated_at=datetime.fromisoformat(now.rstrip("Z")),
            created_by=created_by,
            updated_by=created_by,
        )

    def update_baseline(
        self,
        resource_type: str,
        resource_id: str,
        config: Dict[str, Any],
        updated_by: str,
        reason: Optional[str] = None,
    ) -> Optional[Baseline]:
        """베이스라인 업데이트."""
        # 현재 베이스라인 조회
        current = self.get_baseline(resource_type, resource_id)
        if current is None:
            return None

        new_hash = Baseline.compute_hash(config)

        # 변경 없으면 스킵
        if new_hash == current.config_hash:
            logger.info(f"No changes for {resource_type}/{resource_id}")
            return current

        new_version = current.version + 1
        now = datetime.utcnow().isoformat() + "Z"

        cursor = self.conn.cursor()

        # 베이스라인 업데이트
        cursor.execute(
            """
            UPDATE drift_baselines
            SET version = ?, config = ?, config_hash = ?, updated_at = ?, updated_by = ?
            WHERE resource_type = ? AND resource_id = ?
            """,
            (
                new_version,
                json.dumps(config, ensure_ascii=False),
                new_hash,
                now,
                updated_by,
                resource_type,
                resource_id,
            ),
        )

        # 히스토리 기록
        history_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO drift_baseline_history
            (id, resource_type, resource_id, version, change_type,
             previous_config, current_config, config_hash, change_reason, changed_by)
            VALUES (?, ?, ?, ?, 'UPDATE', ?, ?, ?, ?, ?)
            """,
            (
                history_id,
                resource_type,
                resource_id,
                new_version,
                json.dumps(current.config, ensure_ascii=False),
                json.dumps(config, ensure_ascii=False),
                new_hash,
                reason,
                updated_by,
            ),
        )

        self.conn.commit()

        current.version = new_version
        current.config = config
        current.config_hash = new_hash
        current.updated_at = datetime.fromisoformat(now.rstrip("Z"))
        current.updated_by = updated_by

        return current

    def delete_baseline(self, resource_type: str, resource_id: str) -> bool:
        """베이스라인 삭제."""
        current = self.get_baseline(resource_type, resource_id)
        if current is None:
            return False

        cursor = self.conn.cursor()

        # 히스토리 기록 (삭제 전)
        history_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO drift_baseline_history
            (id, resource_type, resource_id, version, change_type,
             previous_config, current_config, config_hash, changed_by)
            VALUES (?, ?, ?, ?, 'DELETE', ?, '{"_deleted": true}', ?, 'system')
            """,
            (
                history_id,
                resource_type,
                resource_id,
                current.version + 1,
                json.dumps(current.config, ensure_ascii=False),
                current.config_hash,
            ),
        )

        # 베이스라인 삭제
        cursor.execute(
            "DELETE FROM drift_baselines WHERE resource_type = ? AND resource_id = ?",
            (resource_type, resource_id),
        )

        self.conn.commit()
        return True

    def get_version_history(
        self,
        resource_type: str,
        resource_id: str,
    ) -> List[BaselineHistory]:
        """버전 이력 조회."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM drift_baseline_history
            WHERE resource_type = ? AND resource_id = ?
            ORDER BY version DESC
            """,
            (resource_type, resource_id),
        )

        return [self._row_to_history(row) for row in cursor.fetchall()]

    def _row_to_baseline(self, row: sqlite3.Row) -> Baseline:
        """Row를 Baseline으로 변환."""
        created_at = None
        if row["created_at"]:
            created_at = datetime.fromisoformat(row["created_at"].rstrip("Z"))

        updated_at = None
        if row["updated_at"]:
            updated_at = datetime.fromisoformat(row["updated_at"].rstrip("Z"))

        tags = None
        if row["tags"]:
            tags = json.loads(row["tags"])

        return Baseline(
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            version=row["version"],
            config=json.loads(row["config"]),
            config_hash=row["config_hash"],
            resource_arn=row["resource_arn"],
            description=row["description"],
            tags=tags,
            created_at=created_at,
            updated_at=updated_at,
            created_by=row["created_by"],
            updated_by=row["updated_by"],
        )

    def _row_to_history(self, row: sqlite3.Row) -> BaselineHistory:
        """Row를 BaselineHistory로 변환."""
        changed_at = None
        if row["changed_at"]:
            changed_at = datetime.fromisoformat(row["changed_at"].rstrip("Z"))

        previous_config = None
        if row["previous_config"]:
            previous_config = json.loads(row["previous_config"])

        return BaselineHistory(
            id=row["id"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            version=row["version"],
            change_type=row["change_type"],
            previous_config=previous_config,
            current_config=json.loads(row["current_config"]),
            config_hash=row["config_hash"],
            change_reason=row["change_reason"],
            changed_at=changed_at,
            changed_by=row["changed_by"],
        )


class MockProvider(BaselineStoreProvider):
    """Mock 프로바이더 (개발/테스트용)."""

    def __init__(self):
        """Mock 프로바이더 초기화."""
        self._baselines: Dict[str, Baseline] = {}
        self._history: List[BaselineHistory] = []
        logger.info("Mock provider initialized")

    def _key(self, resource_type: str, resource_id: str) -> str:
        """복합 키 생성."""
        return f"{resource_type}:{resource_id}"

    def ensure_tables(self) -> None:
        """테이블 생성 (Mock은 no-op)."""
        pass

    def get_baseline(self, resource_type: str, resource_id: str) -> Optional[Baseline]:
        """베이스라인 조회."""
        return self._baselines.get(self._key(resource_type, resource_id))

    def list_baselines(self, resource_type: Optional[str] = None) -> List[Baseline]:
        """베이스라인 목록 조회."""
        baselines = list(self._baselines.values())
        if resource_type:
            baselines = [b for b in baselines if b.resource_type == resource_type]
        return sorted(baselines, key=lambda b: (b.resource_type, b.resource_id))

    def create_baseline(
        self,
        baseline: BaselineCreate,
        created_by: str,
    ) -> Baseline:
        """베이스라인 생성."""
        config_hash = Baseline.compute_hash(baseline.config)
        now = datetime.utcnow()

        new_baseline = Baseline(
            resource_type=baseline.resource_type,
            resource_id=baseline.resource_id,
            version=1,
            config=baseline.config,
            config_hash=config_hash,
            resource_arn=baseline.resource_arn,
            description=baseline.description,
            tags=baseline.tags,
            created_at=now,
            updated_at=now,
            created_by=created_by,
            updated_by=created_by,
        )

        key = self._key(baseline.resource_type, baseline.resource_id)
        self._baselines[key] = new_baseline

        # 히스토리 기록
        self._history.append(
            BaselineHistory(
                id=str(uuid.uuid4()),
                resource_type=baseline.resource_type,
                resource_id=baseline.resource_id,
                version=1,
                change_type=ChangeType.CREATE.value,
                previous_config=None,
                current_config=baseline.config,
                config_hash=config_hash,
                change_reason="Initial baseline creation",
                changed_at=now,
                changed_by=created_by,
            )
        )

        return new_baseline

    def update_baseline(
        self,
        resource_type: str,
        resource_id: str,
        config: Dict[str, Any],
        updated_by: str,
        reason: Optional[str] = None,
    ) -> Optional[Baseline]:
        """베이스라인 업데이트."""
        current = self.get_baseline(resource_type, resource_id)
        if current is None:
            return None

        new_hash = Baseline.compute_hash(config)
        if new_hash == current.config_hash:
            return current

        now = datetime.utcnow()
        new_version = current.version + 1

        # 히스토리 기록
        self._history.append(
            BaselineHistory(
                id=str(uuid.uuid4()),
                resource_type=resource_type,
                resource_id=resource_id,
                version=new_version,
                change_type=ChangeType.UPDATE.value,
                previous_config=current.config,
                current_config=config,
                config_hash=new_hash,
                change_reason=reason,
                changed_at=now,
                changed_by=updated_by,
            )
        )

        # 업데이트
        current.version = new_version
        current.config = config
        current.config_hash = new_hash
        current.updated_at = now
        current.updated_by = updated_by

        return current

    def delete_baseline(self, resource_type: str, resource_id: str) -> bool:
        """베이스라인 삭제."""
        key = self._key(resource_type, resource_id)
        if key not in self._baselines:
            return False

        current = self._baselines[key]
        now = datetime.utcnow()

        # 히스토리 기록
        self._history.append(
            BaselineHistory(
                id=str(uuid.uuid4()),
                resource_type=resource_type,
                resource_id=resource_id,
                version=current.version + 1,
                change_type=ChangeType.DELETE.value,
                previous_config=current.config,
                current_config={"_deleted": True},
                config_hash=current.config_hash,
                changed_at=now,
                changed_by="system",
            )
        )

        del self._baselines[key]
        return True

    def get_version_history(
        self,
        resource_type: str,
        resource_id: str,
    ) -> List[BaselineHistory]:
        """버전 이력 조회."""
        history = [
            h
            for h in self._history
            if h.resource_type == resource_type and h.resource_id == resource_id
        ]
        return sorted(history, key=lambda h: h.version, reverse=True)


class BaselineStore:
    """
    베이스라인 설정 저장소 (Facade).

    Provider 패턴으로 MySQL/SQLite/Mock 지원.

    Usage:
        store = BaselineStore(provider="sqlite")
        store.ensure_tables()
        baseline = store.create_baseline(...)
    """

    def __init__(self, provider: str = "mock"):
        """BaselineStore 초기화.

        Args:
            provider: 프로바이더 타입 ("mysql", "sqlite", "mock")
        """
        self.provider_type = provider
        self._provider = self._create_provider(provider)
        logger.info(f"BaselineStore initialized with {provider} provider")

    def _create_provider(self, provider: str) -> BaselineStoreProvider:
        """프로바이더 생성."""
        if provider == "sqlite":
            db_path = os.getenv("BASELINE_SQLITE_PATH", ":memory:")
            return SQLiteProvider(db_path)
        elif provider == "mysql":
            # MySQL 프로바이더는 추후 구현
            raise NotImplementedError("MySQL provider not yet implemented")
        else:
            return MockProvider()

    def ensure_tables(self) -> None:
        """테이블 생성 확인."""
        self._provider.ensure_tables()

    def get_baseline(self, resource_type: str, resource_id: str) -> Optional[Baseline]:
        """베이스라인 조회."""
        return self._provider.get_baseline(resource_type, resource_id)

    def list_baselines(self, resource_type: Optional[str] = None) -> List[Baseline]:
        """베이스라인 목록 조회."""
        return self._provider.list_baselines(resource_type)

    def create_baseline(
        self,
        resource_type: str,
        resource_id: str,
        config: Dict[str, Any],
        created_by: str,
        resource_arn: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> Baseline:
        """베이스라인 생성."""
        baseline = BaselineCreate(
            resource_type=resource_type,
            resource_id=resource_id,
            config=config,
            resource_arn=resource_arn,
            description=description,
            tags=tags,
        )
        return self._provider.create_baseline(baseline, created_by)

    def update_baseline(
        self,
        resource_type: str,
        resource_id: str,
        config: Dict[str, Any],
        updated_by: str,
        reason: Optional[str] = None,
    ) -> Optional[Baseline]:
        """베이스라인 업데이트."""
        return self._provider.update_baseline(
            resource_type, resource_id, config, updated_by, reason
        )

    def delete_baseline(self, resource_type: str, resource_id: str) -> bool:
        """베이스라인 삭제."""
        return self._provider.delete_baseline(resource_type, resource_id)

    def get_version_history(
        self,
        resource_type: str,
        resource_id: str,
    ) -> List[BaselineHistory]:
        """버전 이력 조회."""
        return self._provider.get_version_history(resource_type, resource_id)

    def get_baseline_at_version(
        self,
        resource_type: str,
        resource_id: str,
        version: int,
    ) -> Optional[Baseline]:
        """특정 버전의 베이스라인 조회."""
        history = self.get_version_history(resource_type, resource_id)
        for h in history:
            if h.version == version:
                return Baseline(
                    resource_type=h.resource_type,
                    resource_id=h.resource_id,
                    version=h.version,
                    config=h.current_config,
                    config_hash=h.config_hash,
                    updated_at=h.changed_at,
                )
        return None

    def rollback_to_version(
        self,
        resource_type: str,
        resource_id: str,
        version: int,
        rolled_back_by: str,
    ) -> Optional[Baseline]:
        """특정 버전으로 롤백."""
        target = self.get_baseline_at_version(resource_type, resource_id, version)
        if target is None:
            return None

        return self.update_baseline(
            resource_type,
            resource_id,
            target.config,
            rolled_back_by,
            reason=f"Rollback to version {version}",
        )

    def compare_versions(
        self,
        resource_type: str,
        resource_id: str,
        version_a: int,
        version_b: int,
    ) -> Dict[str, Any]:
        """두 버전 비교."""
        baseline_a = self.get_baseline_at_version(resource_type, resource_id, version_a)
        baseline_b = self.get_baseline_at_version(resource_type, resource_id, version_b)

        if baseline_a is None or baseline_b is None:
            return {"error": "One or both versions not found"}

        # 차이점 계산
        diff = self._compare_configs(baseline_a.config, baseline_b.config)

        return {
            "version_a": version_a,
            "version_b": version_b,
            "config_a": baseline_a.config,
            "config_b": baseline_b.config,
            "differences": diff,
        }

    def _compare_configs(
        self,
        config_a: Dict[str, Any],
        config_b: Dict[str, Any],
        path: str = "",
    ) -> List[Dict[str, Any]]:
        """두 설정 비교."""
        differences = []

        all_keys = set(config_a.keys()) | set(config_b.keys())

        for key in all_keys:
            current_path = f"{path}.{key}" if path else key

            if key not in config_a:
                differences.append({
                    "path": current_path,
                    "type": "added",
                    "value": config_b[key],
                })
            elif key not in config_b:
                differences.append({
                    "path": current_path,
                    "type": "removed",
                    "value": config_a[key],
                })
            elif config_a[key] != config_b[key]:
                if isinstance(config_a[key], dict) and isinstance(config_b[key], dict):
                    differences.extend(
                        self._compare_configs(config_a[key], config_b[key], current_path)
                    )
                else:
                    differences.append({
                        "path": current_path,
                        "type": "changed",
                        "old_value": config_a[key],
                        "new_value": config_b[key],
                    })

        return differences
