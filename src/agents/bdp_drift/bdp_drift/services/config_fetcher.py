"""
Config Fetcher - AWS configuration retrieval.

8개 대상 리소스의 현재 설정 조회.
- Primary: Glue, Athena, EMR, SageMaker
- Secondary: S3, MWAA, MSK, Lambda
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.agents.bdp_drift.bdp_drift.services.models import ResourceType

logger = logging.getLogger(__name__)


@dataclass
class ResourceConfig:
    """리소스 설정."""

    resource_type: str
    resource_id: str
    resource_arn: Optional[str]
    config: Dict[str, Any]
    account_id: Optional[str] = None
    region: Optional[str] = None


class BaseConfigFetcher(ABC):
    """설정 조회기 추상 베이스 클래스."""

    @abstractmethod
    def fetch_config(self, resource_id: str) -> Optional[ResourceConfig]:
        """단일 리소스 설정 조회."""
        pass

    @abstractmethod
    def list_resources(self) -> List[str]:
        """리소스 목록 조회."""
        pass

    @abstractmethod
    def fetch_all_configs(self) -> List[ResourceConfig]:
        """모든 리소스 설정 조회."""
        pass


class GlueFetcher(BaseConfigFetcher):
    """Glue Catalogue 설정 조회기."""

    def __init__(self, client=None, use_mock: bool = False):
        self.use_mock = use_mock
        self._client = client
        self.resource_type = ResourceType.GLUE.value

    @property
    def client(self):
        if self._client is None and not self.use_mock:
            import boto3
            self._client = boto3.client("glue")
        return self._client

    def fetch_config(self, resource_id: str) -> Optional[ResourceConfig]:
        """Glue 데이터베이스/테이블 설정 조회."""
        if self.use_mock:
            return self._mock_config(resource_id)

        try:
            # resource_id format: database_name or database_name/table_name
            parts = resource_id.split("/")

            if len(parts) == 1:
                # Database
                response = self.client.get_database(Name=parts[0])
                db = response["Database"]
                return ResourceConfig(
                    resource_type=self.resource_type,
                    resource_id=resource_id,
                    resource_arn=db.get("CatalogId"),
                    config={
                        "name": db["Name"],
                        "description": db.get("Description"),
                        "location_uri": db.get("LocationUri"),
                        "parameters": db.get("Parameters", {}),
                    },
                )
            else:
                # Table
                response = self.client.get_table(
                    DatabaseName=parts[0],
                    Name=parts[1],
                )
                table = response["Table"]
                return ResourceConfig(
                    resource_type=self.resource_type,
                    resource_id=resource_id,
                    resource_arn=table.get("CatalogId"),
                    config={
                        "name": table["Name"],
                        "database": table["DatabaseName"],
                        "columns": [
                            {"name": c["Name"], "type": c["Type"]}
                            for c in table.get("StorageDescriptor", {}).get("Columns", [])
                        ],
                        "partition_keys": [
                            {"name": p["Name"], "type": p["Type"]}
                            for p in table.get("PartitionKeys", [])
                        ],
                        "table_type": table.get("TableType"),
                        "parameters": table.get("Parameters", {}),
                        "storage_descriptor": {
                            "location": table.get("StorageDescriptor", {}).get("Location"),
                            "input_format": table.get("StorageDescriptor", {}).get("InputFormat"),
                            "output_format": table.get("StorageDescriptor", {}).get("OutputFormat"),
                            "serde_info": table.get("StorageDescriptor", {}).get("SerdeInfo", {}),
                        },
                    },
                )
        except Exception as e:
            logger.error(f"Failed to fetch Glue config for {resource_id}: {e}")
            return None

    def list_resources(self) -> List[str]:
        """Glue 데이터베이스 목록 조회."""
        if self.use_mock:
            return ["default", "analytics", "raw_data"]

        resources = []
        try:
            paginator = self.client.get_paginator("get_databases")
            for page in paginator.paginate():
                for db in page["DatabaseList"]:
                    resources.append(db["Name"])
        except Exception as e:
            logger.error(f"Failed to list Glue databases: {e}")

        return resources

    def fetch_all_configs(self) -> List[ResourceConfig]:
        """모든 Glue 설정 조회."""
        configs = []
        for resource_id in self.list_resources():
            config = self.fetch_config(resource_id)
            if config:
                configs.append(config)
        return configs

    def _mock_config(self, resource_id: str) -> ResourceConfig:
        """Mock 설정 반환."""
        return ResourceConfig(
            resource_type=self.resource_type,
            resource_id=resource_id,
            resource_arn=f"arn:aws:glue:ap-northeast-2:123456789012:database/{resource_id}",
            config={
                "name": resource_id,
                "description": f"Mock Glue database {resource_id}",
                "location_uri": f"s3://mock-bucket/{resource_id}/",
                "parameters": {},
            },
        )


class AthenaFetcher(BaseConfigFetcher):
    """Athena 워크그룹 설정 조회기."""

    def __init__(self, client=None, use_mock: bool = False):
        self.use_mock = use_mock
        self._client = client
        self.resource_type = ResourceType.ATHENA.value

    @property
    def client(self):
        if self._client is None and not self.use_mock:
            import boto3
            self._client = boto3.client("athena")
        return self._client

    def fetch_config(self, resource_id: str) -> Optional[ResourceConfig]:
        """Athena 워크그룹 설정 조회."""
        if self.use_mock:
            return self._mock_config(resource_id)

        try:
            response = self.client.get_work_group(WorkGroup=resource_id)
            wg = response["WorkGroup"]
            config = wg.get("Configuration", {})

            return ResourceConfig(
                resource_type=self.resource_type,
                resource_id=resource_id,
                resource_arn=f"arn:aws:athena:{os.getenv('AWS_REGION', 'ap-northeast-2')}::workgroup/{resource_id}",
                config={
                    "name": wg["Name"],
                    "state": wg["State"],
                    "result_configuration": config.get("ResultConfiguration", {}),
                    "enforce_work_group_configuration": config.get("EnforceWorkGroupConfiguration"),
                    "publish_cloudwatch_metrics_enabled": config.get("PublishCloudWatchMetricsEnabled"),
                    "bytes_scanned_cutoff_per_query": config.get("BytesScannedCutoffPerQuery"),
                    "requester_pays_enabled": config.get("RequesterPaysEnabled"),
                    "engine_version": config.get("EngineVersion", {}),
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch Athena config for {resource_id}: {e}")
            return None

    def list_resources(self) -> List[str]:
        """Athena 워크그룹 목록 조회."""
        if self.use_mock:
            return ["primary", "analytics", "adhoc"]

        resources = []
        try:
            paginator = self.client.get_paginator("list_work_groups")
            for page in paginator.paginate():
                for wg in page["WorkGroups"]:
                    resources.append(wg["Name"])
        except Exception as e:
            logger.error(f"Failed to list Athena workgroups: {e}")

        return resources

    def fetch_all_configs(self) -> List[ResourceConfig]:
        """모든 Athena 설정 조회."""
        configs = []
        for resource_id in self.list_resources():
            config = self.fetch_config(resource_id)
            if config:
                configs.append(config)
        return configs

    def _mock_config(self, resource_id: str) -> ResourceConfig:
        """Mock 설정 반환."""
        return ResourceConfig(
            resource_type=self.resource_type,
            resource_id=resource_id,
            resource_arn=f"arn:aws:athena:ap-northeast-2:123456789012:workgroup/{resource_id}",
            config={
                "name": resource_id,
                "state": "ENABLED",
                "result_configuration": {
                    "OutputLocation": f"s3://mock-bucket/athena-results/{resource_id}/",
                    "EncryptionConfiguration": {"EncryptionOption": "SSE_S3"},
                },
                "enforce_work_group_configuration": True,
                "engine_version": {"SelectedEngineVersion": "Athena engine version 3"},
            },
        )


class S3Fetcher(BaseConfigFetcher):
    """S3 버킷 설정 조회기."""

    def __init__(self, client=None, use_mock: bool = False):
        self.use_mock = use_mock
        self._client = client
        self.resource_type = ResourceType.S3.value

    @property
    def client(self):
        if self._client is None and not self.use_mock:
            import boto3
            self._client = boto3.client("s3")
        return self._client

    def fetch_config(self, resource_id: str) -> Optional[ResourceConfig]:
        """S3 버킷 설정 조회."""
        if self.use_mock:
            return self._mock_config(resource_id)

        try:
            config = {"name": resource_id}

            # 버저닝
            try:
                versioning = self.client.get_bucket_versioning(Bucket=resource_id)
                config["versioning"] = versioning.get("Status", "Disabled")
            except Exception:
                config["versioning"] = "Unknown"

            # 암호화
            try:
                encryption = self.client.get_bucket_encryption(Bucket=resource_id)
                rules = encryption.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
                if rules:
                    config["encryption"] = rules[0].get("ApplyServerSideEncryptionByDefault", {})
            except Exception:
                config["encryption"] = None

            # Public Access Block
            try:
                pab = self.client.get_public_access_block(Bucket=resource_id)
                config["public_access_block"] = pab.get("PublicAccessBlockConfiguration", {})
            except Exception:
                config["public_access_block"] = None

            return ResourceConfig(
                resource_type=self.resource_type,
                resource_id=resource_id,
                resource_arn=f"arn:aws:s3:::{resource_id}",
                config=config,
            )
        except Exception as e:
            logger.error(f"Failed to fetch S3 config for {resource_id}: {e}")
            return None

    def list_resources(self) -> List[str]:
        """S3 버킷 목록 조회."""
        if self.use_mock:
            return ["data-lake-raw", "data-lake-processed", "analytics-output"]

        resources = []
        try:
            response = self.client.list_buckets()
            for bucket in response.get("Buckets", []):
                resources.append(bucket["Name"])
        except Exception as e:
            logger.error(f"Failed to list S3 buckets: {e}")

        return resources

    def fetch_all_configs(self) -> List[ResourceConfig]:
        """모든 S3 설정 조회."""
        configs = []
        for resource_id in self.list_resources():
            config = self.fetch_config(resource_id)
            if config:
                configs.append(config)
        return configs

    def _mock_config(self, resource_id: str) -> ResourceConfig:
        """Mock 설정 반환."""
        return ResourceConfig(
            resource_type=self.resource_type,
            resource_id=resource_id,
            resource_arn=f"arn:aws:s3:::{resource_id}",
            config={
                "name": resource_id,
                "versioning": "Enabled",
                "encryption": {
                    "SSEAlgorithm": "aws:kms",
                    "KMSMasterKeyID": "alias/aws/s3",
                },
                "public_access_block": {
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            },
        )


class LambdaFetcher(BaseConfigFetcher):
    """Lambda 함수 설정 조회기."""

    def __init__(self, client=None, use_mock: bool = False):
        self.use_mock = use_mock
        self._client = client
        self.resource_type = ResourceType.LAMBDA.value

    @property
    def client(self):
        if self._client is None and not self.use_mock:
            import boto3
            self._client = boto3.client("lambda")
        return self._client

    def fetch_config(self, resource_id: str) -> Optional[ResourceConfig]:
        """Lambda 함수 설정 조회."""
        if self.use_mock:
            return self._mock_config(resource_id)

        try:
            response = self.client.get_function(FunctionName=resource_id)
            config = response["Configuration"]

            return ResourceConfig(
                resource_type=self.resource_type,
                resource_id=resource_id,
                resource_arn=config["FunctionArn"],
                config={
                    "function_name": config["FunctionName"],
                    "runtime": config.get("Runtime"),
                    "handler": config.get("Handler"),
                    "memory_size": config.get("MemorySize"),
                    "timeout": config.get("Timeout"),
                    "role": config.get("Role"),
                    "environment": config.get("Environment", {}).get("Variables", {}),
                    "layers": [
                        layer["Arn"] for layer in config.get("Layers", [])
                    ],
                    "vpc_config": config.get("VpcConfig", {}),
                    "architectures": config.get("Architectures", ["x86_64"]),
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch Lambda config for {resource_id}: {e}")
            return None

    def list_resources(self) -> List[str]:
        """Lambda 함수 목록 조회."""
        if self.use_mock:
            return ["data-processor", "event-handler", "api-handler"]

        resources = []
        try:
            paginator = self.client.get_paginator("list_functions")
            for page in paginator.paginate():
                for func in page["Functions"]:
                    resources.append(func["FunctionName"])
        except Exception as e:
            logger.error(f"Failed to list Lambda functions: {e}")

        return resources

    def fetch_all_configs(self) -> List[ResourceConfig]:
        """모든 Lambda 설정 조회."""
        configs = []
        for resource_id in self.list_resources():
            config = self.fetch_config(resource_id)
            if config:
                configs.append(config)
        return configs

    def _mock_config(self, resource_id: str) -> ResourceConfig:
        """Mock 설정 반환."""
        return ResourceConfig(
            resource_type=self.resource_type,
            resource_id=resource_id,
            resource_arn=f"arn:aws:lambda:ap-northeast-2:123456789012:function:{resource_id}",
            config={
                "function_name": resource_id,
                "runtime": "python3.11",
                "handler": "handler.main",
                "memory_size": 256,
                "timeout": 30,
                "role": "arn:aws:iam::123456789012:role/lambda-execution-role",
                "environment": {},
                "layers": [],
                "architectures": ["arm64"],
            },
        )


class ConfigFetcher:
    """
    통합 설정 조회기.

    8개 리소스 타입에 대한 통합 인터페이스 제공.

    Usage:
        fetcher = ConfigFetcher(use_mock=True)
        config = fetcher.fetch_config(ResourceType.GLUE, "my-database")
        all_configs = fetcher.fetch_all_configs(ResourceType.S3)
    """

    def __init__(self, use_mock: bool = False):
        """ConfigFetcher 초기화.

        Args:
            use_mock: Mock 모드 사용 여부
        """
        self.use_mock = use_mock or os.getenv("DRIFT_PROVIDER", "").lower() == "mock"

        # 리소스별 Fetcher 초기화
        self._fetchers: Dict[str, BaseConfigFetcher] = {
            ResourceType.GLUE.value: GlueFetcher(use_mock=self.use_mock),
            ResourceType.ATHENA.value: AthenaFetcher(use_mock=self.use_mock),
            ResourceType.S3.value: S3Fetcher(use_mock=self.use_mock),
            ResourceType.LAMBDA.value: LambdaFetcher(use_mock=self.use_mock),
            # EMR, SageMaker, MWAA, MSK는 추후 구현
        }

        logger.info(f"ConfigFetcher initialized (mock={self.use_mock})")

    def get_fetcher(self, resource_type: str) -> Optional[BaseConfigFetcher]:
        """리소스 타입별 Fetcher 반환."""
        return self._fetchers.get(resource_type)

    def fetch_config(
        self,
        resource_type: str,
        resource_id: str,
    ) -> Optional[ResourceConfig]:
        """단일 리소스 설정 조회.

        Args:
            resource_type: 리소스 타입
            resource_id: 리소스 ID

        Returns:
            ResourceConfig 또는 None
        """
        fetcher = self.get_fetcher(resource_type)
        if fetcher is None:
            logger.warning(f"No fetcher for resource type: {resource_type}")
            return None

        return fetcher.fetch_config(resource_id)

    def list_resources(self, resource_type: str) -> List[str]:
        """리소스 목록 조회.

        Args:
            resource_type: 리소스 타입

        Returns:
            리소스 ID 목록
        """
        fetcher = self.get_fetcher(resource_type)
        if fetcher is None:
            return []

        return fetcher.list_resources()

    def fetch_all_configs(
        self,
        resource_type: Optional[str] = None,
    ) -> List[ResourceConfig]:
        """모든 리소스 설정 조회.

        Args:
            resource_type: 리소스 타입 (None이면 모든 타입)

        Returns:
            ResourceConfig 목록
        """
        configs = []

        if resource_type:
            fetcher = self.get_fetcher(resource_type)
            if fetcher:
                configs.extend(fetcher.fetch_all_configs())
        else:
            for fetcher in self._fetchers.values():
                configs.extend(fetcher.fetch_all_configs())

        return configs

    @property
    def supported_resource_types(self) -> List[str]:
        """지원 리소스 타입 목록."""
        return list(self._fetchers.keys())
