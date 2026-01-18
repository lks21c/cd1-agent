"""
Configuration Drift Detector.

Compares baseline configurations from GitLab with current AWS configurations
to detect and classify configuration drifts.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class DriftSeverity(str, Enum):
    """Drift severity levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DriftType(str, Enum):
    """Types of drift changes."""

    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    REMOVED = "REMOVED"


# Severity mapping for different field types
SEVERITY_MAPPING = {
    # CRITICAL - Security related
    "encryption_config": DriftSeverity.CRITICAL,
    "encryption_info": DriftSeverity.CRITICAL,
    "encryption_at_rest": DriftSeverity.CRITICAL,
    "encryption_in_transit": DriftSeverity.CRITICAL,
    "endpoint_public_access": DriftSeverity.CRITICAL,
    "public_access_block": DriftSeverity.CRITICAL,
    "block_public_acls": DriftSeverity.CRITICAL,
    "block_public_policy": DriftSeverity.CRITICAL,
    "restrict_public_buckets": DriftSeverity.CRITICAL,
    "webserver_access_mode": DriftSeverity.CRITICAL,

    # HIGH - Major specs
    "version": DriftSeverity.HIGH,
    "release_label": DriftSeverity.HIGH,
    "kafka_version": DriftSeverity.HIGH,
    "airflow_version": DriftSeverity.HIGH,
    "instance_type": DriftSeverity.HIGH,
    "instance_types": DriftSeverity.HIGH,
    "environment_class": DriftSeverity.HIGH,
    "number_of_broker_nodes": DriftSeverity.HIGH,
    "ami_type": DriftSeverity.HIGH,
    "capacity_type": DriftSeverity.HIGH,

    # MEDIUM - Scaling/capacity
    "scaling_config": DriftSeverity.MEDIUM,
    "min_size": DriftSeverity.MEDIUM,
    "max_size": DriftSeverity.MEDIUM,
    "desired_size": DriftSeverity.MEDIUM,
    "min_workers": DriftSeverity.MEDIUM,
    "max_workers": DriftSeverity.MEDIUM,
    "schedulers": DriftSeverity.MEDIUM,
    "instance_count": DriftSeverity.MEDIUM,
    "volume_size": DriftSeverity.MEDIUM,
    "disk_size": DriftSeverity.MEDIUM,
    "storage_info": DriftSeverity.MEDIUM,

    # LOW - Metadata
    "tags": DriftSeverity.LOW,
    "logging": DriftSeverity.LOW,
    "logging_configuration": DriftSeverity.LOW,
    "enhanced_monitoring": DriftSeverity.LOW,
}

# Fields to ignore during comparison
IGNORE_FIELDS = {
    "fetched_at",
    "last_modified",
    "created_at",
    "updated_at",
    "resource_arn",
    "arn",
}


@dataclass
class DriftedField:
    """Represents a single drifted field."""

    field_path: str
    drift_type: DriftType
    baseline_value: Any
    current_value: Any
    severity: DriftSeverity

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "field": self.field_path,
            "drift_type": self.drift_type.value,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "severity": self.severity.value,
        }


@dataclass
class DriftResult:
    """Result of drift detection for a single resource."""

    resource_type: str
    resource_id: str
    resource_arn: str
    has_drift: bool
    drifted_fields: List[DriftedField]
    max_severity: Optional[DriftSeverity]
    baseline_version: str
    detection_timestamp: str

    @property
    def added_count(self) -> int:
        """Count of added fields."""
        return sum(1 for f in self.drifted_fields if f.drift_type == DriftType.ADDED)

    @property
    def modified_count(self) -> int:
        """Count of modified fields."""
        return sum(1 for f in self.drifted_fields if f.drift_type == DriftType.MODIFIED)

    @property
    def removed_count(self) -> int:
        """Count of removed fields."""
        return sum(1 for f in self.drifted_fields if f.drift_type == DriftType.REMOVED)

    @property
    def critical_count(self) -> int:
        """Count of critical drifts."""
        return sum(1 for f in self.drifted_fields if f.severity == DriftSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        """Count of high severity drifts."""
        return sum(1 for f in self.drifted_fields if f.severity == DriftSeverity.HIGH)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_arn": self.resource_arn,
            "has_drift": self.has_drift,
            "severity": self.max_severity.value if self.max_severity else None,
            "drifted_fields": [f.to_dict() for f in self.drifted_fields],
            "drift_summary": {
                "added_fields": self.added_count,
                "modified_fields": self.modified_count,
                "removed_fields": self.removed_count,
            },
            "baseline_version": self.baseline_version,
            "detection_timestamp": self.detection_timestamp,
        }


