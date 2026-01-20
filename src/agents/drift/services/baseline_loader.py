"""
Baseline Loader with Provider Abstraction.

Loads configuration baselines from local files for drift detection.
Replaces GitLab-based baseline management with file-based loading.
"""

import hashlib
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BaselineProvider(str, Enum):
    """Supported baseline provider modes."""

    REAL = "real"
    MOCK = "mock"
    LOCALSTACK = "localstack"


@dataclass
class BaselineFile:
    """Represents a baseline configuration file."""

    file_path: str
    content: Dict[str, Any]
    file_hash: str  # SHA256 hash for version tracking
    last_modified: str
    baselines_dir: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "content": self.content,
            "file_hash": self.file_hash,
            "last_modified": self.last_modified,
            "baselines_dir": self.baselines_dir,
        }


class BaseBaselineProvider(ABC):
    """Abstract base class for baseline providers."""

    @abstractmethod
    def get_file(
        self,
        resource_type: str,
        resource_id: str,
    ) -> BaselineFile:
        """Get baseline file content."""
        pass

    @abstractmethod
    def list_files(
        self,
        resource_type: Optional[str] = None,
    ) -> List[str]:
        """List baseline files."""
        pass

    @abstractmethod
    def get_file_info(self) -> Dict[str, Any]:
        """Get baseline source information."""
        pass


