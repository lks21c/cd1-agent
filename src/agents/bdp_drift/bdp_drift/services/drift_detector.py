"""
Drift Detector - Configuration drift detection logic.

베이스라인과 현재 설정 비교를 통한 드리프트 탐지.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.agents.bdp_drift.bdp_drift.services.models import (
    Baseline,
    DriftCategory,
    DriftField,
    DriftResult,
    DriftSeverity,
    get_field_severity,
)
from src.agents.bdp_drift.bdp_drift.services.baseline_store import BaselineStore
from src.agents.bdp_drift.bdp_drift.services.config_fetcher import ConfigFetcher, ResourceConfig

logger = logging.getLogger(__name__)


class DriftDetector:
    """
    드리프트 탐지기.

    베이스라인과 현재 설정을 비교하여 드리프트 탐지.

    Usage:
        detector = DriftDetector(baseline_store, config_fetcher)
        results = detector.detect_all()
    """

    # 무시할 필드 목록 (동적/임시 값)
    IGNORE_FIELDS: Set[str] = {
        "last_modified_time",
        "create_time",
        "update_time",
        "last_access_time",
        "version_id",
        "code_sha256",
        "last_modified",
        "creation_date",
    }

    def __init__(
        self,
        baseline_store: BaselineStore,
        config_fetcher: ConfigFetcher,
        ignore_fields: Optional[Set[str]] = None,
    ):
        """DriftDetector 초기화.

        Args:
            baseline_store: 베이스라인 저장소
            config_fetcher: 설정 조회기
            ignore_fields: 추가로 무시할 필드 목록
        """
        self.baseline_store = baseline_store
        self.config_fetcher = config_fetcher
        self.ignore_fields = self.IGNORE_FIELDS.copy()
        if ignore_fields:
            self.ignore_fields.update(ignore_fields)

        logger.info("DriftDetector initialized")

    def detect(
        self,
        resource_type: str,
        resource_id: str,
    ) -> Optional[DriftResult]:
        """단일 리소스 드리프트 탐지.

        Args:
            resource_type: 리소스 타입
            resource_id: 리소스 ID

        Returns:
            DriftResult 또는 None (베이스라인 없음)
        """
        # 베이스라인 조회
        baseline = self.baseline_store.get_baseline(resource_type, resource_id)
        if baseline is None:
            logger.warning(f"No baseline found for {resource_type}/{resource_id}")
            return None

        # 현재 설정 조회
        current = self.config_fetcher.fetch_config(resource_type, resource_id)
        if current is None:
            logger.warning(f"Failed to fetch current config for {resource_type}/{resource_id}")
            return DriftResult(
                resource_type=resource_type,
                resource_id=resource_id,
                resource_arn=baseline.resource_arn,
                has_drift=True,
                severity=DriftSeverity.CRITICAL,
                drift_fields=[
                    DriftField(
                        field_name="_resource_exists",
                        baseline_value=True,
                        current_value=False,
                        severity=DriftSeverity.CRITICAL,
                        description="리소스가 존재하지 않습니다",
                    )
                ],
                baseline_config=baseline.config,
                current_config={},
                baseline_version=baseline.version,
                detection_timestamp=datetime.utcnow(),
            )

        # 설정 비교
        drift_fields = self._compare_configs(
            baseline.config,
            current.config,
        )

        # 결과 생성
        has_drift = len(drift_fields) > 0
        severity = self._calculate_severity(drift_fields) if has_drift else DriftSeverity.LOW

        return DriftResult(
            resource_type=resource_type,
            resource_id=resource_id,
            resource_arn=current.resource_arn,
            has_drift=has_drift,
            severity=severity,
            drift_fields=drift_fields,
            baseline_config=baseline.config,
            current_config=current.config,
            baseline_version=baseline.version,
            detection_timestamp=datetime.utcnow(),
            account_id=current.account_id,
        )

    def detect_by_type(self, resource_type: str) -> List[DriftResult]:
        """리소스 타입별 드리프트 탐지.

        Args:
            resource_type: 리소스 타입

        Returns:
            DriftResult 목록
        """
        results = []

        # 해당 타입의 모든 베이스라인 조회
        baselines = self.baseline_store.list_baselines(resource_type)

        for baseline in baselines:
            result = self.detect(baseline.resource_type, baseline.resource_id)
            if result:
                results.append(result)

        return results

    def detect_all(
        self,
        resource_types: Optional[List[str]] = None,
    ) -> List[DriftResult]:
        """모든 리소스 드리프트 탐지.

        Args:
            resource_types: 대상 리소스 타입 목록 (None이면 모든 타입)

        Returns:
            DriftResult 목록
        """
        results = []

        # 모든 베이스라인 조회
        baselines = self.baseline_store.list_baselines()

        for baseline in baselines:
            # 필터링
            if resource_types and baseline.resource_type not in resource_types:
                continue

            result = self.detect(baseline.resource_type, baseline.resource_id)
            if result:
                results.append(result)

        return results

    def _compare_configs(
        self,
        baseline: Dict[str, Any],
        current: Dict[str, Any],
        path: str = "",
    ) -> List[DriftField]:
        """두 설정 비교.

        Args:
            baseline: 베이스라인 설정
            current: 현재 설정
            path: 현재 경로 (중첩 객체용)

        Returns:
            DriftField 목록
        """
        drift_fields = []

        all_keys = set(baseline.keys()) | set(current.keys())

        for key in all_keys:
            # 무시할 필드 스킵
            if key.lower() in {f.lower() for f in self.ignore_fields}:
                continue

            current_path = f"{path}.{key}" if path else key
            baseline_value = baseline.get(key)
            current_value = current.get(key)

            # 키가 베이스라인에만 있음 (삭제됨) → DISCOVERED
            if key not in current:
                drift_fields.append(
                    DriftField(
                        field_name=current_path,
                        baseline_value=baseline_value,
                        current_value=None,
                        severity=get_field_severity(key),
                        category=DriftCategory.DISCOVERED,
                        description=f"필드가 삭제되었습니다: {key}",
                    )
                )
                continue

            # 키가 현재 설정에만 있음 (추가됨) → DISCOVERED
            if key not in baseline:
                drift_fields.append(
                    DriftField(
                        field_name=current_path,
                        baseline_value=None,
                        current_value=current_value,
                        severity=get_field_severity(key),
                        category=DriftCategory.DISCOVERED,
                        description=f"필드가 추가되었습니다: {key}",
                    )
                )
                continue

            # 값 비교
            if baseline_value != current_value:
                # 중첩 딕셔너리
                if isinstance(baseline_value, dict) and isinstance(current_value, dict):
                    nested = self._compare_configs(
                        baseline_value,
                        current_value,
                        current_path,
                    )
                    drift_fields.extend(nested)
                # 리스트
                elif isinstance(baseline_value, list) and isinstance(current_value, list):
                    if self._list_differs(baseline_value, current_value):
                        drift_fields.append(
                            DriftField(
                                field_name=current_path,
                                baseline_value=baseline_value,
                                current_value=current_value,
                                severity=get_field_severity(key),
                                description=f"리스트가 변경되었습니다: {key}",
                            )
                        )
                # 단순 값
                else:
                    drift_fields.append(
                        DriftField(
                            field_name=current_path,
                            baseline_value=baseline_value,
                            current_value=current_value,
                            severity=get_field_severity(key),
                            description=f"값이 변경되었습니다: {baseline_value} → {current_value}",
                        )
                    )

        return drift_fields

    def _list_differs(self, list1: List[Any], list2: List[Any]) -> bool:
        """두 리스트 비교.

        순서 무관하게 요소 비교.

        Args:
            list1: 첫 번째 리스트
            list2: 두 번째 리스트

        Returns:
            차이 여부
        """
        if len(list1) != len(list2):
            return True

        # 단순 타입 리스트
        try:
            return set(list1) != set(list2)
        except TypeError:
            # 딕셔너리 등 해시 불가능한 요소
            # 순서대로 비교
            return list1 != list2

    def _calculate_severity(self, drift_fields: List[DriftField]) -> DriftSeverity:
        """드리프트 심각도 계산.

        MONITORED 필드만 심각도 계산에 포함 (DISCOVERED 제외).
        가장 높은 심각도 반환.

        Args:
            drift_fields: 드리프트 필드 목록

        Returns:
            최고 심각도
        """
        if not drift_fields:
            return DriftSeverity.LOW

        # MONITORED 필드만 심각도 계산에 포함
        monitored_fields = [
            f for f in drift_fields
            if f.category == DriftCategory.MONITORED
        ]

        if not monitored_fields:
            return DriftSeverity.LOW  # DISCOVERED 필드만 있으면 LOW

        severity_order = [
            DriftSeverity.CRITICAL,
            DriftSeverity.HIGH,
            DriftSeverity.MEDIUM,
            DriftSeverity.LOW,
        ]

        for severity in severity_order:
            if any(f.severity == severity for f in monitored_fields):
                return severity

        return DriftSeverity.LOW

    def create_baseline_from_current(
        self,
        resource_type: str,
        resource_id: str,
        created_by: str,
        description: Optional[str] = None,
    ) -> Optional[Baseline]:
        """현재 설정으로 베이스라인 생성.

        Args:
            resource_type: 리소스 타입
            resource_id: 리소스 ID
            created_by: 생성자
            description: 설명

        Returns:
            생성된 Baseline 또는 None
        """
        current = self.config_fetcher.fetch_config(resource_type, resource_id)
        if current is None:
            logger.error(f"Cannot create baseline: resource not found {resource_type}/{resource_id}")
            return None

        return self.baseline_store.create_baseline(
            resource_type=resource_type,
            resource_id=resource_id,
            config=current.config,
            created_by=created_by,
            resource_arn=current.resource_arn,
            description=description or f"Baseline for {resource_id}",
        )

    def update_baseline_from_current(
        self,
        resource_type: str,
        resource_id: str,
        updated_by: str,
        reason: Optional[str] = None,
    ) -> Optional[Baseline]:
        """현재 설정으로 베이스라인 업데이트.

        Args:
            resource_type: 리소스 타입
            resource_id: 리소스 ID
            updated_by: 수정자
            reason: 변경 사유

        Returns:
            업데이트된 Baseline 또는 None
        """
        current = self.config_fetcher.fetch_config(resource_type, resource_id)
        if current is None:
            logger.error(f"Cannot update baseline: resource not found {resource_type}/{resource_id}")
            return None

        return self.baseline_store.update_baseline(
            resource_type=resource_type,
            resource_id=resource_id,
            config=current.config,
            updated_by=updated_by,
            reason=reason,
        )


def create_detector(
    baseline_provider: str = "mock",
    use_mock_fetcher: bool = True,
) -> DriftDetector:
    """DriftDetector 팩토리 함수.

    Args:
        baseline_provider: 베이스라인 저장소 프로바이더
        use_mock_fetcher: Mock 설정 조회기 사용 여부

    Returns:
        DriftDetector 인스턴스
    """
    baseline_store = BaselineStore(provider=baseline_provider)
    baseline_store.ensure_tables()

    config_fetcher = ConfigFetcher(use_mock=use_mock_fetcher)

    return DriftDetector(baseline_store, config_fetcher)