@dataclass
class AggregatedDriftResult:
    """Aggregated drift detection results across multiple resources."""

    drifts: List[DriftResult] = field(default_factory=list)
    resources_analyzed: int = 0
    detection_timestamp: str = ""
    baseline_info: Dict[str, str] = field(default_factory=dict)

    @property
    def has_drifts(self) -> bool:
        """Check if any drifts were detected."""
        return any(d.has_drift for d in self.drifts)

    @property
    def total_drift_count(self) -> int:
        """Total number of drifted fields across all resources."""
        return sum(len(d.drifted_fields) for d in self.drifts)

    @property
    def severity_summary(self) -> Dict[str, int]:
        """Summary of drifts by severity."""
        summary = {s.value: 0 for s in DriftSeverity}
        for drift in self.drifts:
            for field in drift.drifted_fields:
                summary[field.severity.value] += 1
        return summary

    @property
    def drift_details(self) -> List[Dict[str, Any]]:
        """List of drift details for resources with drifts."""
        return [d.to_dict() for d in self.drifts if d.has_drift]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "drifts_detected": self.has_drifts,
            "total_drift_count": self.total_drift_count,
            "severity_summary": self.severity_summary,
            "resources_analyzed": self.resources_analyzed,
            "drift_details": self.drift_details,
            "baseline_info": self.baseline_info,
            "detection_timestamp": self.detection_timestamp,
        }