class RealBaselineProvider(BaseBaselineProvider):
    """Real file-based baseline provider."""

    def __init__(self, baselines_dir: str = "conf/baselines"):
        self.baselines_dir = Path(baselines_dir)
        if not self.baselines_dir.is_absolute():
            # Make path relative to project root
            project_root = Path(__file__).parent.parent.parent.parent.parent
            self.baselines_dir = project_root / baselines_dir

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content (first 12 chars)."""
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]

    def _get_file_mtime(self, file_path: Path) -> str:
        """Get file modification time as ISO string."""
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime).isoformat()

    def get_file(
        self,
        resource_type: str,
        resource_id: str,
    ) -> BaselineFile:
        """Get baseline file content from local filesystem."""
        type_dir = self.baselines_dir / resource_type.lower()
        file_path = type_dir / f"{resource_id}.json"

        if not file_path.exists():
            raise FileNotFoundError(
                f"Baseline not found: {file_path}"
            )

        with open(file_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        try:
            rel_path = file_path.relative_to(self.baselines_dir.parent.parent)
        except ValueError:
            rel_path = file_path

        return BaselineFile(
            file_path=str(rel_path),
            content=content,
            file_hash=self._compute_file_hash(file_path),
            last_modified=self._get_file_mtime(file_path),
            baselines_dir=str(self.baselines_dir),
        )

    def list_files(
        self,
        resource_type: Optional[str] = None,
    ) -> List[str]:
        """List baseline files in directory."""
        if resource_type:
            search_dir = self.baselines_dir / resource_type.lower()
        else:
            search_dir = self.baselines_dir

        if not search_dir.exists():
            return []

        files = []
        for json_file in search_dir.rglob("*.json"):
            if not json_file.name.startswith("_"):
                rel_path = json_file.relative_to(self.baselines_dir)
                files.append(str(rel_path))

        return sorted(files)

    def get_file_info(self) -> Dict[str, Any]:
        """Get baseline source information."""
        return {
            "source": "local_filesystem",
            "baselines_dir": str(self.baselines_dir),
        }


class MockBaselineProvider(BaseBaselineProvider):
    """Mock baseline provider for testing."""

    def __init__(self):
        self._baselines: Dict[str, Dict[str, Any]] = {}
        self._setup_default_baselines()

    def _setup_default_baselines(self):
        """Setup default mock baselines."""
        # EKS baseline
        self.set_baseline("eks", "production-cluster", {
            "cluster_name": "production-eks",
            "version": "1.29",
            "endpoint_public_access": False,
            "endpoint_private_access": True,
            "logging": {
                "api": True,
                "audit": True,
                "authenticator": True,
                "controllerManager": True,
                "scheduler": True,
            },
            "node_groups": [
                {
                    "name": "general-workload",
                    "instance_types": ["m6i.xlarge", "m6i.2xlarge"],
                    "scaling_config": {
                        "min_size": 3,
                        "max_size": 10,
                        "desired_size": 5,
                    },
                    "disk_size": 100,
                    "ami_type": "AL2_x86_64",
                    "capacity_type": "ON_DEMAND",
                }
            ],
            "tags": {
                "Environment": "production",
                "ManagedBy": "cd1-agent",
            },
        })

        # MSK baseline
        self.set_baseline("msk", "production-kafka", {
            "cluster_name": "production-kafka",
            "kafka_version": "3.5.1",
            "broker_config": {
                "instance_type": "kafka.m5.large",
                "number_of_broker_nodes": 3,
                "storage_info": {
                    "ebs_storage_info": {
                        "volume_size": 1000,
                        "provisioned_throughput": {
                            "enabled": True,
                            "volume_throughput": 250,
                        },
                    },
                },
            },
            "encryption_info": {
                "encryption_at_rest": True,
                "encryption_in_transit": "TLS",
            },
            "enhanced_monitoring": "PER_TOPIC_PER_BROKER",
            "tags": {
                "Environment": "production",
            },
        })

        # S3 baseline
        self.set_baseline("s3", "data-lake-bucket", {
            "bucket_name": "company-data-lake-prod",
            "versioning": {
                "status": "Enabled",
            },
            "encryption": {
                "sse_algorithm": "aws:kms",
                "kms_master_key_id": "alias/data-lake-key",
                "bucket_key_enabled": True,
            },
            "public_access_block": {
                "block_public_acls": True,
                "ignore_public_acls": True,
                "block_public_policy": True,
                "restrict_public_buckets": True,
            },
            "tags": {
                "Environment": "production",
                "DataClassification": "confidential",
            },
        })

        # EMR baseline
        self.set_baseline("emr", "analytics-cluster", {
            "cluster_name": "analytics-emr-prod",
            "release_label": "emr-7.0.0",
            "applications": ["Spark", "Hadoop", "Hive"],
            "instance_groups": {
                "master": {
                    "instance_type": "m5.xlarge",
                    "instance_count": 1,
                },
                "core": {
                    "instance_type": "r5.2xlarge",
                    "instance_count": 4,
                },
            },
            "tags": {
                "Environment": "production",
            },
        })

        # MWAA baseline
        self.set_baseline("mwaa", "orchestration-env", {
            "environment_name": "bdp-airflow-prod",
            "airflow_version": "2.8.1",
            "environment_class": "mw1.medium",
            "min_workers": 2,
            "max_workers": 10,
            "schedulers": 2,
            "webserver_access_mode": "PRIVATE_ONLY",
            "tags": {
                "Environment": "production",
            },
        })

    def set_baseline(
        self,
        resource_type: str,
        resource_id: str,
        content: Dict[str, Any],
        file_hash: str = "abc123def456",
    ) -> None:
        """Set mock baseline for testing."""
        key = f"{resource_type.lower()}/{resource_id}"
        self._baselines[key] = {
            "content": content,
            "file_hash": file_hash,
            "last_modified": "2024-01-01T00:00:00",
        }

    def get_file(
        self,
        resource_type: str,
        resource_id: str,
    ) -> BaselineFile:
        """Get mock baseline file."""
        key = f"{resource_type.lower()}/{resource_id}"
        logger.debug(f"Mock BaselineLoader get_file: {key}")

        if key not in self._baselines:
            raise FileNotFoundError(f"Baseline not found: {key}")

        baseline = self._baselines[key]

        return BaselineFile(
            file_path=f"conf/baselines/{key}.json",
            content=baseline["content"],
            file_hash=baseline["file_hash"],
            last_modified=baseline["last_modified"],
            baselines_dir="conf/baselines",
        )

    def list_files(
        self,
        resource_type: Optional[str] = None,
    ) -> List[str]:
        """List mock baseline files."""
        logger.debug(f"Mock BaselineLoader list_files: {resource_type}")

        files = []
        for key in self._baselines.keys():
            if resource_type is None or key.startswith(f"{resource_type.lower()}/"):
                files.append(f"{key}.json")

        return sorted(files)

    def get_file_info(self) -> Dict[str, Any]:
        """Get mock baseline source information."""
        return {
            "source": "mock",
            "baselines_dir": "conf/baselines",
        }


class LocalStackBaselineProvider(BaseBaselineProvider):
    """LocalStack DynamoDB-based baseline provider for testing."""

    def __init__(
        self,
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        """
        Initialize LocalStack baseline provider.

        Args:
            region: AWS region
            endpoint_url: LocalStack endpoint URL
        """
        import boto3

        self.region = region or os.environ.get("AWS_REGION", "ap-northeast-2")
        self.endpoint_url = endpoint_url or os.environ.get(
            "LOCALSTACK_ENDPOINT", "http://localhost:4566"
        )
        self.table_name = os.environ.get(
            "DRIFT_BASELINE_TABLE", "drift-baseline-configs"
        )

        self.dynamodb = boto3.client(
            "dynamodb",
            region_name=self.region,
            endpoint_url=self.endpoint_url,
        )

        logger.info(
            f"LocalStackBaselineProvider initialized: "
            f"endpoint={self.endpoint_url}, table={self.table_name}"
        )

    def get_file(
        self,
        resource_type: str,
        resource_id: str,
    ) -> BaselineFile:
        """
        Get baseline from LocalStack DynamoDB.

        Args:
            resource_type: Resource type (eks, msk, s3, emr, mwaa)
            resource_id: Resource identifier

        Returns:
            BaselineFile with configuration baseline
        """
        pk = f"RESOURCE#{resource_type}#{resource_id}"
        logger.debug(f"LocalStack BaselineLoader get_file: {pk}")

        try:
            response = self.dynamodb.query(
                TableName=self.table_name,
                KeyConditionExpression="pk = :pk",
                ExpressionAttributeValues={
                    ":pk": {"S": pk}
                },
                ScanIndexForward=False,  # Descending (latest first)
                Limit=1,
            )

            items = response.get("Items", [])
            if not items:
                raise FileNotFoundError(
                    f"Baseline not found in LocalStack: {resource_type}/{resource_id}"
                )

            item = items[0]

            # Parse config from JSON string
            import json
            config_str = item.get("config", {}).get("S", "{}")
            config = json.loads(config_str)

            return BaselineFile(
                file_path=f"localstack://{self.table_name}/{resource_type}/{resource_id}",
                content=config,
                file_hash=item.get("config_hash", {}).get("S", "localstack"),
                last_modified=item.get("timestamp", {}).get("S", ""),
                baselines_dir=f"localstack://{self.table_name}",
            )

        except self.dynamodb.exceptions.ResourceNotFoundException:
            raise FileNotFoundError(
                f"DynamoDB table not found: {self.table_name}. "
                "Run 'make drift-init' to create tables."
            )

    def list_files(
        self,
        resource_type: Optional[str] = None,
    ) -> List[str]:
        """
        List baseline files from LocalStack DynamoDB.

        Args:
            resource_type: Filter by resource type

        Returns:
            List of baseline identifiers
        """
        logger.debug(f"LocalStack BaselineLoader list_files: {resource_type}")

        try:
            scan_kwargs = {
                "TableName": self.table_name,
                "ProjectionExpression": "pk, resource_type, resource_id",
            }

            if resource_type:
                scan_kwargs["FilterExpression"] = "resource_type = :rt"
                scan_kwargs["ExpressionAttributeValues"] = {
                    ":rt": {"S": resource_type}
                }

            response = self.dynamodb.scan(**scan_kwargs)
            items = response.get("Items", [])

            files = []
            for item in items:
                rt = item.get("resource_type", {}).get("S", "")
                rid = item.get("resource_id", {}).get("S", "")
                if rt and rid:
                    files.append(f"{rt}/{rid}.json")

            return sorted(files)

        except self.dynamodb.exceptions.ResourceNotFoundException:
            logger.warning(f"DynamoDB table not found: {self.table_name}")
            return []

    def get_file_info(self) -> Dict[str, Any]:
        """Get LocalStack baseline source information."""
        return {
            "source": "localstack",
            "table": self.table_name,
            "endpoint_url": self.endpoint_url,
        }


class BaselineLoader:
    """Baseline loader with automatic provider selection."""

    def __init__(
        self,
        baselines_dir: str = "conf/baselines",
        provider: Optional[BaselineProvider] = None,
        endpoint_url: Optional[str] = None,
    ):
        """
        Initialize baseline loader.

        Args:
            baselines_dir: Path to baseline files directory
            provider: Force specific provider (auto-detect if None)
            endpoint_url: LocalStack endpoint URL (for LOCALSTACK provider)
        """
        self.baselines_dir = baselines_dir

        # Auto-detect provider (DRIFT_PROVIDER takes precedence)
        if provider is None:
            drift_provider = os.environ.get("DRIFT_PROVIDER", "").lower()
            if drift_provider == "localstack":
                provider = BaselineProvider.LOCALSTACK
            elif os.environ.get("AWS_MOCK", "").lower() == "true":
                provider = BaselineProvider.MOCK
            elif os.environ.get("BASELINES_MOCK", "").lower() == "true":
                provider = BaselineProvider.MOCK
            else:
                provider = BaselineProvider.REAL

        self.provider_type = provider

        if provider == BaselineProvider.LOCALSTACK:
            self._provider = LocalStackBaselineProvider(endpoint_url=endpoint_url)
            logger.info("Using LocalStack Baseline Provider")
        elif provider == BaselineProvider.MOCK:
            self._provider = MockBaselineProvider()
            logger.info("Using Mock Baseline Provider")
        else:
            self._provider = RealBaselineProvider(baselines_dir=baselines_dir)
            logger.info(f"Using Real Baseline Provider: {baselines_dir}")

    @property
    def provider(self) -> BaseBaselineProvider:
        """Get the underlying provider."""
        return self._provider

    def get_baseline_file(
        self,
        file_path: str,
    ) -> BaselineFile:
        """
        Get baseline file by path.

        Args:
            file_path: Path like "eks/production-cluster.json"

        Returns:
            BaselineFile with configuration
        """
        # Parse path to extract resource_type and resource_id
        parts = file_path.replace("\\", "/").split("/")
        if len(parts) >= 2:
            resource_type = parts[-2]
            resource_id = parts[-1].replace(".json", "")
        else:
            raise ValueError(f"Invalid file path format: {file_path}")

        return self._provider.get_file(resource_type, resource_id)

    def get_resource_baseline(
        self,
        resource_type: str,
        resource_name: str,
        ref: Optional[str] = None,  # Kept for backward compatibility
    ) -> BaselineFile:
        """
        Get baseline for a specific resource.

        Args:
            resource_type: Resource type (eks, msk, s3, emr, mwaa)
            resource_name: Resource identifier
            ref: Ignored (kept for backward compatibility)

        Returns:
            BaselineFile with configuration baseline
        """
        return self._provider.get_file(resource_type, resource_name)

    def list_baselines(
        self,
        resource_type: Optional[str] = None,
    ) -> List[str]:
        """
        List available baseline files.

        Args:
            resource_type: Filter by resource type (eks, msk, etc.)

        Returns:
            List of baseline file paths
        """
        return self._provider.list_files(resource_type)

    def get_baseline_info(self) -> Dict[str, Any]:
        """
        Get baseline source information.

        Returns:
            Dict with source info
        """
        return self._provider.get_file_info()

    # Backward compatibility alias
    def get_commit_info(
        self,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get baseline info (backward compatibility).

        Returns:
            Dict with 'sha' key for compatibility with GitLabClient interface
        """
        info = self.get_baseline_info()
        return {
            "sha": "local-file",
            "short_sha": "local",
            "message": "Local filesystem baselines",
            "author_name": "CD1 Agent",
            "authored_date": datetime.utcnow().isoformat(),
            **info,
        }


# Module-level convenience function
def get_baseline_loader(
    baselines_dir: str = "conf/baselines",
) -> BaselineLoader:
    """Get baseline loader instance."""
    return BaselineLoader(baselines_dir=baselines_dir)


if __name__ == "__main__":
    # Test mock provider
    os.environ["AWS_MOCK"] = "true"

    loader = BaselineLoader()
    print(f"Provider type: {loader.provider_type}")

    # Test baseline retrieval
    print("\n=== EKS Baseline ===")
    baseline = loader.get_resource_baseline("eks", "production-cluster")
    print(f"  Cluster: {baseline.content.get('cluster_name')}")
    print(f"  Version: {baseline.content.get('version')}")
    print(f"  Hash: {baseline.file_hash}")

    print("\n=== MSK Baseline ===")
    baseline = loader.get_resource_baseline("msk", "production-kafka")
    print(f"  Cluster: {baseline.content.get('cluster_name')}")
    print(f"  Kafka Version: {baseline.content.get('kafka_version')}")

    print("\n=== List All Baselines ===")
    baselines = loader.list_baselines()
    for b in baselines:
        print(f"  - {b}")

    print("\n=== Baseline Info ===")
    info = loader.get_baseline_info()
    print(f"  Source: {info}")
