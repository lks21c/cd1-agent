"""
AWS Config Fetcher with Provider Abstraction.

Fetches current AWS resource configurations for drift detection.
Supports EKS, MSK, S3, EMR, and MWAA resources.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigProvider(str, Enum):
    """Supported config provider modes."""

    REAL = "real"
    MOCK = "mock"


class ResourceType(str, Enum):
    """Supported AWS resource types for drift detection."""

    EKS = "EKS"
    MSK = "MSK"
    S3 = "S3"
    EMR = "EMR"
    MWAA = "MWAA"


@dataclass
class ResourceConfig:
    """Represents current configuration of an AWS resource."""

    resource_type: ResourceType
    resource_id: str
    resource_arn: str
    config: Dict[str, Any]
    fetched_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "resource_arn": self.resource_arn,
            "config": self.config,
            "fetched_at": self.fetched_at,
        }


class BaseConfigProvider(ABC):
    """Abstract base class for config providers."""

    @abstractmethod
    def get_eks_config(self, cluster_name: str) -> ResourceConfig:
        """Get EKS cluster configuration."""
        pass

    @abstractmethod
    def get_msk_config(self, cluster_arn: str) -> ResourceConfig:
        """Get MSK cluster configuration."""
        pass

    @abstractmethod
    def get_s3_config(self, bucket_name: str) -> ResourceConfig:
        """Get S3 bucket configuration."""
        pass

    @abstractmethod
    def get_emr_config(self, cluster_id: str) -> ResourceConfig:
        """Get EMR cluster configuration."""
        pass

    @abstractmethod
    def get_mwaa_config(self, environment_name: str) -> ResourceConfig:
        """Get MWAA environment configuration."""
        pass


class RealConfigProvider(BaseConfigProvider):
    """Real AWS API config provider."""

    def __init__(self, region: str = "ap-northeast-2"):
        self.region = region
        self._clients: Dict[str, Any] = {}

    def _get_client(self, service: str):
        """Get or create boto3 client."""
        if service not in self._clients:
            import boto3
            self._clients[service] = boto3.client(service, region_name=self.region)
        return self._clients[service]

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat()

    def get_eks_config(self, cluster_name: str) -> ResourceConfig:
        """Get EKS cluster configuration."""
        eks = self._get_client("eks")

        # Get cluster info
        cluster_resp = eks.describe_cluster(name=cluster_name)
        cluster = cluster_resp["cluster"]

        # Get node groups
        ng_list = eks.list_nodegroups(clusterName=cluster_name)
        node_groups = []

        for ng_name in ng_list.get("nodegroups", []):
            ng_resp = eks.describe_nodegroup(
                clusterName=cluster_name,
                nodegroupName=ng_name,
            )
            ng = ng_resp["nodegroup"]
            node_groups.append({
                "name": ng["nodegroupName"],
                "instance_types": ng.get("instanceTypes", []),
                "scaling_config": ng.get("scalingConfig", {}),
                "disk_size": ng.get("diskSize"),
                "ami_type": ng.get("amiType"),
                "capacity_type": ng.get("capacityType"),
            })

        # Normalize to baseline format
        config = {
            "cluster_name": cluster["name"],
            "version": cluster.get("version"),
            "endpoint_public_access": cluster.get("resourcesVpcConfig", {}).get(
                "endpointPublicAccess", False
            ),
            "endpoint_private_access": cluster.get("resourcesVpcConfig", {}).get(
                "endpointPrivateAccess", True
            ),
            "logging": self._parse_eks_logging(cluster.get("logging", {})),
            "node_groups": node_groups,
            "tags": cluster.get("tags", {}),
        }

        return ResourceConfig(
            resource_type=ResourceType.EKS,
            resource_id=cluster_name,
            resource_arn=cluster["arn"],
            config=config,
            fetched_at=self._get_timestamp(),
        )

    def _parse_eks_logging(self, logging_config: Dict) -> Dict[str, bool]:
        """Parse EKS logging configuration."""
        result = {}
        for log_setup in logging_config.get("clusterLogging", []):
            if log_setup.get("enabled"):
                for log_type in log_setup.get("types", []):
                    result[log_type.lower()] = True
        return result

    def get_msk_config(self, cluster_arn: str) -> ResourceConfig:
        """Get MSK cluster configuration."""
        kafka = self._get_client("kafka")

        cluster_resp = kafka.describe_cluster_v2(ClusterArn=cluster_arn)
        cluster = cluster_resp["ClusterInfo"]
        provisioned = cluster.get("Provisioned", {})

        config = {
            "cluster_name": cluster.get("ClusterName"),
            "kafka_version": provisioned.get("CurrentBrokerSoftwareInfo", {}).get(
                "KafkaVersion"
            ),
            "broker_config": {
                "instance_type": provisioned.get("BrokerNodeGroupInfo", {}).get(
                    "InstanceType"
                ),
                "number_of_broker_nodes": provisioned.get("NumberOfBrokerNodes"),
                "storage_info": provisioned.get("BrokerNodeGroupInfo", {}).get(
                    "StorageInfo", {}
                ),
            },
            "encryption_info": {
                "encryption_at_rest": provisioned.get("EncryptionInfo", {})
                .get("EncryptionAtRest", {})
                .get("DataVolumeKMSKeyId") is not None,
                "encryption_in_transit": provisioned.get("EncryptionInfo", {})
                .get("EncryptionInTransit", {})
                .get("ClientBroker", "TLS"),
            },
            "enhanced_monitoring": provisioned.get("EnhancedMonitoring"),
            "tags": cluster.get("Tags", {}),
        }

        return ResourceConfig(
            resource_type=ResourceType.MSK,
            resource_id=cluster.get("ClusterName", ""),
            resource_arn=cluster_arn,
            config=config,
            fetched_at=self._get_timestamp(),
        )

    def get_s3_config(self, bucket_name: str) -> ResourceConfig:
        """Get S3 bucket configuration."""
        s3 = self._get_client("s3")

        config = {
            "bucket_name": bucket_name,
        }

        # Get versioning
        try:
            versioning = s3.get_bucket_versioning(Bucket=bucket_name)
            config["versioning"] = {
                "status": versioning.get("Status", "Disabled"),
            }
        except Exception as e:
            logger.warning(f"Failed to get versioning for {bucket_name}: {e}")
            config["versioning"] = {"status": "Unknown"}

        # Get encryption
        try:
            encryption = s3.get_bucket_encryption(Bucket=bucket_name)
            rules = encryption.get("ServerSideEncryptionConfiguration", {}).get(
                "Rules", []
            )
            if rules:
                rule = rules[0].get("ApplyServerSideEncryptionByDefault", {})
                config["encryption"] = {
                    "sse_algorithm": rule.get("SSEAlgorithm"),
                    "kms_master_key_id": rule.get("KMSMasterKeyID"),
                    "bucket_key_enabled": rules[0].get("BucketKeyEnabled", False),
                }
        except s3.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "ServerSideEncryptionConfigurationNotFoundError":
                config["encryption"] = {"sse_algorithm": "None"}
            else:
                logger.warning(f"Failed to get encryption for {bucket_name}: {e}")

        # Get public access block
        try:
            pab = s3.get_public_access_block(Bucket=bucket_name)
            config["public_access_block"] = pab.get(
                "PublicAccessBlockConfiguration", {}
            )
        except s3.exceptions.ClientError:
            config["public_access_block"] = {}

        # Get tags
        try:
            tagging = s3.get_bucket_tagging(Bucket=bucket_name)
            config["tags"] = {
                tag["Key"]: tag["Value"]
                for tag in tagging.get("TagSet", [])
            }
        except s3.exceptions.ClientError:
            config["tags"] = {}

        return ResourceConfig(
            resource_type=ResourceType.S3,
            resource_id=bucket_name,
            resource_arn=f"arn:aws:s3:::{bucket_name}",
            config=config,
            fetched_at=self._get_timestamp(),
        )

    def get_emr_config(self, cluster_id: str) -> ResourceConfig:
        """Get EMR cluster configuration."""
        emr = self._get_client("emr")

        cluster_resp = emr.describe_cluster(ClusterId=cluster_id)
        cluster = cluster_resp["Cluster"]

        # Get instance groups
        ig_resp = emr.list_instance_groups(ClusterId=cluster_id)
        instance_groups = {}

        for ig in ig_resp.get("InstanceGroups", []):
            ig_type = ig["InstanceGroupType"].lower()
            instance_groups[ig_type] = {
                "instance_type": ig.get("InstanceType"),
                "instance_count": ig.get("RequestedInstanceCount"),
            }

        config = {
            "cluster_name": cluster.get("Name"),
            "release_label": cluster.get("ReleaseLabel"),
            "applications": [app["Name"] for app in cluster.get("Applications", [])],
            "instance_groups": instance_groups,
            "tags": {
                tag["Key"]: tag["Value"]
                for tag in cluster.get("Tags", [])
            },
        }

        return ResourceConfig(
            resource_type=ResourceType.EMR,
            resource_id=cluster_id,
            resource_arn=cluster.get("ClusterArn", ""),
            config=config,
            fetched_at=self._get_timestamp(),
        )

    def get_mwaa_config(self, environment_name: str) -> ResourceConfig:
        """Get MWAA environment configuration."""
        mwaa = self._get_client("mwaa")

        env_resp = mwaa.get_environment(Name=environment_name)
        env = env_resp["Environment"]

        config = {
            "environment_name": env.get("Name"),
            "airflow_version": env.get("AirflowVersion"),
            "environment_class": env.get("EnvironmentClass"),
            "min_workers": env.get("MinWorkers"),
            "max_workers": env.get("MaxWorkers"),
            "schedulers": env.get("Schedulers"),
            "webserver_access_mode": env.get("WebserverAccessMode"),
            "tags": env.get("Tags", {}),
        }

        return ResourceConfig(
            resource_type=ResourceType.MWAA,
            resource_id=environment_name,
            resource_arn=env.get("Arn", ""),
            config=config,
            fetched_at=self._get_timestamp(),
        )


class MockConfigProvider(BaseConfigProvider):
    """Mock config provider for testing."""

    def __init__(self):
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._setup_default_configs()

    def _setup_default_configs(self):
        """Setup default mock configurations (with some drifts)."""
        from datetime import datetime

        now = datetime.utcnow().isoformat()

        # EKS config (with instance type drift)
        self._configs["EKS:production-eks"] = {
            "resource_type": ResourceType.EKS,
            "resource_id": "production-eks",
            "resource_arn": "arn:aws:eks:ap-northeast-2:123456789012:cluster/production-eks",
            "fetched_at": now,
            "config": {
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
                        "instance_types": ["m5.large"],  # DRIFT: was m6i.xlarge
                        "scaling_config": {
                            "min_size": 3,
                            "max_size": 10,
                            "desired_size": 3,  # DRIFT: was 5
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
            },
        }

        # MSK config (no drift)
        self._configs["MSK:production-kafka"] = {
            "resource_type": ResourceType.MSK,
            "resource_id": "production-kafka",
            "resource_arn": "arn:aws:kafka:ap-northeast-2:123456789012:cluster/production-kafka/abc123",
            "fetched_at": now,
            "config": {
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
            },
        }

        # S3 config (with security drift - public access enabled)
        self._configs["S3:company-data-lake-prod"] = {
            "resource_type": ResourceType.S3,
            "resource_id": "company-data-lake-prod",
            "resource_arn": "arn:aws:s3:::company-data-lake-prod",
            "fetched_at": now,
            "config": {
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
                    "block_public_acls": False,  # DRIFT: was True (CRITICAL)
                    "ignore_public_acls": True,
                    "block_public_policy": True,
                    "restrict_public_buckets": True,
                },
                "tags": {
                    "Environment": "production",
                    "DataClassification": "confidential",
                },
            },
        }

        # EMR config (no drift)
        self._configs["EMR:j-XXXXX"] = {
            "resource_type": ResourceType.EMR,
            "resource_id": "j-XXXXX",
            "resource_arn": "arn:aws:elasticmapreduce:ap-northeast-2:123456789012:cluster/j-XXXXX",
            "fetched_at": now,
            "config": {
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
            },
        }

        # MWAA config (with scaling drift)
        self._configs["MWAA:bdp-airflow-prod"] = {
            "resource_type": ResourceType.MWAA,
            "resource_id": "bdp-airflow-prod",
            "resource_arn": "arn:aws:airflow:ap-northeast-2:123456789012:environment/bdp-airflow-prod",
            "fetched_at": now,
            "config": {
                "environment_name": "bdp-airflow-prod",
                "airflow_version": "2.8.1",
                "environment_class": "mw1.medium",
                "min_workers": 1,  # DRIFT: was 2
                "max_workers": 10,
                "schedulers": 2,
                "webserver_access_mode": "PRIVATE_ONLY",
                "tags": {
                    "Environment": "production",
                },
            },
        }

    def set_current_config(
        self,
        resource_type: str,
        resource_id: str,
        config: Dict[str, Any],
    ) -> None:
        """Set mock current configuration for testing."""
        from datetime import datetime

        key = f"{resource_type}:{resource_id}"
        self._configs[key] = {
            "resource_type": ResourceType(resource_type),
            "resource_id": resource_id,
            "resource_arn": f"arn:aws:{resource_type.lower()}:ap-northeast-2:123456789012:{resource_id}",
            "config": config,
            "fetched_at": datetime.utcnow().isoformat(),
        }

    def _get_config(self, resource_type: str, resource_id: str) -> ResourceConfig:
        """Get mock configuration."""
        key = f"{resource_type}:{resource_id}"

        if key not in self._configs:
            raise ValueError(f"Resource not found: {key}")

        data = self._configs[key]
        return ResourceConfig(
            resource_type=data["resource_type"],
            resource_id=data["resource_id"],
            resource_arn=data["resource_arn"],
            config=data["config"],
            fetched_at=data["fetched_at"],
        )

    def get_eks_config(self, cluster_name: str) -> ResourceConfig:
        """Get EKS cluster configuration (mock)."""
        logger.debug(f"Mock ConfigFetcher get_eks_config: {cluster_name}")
        return self._get_config("EKS", cluster_name)

    def get_msk_config(self, cluster_arn: str) -> ResourceConfig:
        """Get MSK cluster configuration (mock)."""
        logger.debug(f"Mock ConfigFetcher get_msk_config: {cluster_arn}")
        # Extract cluster name from ARN for key lookup
        cluster_name = cluster_arn.split("/")[-1].split(":")[0] if "/" in cluster_arn else cluster_arn
        return self._get_config("MSK", cluster_name)

    def get_s3_config(self, bucket_name: str) -> ResourceConfig:
        """Get S3 bucket configuration (mock)."""
        logger.debug(f"Mock ConfigFetcher get_s3_config: {bucket_name}")
        return self._get_config("S3", bucket_name)

    def get_emr_config(self, cluster_id: str) -> ResourceConfig:
        """Get EMR cluster configuration (mock)."""
        logger.debug(f"Mock ConfigFetcher get_emr_config: {cluster_id}")
        return self._get_config("EMR", cluster_id)

    def get_mwaa_config(self, environment_name: str) -> ResourceConfig:
        """Get MWAA environment configuration (mock)."""
        logger.debug(f"Mock ConfigFetcher get_mwaa_config: {environment_name}")
        return self._get_config("MWAA", environment_name)


class ConfigFetcher:
    """Config fetcher with automatic provider selection."""

    def __init__(
        self,
        region: Optional[str] = None,
        provider: Optional[ConfigProvider] = None,
    ):
        """
        Initialize config fetcher.

        Args:
            region: AWS region for API calls
            provider: Force specific provider (auto-detect if None)
        """
        self.region = region or os.environ.get("AWS_REGION", "ap-northeast-2")

        # Auto-detect provider
        if provider is None:
            if os.environ.get("AWS_MOCK", "").lower() == "true":
                provider = ConfigProvider.MOCK
            else:
                provider = ConfigProvider.REAL

        self.provider_type = provider

        if provider == ConfigProvider.MOCK:
            self._provider = MockConfigProvider()
            logger.info("Using Mock Config Provider")
        else:
            self._provider = RealConfigProvider(region=self.region)
            logger.info(f"Using Real Config Provider: {self.region}")

    @property
    def provider(self) -> BaseConfigProvider:
        """Get the underlying provider."""
        return self._provider

    def get_config(
        self,
        resource_type: ResourceType,
        resource_id: str,
    ) -> ResourceConfig:
        """
        Get current configuration for a resource.

        Args:
            resource_type: Type of AWS resource
            resource_id: Resource identifier (name, ARN, or ID)

        Returns:
            ResourceConfig with current configuration
        """
        if resource_type == ResourceType.EKS:
            return self._provider.get_eks_config(resource_id)
        elif resource_type == ResourceType.MSK:
            return self._provider.get_msk_config(resource_id)
        elif resource_type == ResourceType.S3:
            return self._provider.get_s3_config(resource_id)
        elif resource_type == ResourceType.EMR:
            return self._provider.get_emr_config(resource_id)
        elif resource_type == ResourceType.MWAA:
            return self._provider.get_mwaa_config(resource_id)
        else:
            raise ValueError(f"Unsupported resource type: {resource_type}")

    def get_multiple_configs(
        self,
        resources: List[Dict[str, str]],
    ) -> List[ResourceConfig]:
        """
        Get configurations for multiple resources.

        Args:
            resources: List of {"type": "EKS", "id": "cluster-name"} dicts

        Returns:
            List of ResourceConfig objects
        """
        configs = []
        for resource in resources:
            try:
                resource_type = ResourceType(resource["type"].upper())
                config = self.get_config(resource_type, resource["id"])
                configs.append(config)
            except Exception as e:
                logger.error(
                    f"Failed to fetch config for {resource['type']}:{resource['id']}: {e}"
                )
        return configs


# Module-level convenience function
def get_config_fetcher(region: Optional[str] = None) -> ConfigFetcher:
    """Get config fetcher instance."""
    return ConfigFetcher(region=region)


if __name__ == "__main__":
    # Test mock provider
    os.environ["AWS_MOCK"] = "true"

    fetcher = ConfigFetcher()
    print(f"Provider type: {fetcher.provider_type}")

    # Test EKS config
    print("\n=== EKS Config ===")
    config = fetcher.get_config(ResourceType.EKS, "production-eks")
    print(f"  Cluster: {config.config.get('cluster_name')}")
    print(f"  Version: {config.config.get('version')}")
    print(f"  Node Groups: {len(config.config.get('node_groups', []))}")

    # Test S3 config
    print("\n=== S3 Config ===")
    config = fetcher.get_config(ResourceType.S3, "company-data-lake-prod")
    print(f"  Bucket: {config.config.get('bucket_name')}")
    print(f"  Public Access Block: {config.config.get('public_access_block')}")

    # Test MWAA config
    print("\n=== MWAA Config ===")
    config = fetcher.get_config(ResourceType.MWAA, "bdp-airflow-prod")
    print(f"  Environment: {config.config.get('environment_name')}")
    print(f"  Min Workers: {config.config.get('min_workers')}")