class ConfigDriftDetector:
    """Detects configuration drifts between baseline and current configs."""

    def __init__(
        self,
        severity_mapping: Optional[Dict[str, DriftSeverity]] = None,
        ignore_fields: Optional[Set[str]] = None,
        tolerance_rules: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        """
        Initialize drift detector.

        Args:
            severity_mapping: Custom severity mapping for fields
            ignore_fields: Fields to ignore during comparison
            tolerance_rules: Tolerance rules for specific fields
        """
        self.severity_mapping = severity_mapping or SEVERITY_MAPPING
        self.ignore_fields = ignore_fields or IGNORE_FIELDS
        self.tolerance_rules = tolerance_rules or {}

    def detect(
        self,
        baseline: Dict[str, Any],
        current: Dict[str, Any],
        resource_type: str,
        resource_id: str,
        resource_arn: str = "",
        baseline_version: str = "",
    ) -> DriftResult:
        """
        Detect drift between baseline and current configuration.

        Args:
            baseline: Baseline configuration from GitLab
            current: Current configuration from AWS
            resource_type: Type of resource (EKS, MSK, etc.)
            resource_id: Resource identifier
            resource_arn: Resource ARN
            baseline_version: Git commit SHA of baseline

        Returns:
            DriftResult with detected drifts
        """
        from datetime import datetime

        drifted_fields = []

        # Compare configurations recursively
        self._compare_dicts(
            baseline=baseline,
            current=current,
            path="",
            drifted_fields=drifted_fields,
        )

        # Determine max severity
        max_severity = None
        if drifted_fields:
            severity_order = [
                DriftSeverity.CRITICAL,
                DriftSeverity.HIGH,
                DriftSeverity.MEDIUM,
                DriftSeverity.LOW,
            ]
            for severity in severity_order:
                if any(f.severity == severity for f in drifted_fields):
                    max_severity = severity
                    break

        return DriftResult(
            resource_type=resource_type,
            resource_id=resource_id,
            resource_arn=resource_arn,
            has_drift=len(drifted_fields) > 0,
            drifted_fields=drifted_fields,
            max_severity=max_severity,
            baseline_version=baseline_version,
            detection_timestamp=datetime.utcnow().isoformat(),
        )

    def _compare_dicts(
        self,
        baseline: Dict[str, Any],
        current: Dict[str, Any],
        path: str,
        drifted_fields: List[DriftedField],
    ) -> None:
        """Recursively compare two dictionaries."""
        all_keys = set(baseline.keys()) | set(current.keys())

        for key in all_keys:
            # Skip ignored fields
            if key in self.ignore_fields:
                continue

            field_path = f"{path}.{key}" if path else key

            if key not in baseline:
                # Field added in current config
                drifted_fields.append(DriftedField(
                    field_path=field_path,
                    drift_type=DriftType.ADDED,
                    baseline_value=None,
                    current_value=current[key],
                    severity=self._get_severity(key, field_path),
                ))
            elif key not in current:
                # Field removed from current config
                drifted_fields.append(DriftedField(
                    field_path=field_path,
                    drift_type=DriftType.REMOVED,
                    baseline_value=baseline[key],
                    current_value=None,
                    severity=self._get_severity(key, field_path),
                ))
            else:
                baseline_val = baseline[key]
                current_val = current[key]

                # Check if values are within tolerance
                if self._within_tolerance(field_path, baseline_val, current_val):
                    continue

                # Handle different types
                if isinstance(baseline_val, dict) and isinstance(current_val, dict):
                    # Recurse into nested dicts
                    self._compare_dicts(
                        baseline_val,
                        current_val,
                        field_path,
                        drifted_fields,
                    )
                elif isinstance(baseline_val, list) and isinstance(current_val, list):
                    # Compare lists
                    self._compare_lists(
                        baseline_val,
                        current_val,
                        field_path,
                        drifted_fields,
                    )
                elif self._normalize_value(baseline_val) != self._normalize_value(current_val):
                    # Simple value comparison
                    drifted_fields.append(DriftedField(
                        field_path=field_path,
                        drift_type=DriftType.MODIFIED,
                        baseline_value=baseline_val,
                        current_value=current_val,
                        severity=self._get_severity(key, field_path),
                    ))

    def _compare_lists(
        self,
        baseline: List[Any],
        current: List[Any],
        path: str,
        drifted_fields: List[DriftedField],
    ) -> None:
        """Compare two lists, handling both simple and complex items."""
        # Check if lists contain dicts (e.g., node_groups)
        if baseline and isinstance(baseline[0], dict):
            # Try to match by name/id field
            baseline_by_name = {
                self._get_item_key(item): item for item in baseline
            }
            current_by_name = {
                self._get_item_key(item): item for item in current
            }

            all_names = set(baseline_by_name.keys()) | set(current_by_name.keys())

            for idx, name in enumerate(all_names):
                item_path = f"{path}[{idx}]"

                if name not in baseline_by_name:
                    drifted_fields.append(DriftedField(
                        field_path=item_path,
                        drift_type=DriftType.ADDED,
                        baseline_value=None,
                        current_value=current_by_name[name],
                        severity=self._get_severity(path.split(".")[-1], path),
                    ))
                elif name not in current_by_name:
                    drifted_fields.append(DriftedField(
                        field_path=item_path,
                        drift_type=DriftType.REMOVED,
                        baseline_value=baseline_by_name[name],
                        current_value=None,
                        severity=self._get_severity(path.split(".")[-1], path),
                    ))
                else:
                    self._compare_dicts(
                        baseline_by_name[name],
                        current_by_name[name],
                        item_path,
                        drifted_fields,
                    )
        else:
            # Simple list comparison
            baseline_set = set(str(v) for v in baseline)
            current_set = set(str(v) for v in current)

            if baseline_set != current_set:
                drifted_fields.append(DriftedField(
                    field_path=path,
                    drift_type=DriftType.MODIFIED,
                    baseline_value=baseline,
                    current_value=current,
                    severity=self._get_severity(path.split(".")[-1], path),
                ))

    def _get_item_key(self, item: Dict[str, Any]) -> str:
        """Get unique key for a list item."""
        # Try common key fields
        for key_field in ["name", "id", "key", "Name", "Id"]:
            if key_field in item:
                return str(item[key_field])
        # Fall back to hash of item
        return str(hash(frozenset(str(v) for v in item.values())))

    def _get_severity(self, field_name: str, field_path: str) -> DriftSeverity:
        """Determine severity for a field."""
        # Check exact field name first
        if field_name in self.severity_mapping:
            return self.severity_mapping[field_name]

        # Check if any part of the path matches
        path_parts = field_path.split(".")
        for part in path_parts:
            # Remove array indices
            clean_part = part.split("[")[0]
            if clean_part in self.severity_mapping:
                return self.severity_mapping[clean_part]

        # Default to MEDIUM
        return DriftSeverity.MEDIUM

    def _within_tolerance(
        self,
        field_path: str,
        baseline_val: Any,
        current_val: Any,
    ) -> bool:
        """Check if values are within tolerance."""
        if field_path not in self.tolerance_rules:
            return False

        rule = self.tolerance_rules[field_path]
        rule_type = rule.get("type")

        if rule_type == "ignore":
            return True

        if rule_type == "percentage":
            threshold = rule.get("threshold", 0)
            try:
                baseline_num = float(baseline_val)
                current_num = float(current_val)
                if baseline_num == 0:
                    return current_num == 0
                change_pct = abs(current_num - baseline_num) / baseline_num * 100
                return change_pct <= threshold
            except (TypeError, ValueError):
                return False

        return False

    def _normalize_value(self, value: Any) -> Any:
        """Normalize value for comparison."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return value.lower().strip()
        return value


# Module-level convenience function
def detect_drift(
    baseline: Dict[str, Any],
    current: Dict[str, Any],
    resource_type: str,
    resource_id: str,
    resource_arn: str = "",
    baseline_version: str = "",
) -> DriftResult:
    """Detect drift between baseline and current configuration."""
    detector = ConfigDriftDetector()
    return detector.detect(
        baseline=baseline,
        current=current,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_arn=resource_arn,
        baseline_version=baseline_version,
    )


if __name__ == "__main__":
    # Test drift detection
    baseline = {
        "cluster_name": "production-eks",
        "version": "1.29",
        "node_groups": [
            {
                "name": "general-workload",
                "instance_types": ["m6i.xlarge", "m6i.2xlarge"],
                "scaling_config": {
                    "min_size": 3,
                    "max_size": 10,
                    "desired_size": 5,
                },
            }
        ],
        "tags": {"Environment": "production"},
    }

    current = {
        "cluster_name": "production-eks",
        "version": "1.29",
        "node_groups": [
            {
                "name": "general-workload",
                "instance_types": ["m5.large"],  # DRIFT
                "scaling_config": {
                    "min_size": 3,
                    "max_size": 10,
                    "desired_size": 3,  # DRIFT
                },
            }
        ],
        "tags": {"Environment": "production"},
    }

    result = detect_drift(
        baseline=baseline,
        current=current,
        resource_type="EKS",
        resource_id="production-eks",
        baseline_version="abc123",
    )

    print(f"Has drift: {result.has_drift}")
    print(f"Max severity: {result.max_severity}")
    print(f"Drifted fields:")
    for field in result.drifted_fields:
        print(f"  - {field.field_path}: {field.baseline_value} → {field.current_value} ({field.severity})")
