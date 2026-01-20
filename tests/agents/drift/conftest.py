"""
Drift Agent Test Fixtures.

Provides LocalStack-specific fixtures for Drift Agent testing.
"""

import json
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, Generator

import pytest


# ============================================================================
# LocalStack Drift Agent Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def drift_localstack_endpoint() -> str:
    """Get LocalStack endpoint URL for drift agent tests."""
    return os.getenv("LOCALSTACK_ENDPOINT", "http://localhost:4566")


@pytest.fixture(scope="session")
def drift_tables_created(localstack_available: bool, drift_localstack_endpoint: str) -> bool:
    """Ensure drift-specific DynamoDB tables are created.

    Returns True if tables are created successfully or already exist.
    """
    if not localstack_available:
        return False

    try:
        import boto3

        dynamodb = boto3.client(
            "dynamodb",
            endpoint_url=drift_localstack_endpoint,
            region_name="ap-northeast-2",
        )

        # Check if tables exist
        tables = dynamodb.list_tables()["TableNames"]

        required_tables = [
            "drift-baseline-configs",
            "drift-current-configs",
            "drift-detection-results",
        ]
        missing_tables = [t for t in required_tables if t not in tables]

        if missing_tables:
            # Run the init script to create tables
            script_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "..",
                "infra",
                "localstack",
                "drift",
                "init",
                "03-create-drift-tables.sh",
            )
            if os.path.exists(script_path):
                env = os.environ.copy()
                env["LOCALSTACK_ENDPOINT"] = drift_localstack_endpoint
                subprocess.run(["bash", script_path], env=env, check=True)
            else:
                # Create tables directly
                for table_name in missing_tables:
                    try:
                        dynamodb.create_table(
                            TableName=table_name,
                            AttributeDefinitions=[
                                {"AttributeName": "pk", "AttributeType": "S"},
                                {"AttributeName": "sk", "AttributeType": "S"},
                            ],
                            KeySchema=[
                                {"AttributeName": "pk", "KeyType": "HASH"},
                                {"AttributeName": "sk", "KeyType": "RANGE"},
                            ],
                            BillingMode="PAY_PER_REQUEST",
                        )
                    except dynamodb.exceptions.ResourceInUseException:
                        pass

        return True

    except Exception as e:
        pytest.skip(f"Failed to create drift tables: {e}")
        return False


@pytest.fixture
def skip_without_drift_tables(drift_tables_created: bool):
    """Skip test if drift tables are not available."""
    if not drift_tables_created:
        pytest.skip("Drift DynamoDB tables are not available")


@pytest.fixture
def localstack_drift_handler(
    localstack_available: bool,
    drift_localstack_endpoint: str,
    drift_tables_created: bool,
) -> Generator[Any, None, None]:
    """Create DriftDetectionHandler configured for LocalStack.

    Automatically skips if LocalStack is not available.
    """
    if not localstack_available:
        pytest.skip("LocalStack is not available")

    if not drift_tables_created:
        pytest.skip("Drift tables are not created")

    # Set environment variables for LocalStack
    original_env = {}
    env_vars = {
        "DRIFT_PROVIDER": "localstack",
        "LOCALSTACK_ENDPOINT": drift_localstack_endpoint,
        "AWS_REGION": "ap-northeast-2",
        "DRIFT_BASELINE_TABLE": "drift-baseline-configs",
        "DRIFT_CURRENT_TABLE": "drift-current-configs",
        "AWS_PROVIDER": "localstack",
        "ENABLE_DRIFT_ANALYSIS": "false",  # Disable LLM for LocalStack tests
    }

    for key, value in env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        from src.agents.drift.handler import DriftDetectionHandler

        handler = DriftDetectionHandler()
        yield handler
    finally:
        # Restore original environment
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def localstack_config_fetcher(
    localstack_available: bool,
    drift_localstack_endpoint: str,
    drift_tables_created: bool,
) -> Generator[Any, None, None]:
    """Create ConfigFetcher configured for LocalStack."""
    if not localstack_available:
        pytest.skip("LocalStack is not available")

    if not drift_tables_created:
        pytest.skip("Drift tables are not created")

    from src.agents.drift.services.config_fetcher import ConfigFetcher, ConfigProvider

    fetcher = ConfigFetcher(
        provider=ConfigProvider.LOCALSTACK,
        endpoint_url=drift_localstack_endpoint,
    )
    yield fetcher


@pytest.fixture
def localstack_baseline_loader(
    localstack_available: bool,
    drift_localstack_endpoint: str,
    drift_tables_created: bool,
) -> Generator[Any, None, None]:
    """Create BaselineLoader configured for LocalStack."""
    if not localstack_available:
        pytest.skip("LocalStack is not available")

    if not drift_tables_created:
        pytest.skip("Drift tables are not created")

    from src.agents.drift.services.baseline_loader import (
        BaselineLoader,
        BaselineProvider,
    )

    loader = BaselineLoader(
        provider=BaselineProvider.LOCALSTACK,
        endpoint_url=drift_localstack_endpoint,
    )
    yield loader


@pytest.fixture
def inject_drift_baselines(
    localstack_available: bool,
    drift_localstack_endpoint: str,
    drift_tables_created: bool,
) -> Generator[bool, None, None]:
    """Inject baseline configurations for testing.

    Returns True if baselines were injected successfully.
    """
    if not localstack_available or not drift_tables_created:
        yield False
        return

    # Run the baseline injection script
    script_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "infra",
        "localstack",
        "drift",
        "init",
        "04-inject-drift-baselines.sh",
    )

    if os.path.exists(script_path):
        env = os.environ.copy()
        env["LOCALSTACK_ENDPOINT"] = drift_localstack_endpoint
        result = subprocess.run(["bash", script_path], env=env, capture_output=True)
        yield result.returncode == 0
    else:
        # Inject directly via boto3
        yield _inject_baselines_directly(drift_localstack_endpoint)


def _inject_baselines_directly(endpoint_url: str) -> bool:
    """Inject baseline and current configs directly via boto3."""
    import boto3

    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=endpoint_url,
        region_name="ap-northeast-2",
    )

    timestamp = datetime.utcnow().isoformat()

    # Resource configurations
    configs = {
        "eks": {
            "resource_id": "production-eks",
            "resource_arn": "arn:aws:eks:ap-northeast-2:123456789012:cluster/production-eks",
            "config": {
                "cluster_name": "production-eks",
                "version": "1.29",
                "endpoint_public_access": False,
                "endpoint_private_access": True,
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
            },
        },
        "s3": {
            "resource_id": "company-data-lake-prod",
            "resource_arn": "arn:aws:s3:::company-data-lake-prod",
            "config": {
                "bucket_name": "company-data-lake-prod",
                "public_access_block": {
                    "block_public_acls": True,
                    "ignore_public_acls": True,
                    "block_public_policy": True,
                    "restrict_public_buckets": True,
                },
            },
        },
        "msk": {
            "resource_id": "production-kafka",
            "resource_arn": "arn:aws:kafka:ap-northeast-2:123456789012:cluster/production-kafka/abc123",
            "config": {
                "cluster_name": "production-kafka",
                "kafka_version": "3.5.1",
                "broker_config": {
                    "instance_type": "kafka.m5.large",
                    "number_of_broker_nodes": 3,
                },
            },
        },
        "mwaa": {
            "resource_id": "bdp-airflow-prod",
            "resource_arn": "arn:aws:airflow:ap-northeast-2:123456789012:environment/bdp-airflow-prod",
            "config": {
                "environment_name": "bdp-airflow-prod",
                "min_workers": 2,
                "max_workers": 10,
            },
        },
    }

    try:
        for resource_type, data in configs.items():
            # Inject baseline
            dynamodb.put_item(
                TableName="drift-baseline-configs",
                Item={
                    "pk": {"S": f"RESOURCE#{resource_type}#{data['resource_id']}"},
                    "sk": {"S": f"VERSION#{timestamp}"},
                    "resource_type": {"S": resource_type},
                    "resource_id": {"S": data["resource_id"]},
                    "config": {"S": json.dumps(data["config"])},
                    "config_hash": {"S": "baseline123"},
                    "timestamp": {"S": timestamp},
                    "is_latest": {"BOOL": True},
                },
            )

            # Inject current config (same as baseline - no drift)
            dynamodb.put_item(
                TableName="drift-current-configs",
                Item={
                    "pk": {"S": f"RESOURCE#{resource_type}#{data['resource_id']}"},
                    "sk": {"S": f"FETCH#{timestamp}"},
                    "resource_type": {"S": resource_type},
                    "resource_id": {"S": data["resource_id"]},
                    "resource_arn": {"S": data["resource_arn"]},
                    "config": {"S": json.dumps(data["config"])},
                    "fetched_at": {"S": timestamp},
                    "is_latest": {"BOOL": True},
                },
            )

        return True
    except Exception:
        return False


@pytest.fixture
def inject_eks_drift(
    localstack_available: bool,
    drift_localstack_endpoint: str,
    drift_tables_created: bool,
    inject_drift_baselines: bool,
) -> Generator[Dict[str, Any], None, None]:
    """Inject EKS cluster drift scenario.

    Returns dict with drift details.
    """
    if not localstack_available or not drift_tables_created or not inject_drift_baselines:
        yield {}
        return

    import boto3

    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=drift_localstack_endpoint,
        region_name="ap-northeast-2",
    )

    timestamp = datetime.utcnow().isoformat()

    # Drifted config - instance type downgrade
    drifted_config = {
        "cluster_name": "production-eks",
        "version": "1.29",
        "endpoint_public_access": False,
        "endpoint_private_access": True,
        "node_groups": [
            {
                "name": "general-workload",
                "instance_types": ["m5.large"],  # DRIFT: was m6i.xlarge
                "scaling_config": {
                    "min_size": 3,
                    "max_size": 10,
                    "desired_size": 3,  # DRIFT: was 5
                },
            }
        ],
    }

    try:
        dynamodb.put_item(
            TableName="drift-current-configs",
            Item={
                "pk": {"S": "RESOURCE#eks#production-eks"},
                "sk": {"S": f"FETCH#{timestamp}"},
                "resource_type": {"S": "eks"},
                "resource_id": {"S": "production-eks"},
                "resource_arn": {"S": "arn:aws:eks:ap-northeast-2:123456789012:cluster/production-eks"},
                "config": {"S": json.dumps(drifted_config)},
                "fetched_at": {"S": timestamp},
                "is_latest": {"BOOL": True},
            },
        )
        yield {
            "resource_type": "EKS",
            "resource_id": "production-eks",
            "drift_fields": ["node_groups.instance_types", "node_groups.scaling_config.desired_size"],
            "expected_severity": "HIGH",
        }
    except Exception:
        yield {}


@pytest.fixture
def inject_s3_security_drift(
    localstack_available: bool,
    drift_localstack_endpoint: str,
    drift_tables_created: bool,
    inject_drift_baselines: bool,
) -> Generator[Dict[str, Any], None, None]:
    """Inject S3 bucket security drift scenario (CRITICAL).

    Returns dict with drift details.
    """
    if not localstack_available or not drift_tables_created or not inject_drift_baselines:
        yield {}
        return

    import boto3

    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=drift_localstack_endpoint,
        region_name="ap-northeast-2",
    )

    timestamp = datetime.utcnow().isoformat()

    # Drifted config - public access block disabled
    drifted_config = {
        "bucket_name": "company-data-lake-prod",
        "public_access_block": {
            "block_public_acls": False,  # CRITICAL DRIFT
            "ignore_public_acls": True,
            "block_public_policy": True,
            "restrict_public_buckets": True,
        },
    }

    try:
        dynamodb.put_item(
            TableName="drift-current-configs",
            Item={
                "pk": {"S": "RESOURCE#s3#company-data-lake-prod"},
                "sk": {"S": f"FETCH#{timestamp}"},
                "resource_type": {"S": "s3"},
                "resource_id": {"S": "company-data-lake-prod"},
                "resource_arn": {"S": "arn:aws:s3:::company-data-lake-prod"},
                "config": {"S": json.dumps(drifted_config)},
                "fetched_at": {"S": timestamp},
                "is_latest": {"BOOL": True},
            },
        )
        yield {
            "resource_type": "S3",
            "resource_id": "company-data-lake-prod",
            "drift_fields": ["public_access_block.block_public_acls"],
            "expected_severity": "CRITICAL",
        }
    except Exception:
        yield {}


@pytest.fixture
def inject_mwaa_drift(
    localstack_available: bool,
    drift_localstack_endpoint: str,
    drift_tables_created: bool,
    inject_drift_baselines: bool,
) -> Generator[Dict[str, Any], None, None]:
    """Inject MWAA environment drift scenario.

    Returns dict with drift details.
    """
    if not localstack_available or not drift_tables_created or not inject_drift_baselines:
        yield {}
        return

    import boto3

    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=drift_localstack_endpoint,
        region_name="ap-northeast-2",
    )

    timestamp = datetime.utcnow().isoformat()

    # Drifted config - worker capacity reduced
    drifted_config = {
        "environment_name": "bdp-airflow-prod",
        "min_workers": 1,  # DRIFT: was 2
        "max_workers": 5,  # DRIFT: was 10
    }

    try:
        dynamodb.put_item(
            TableName="drift-current-configs",
            Item={
                "pk": {"S": "RESOURCE#mwaa#bdp-airflow-prod"},
                "sk": {"S": f"FETCH#{timestamp}"},
                "resource_type": {"S": "mwaa"},
                "resource_id": {"S": "bdp-airflow-prod"},
                "resource_arn": {"S": "arn:aws:airflow:ap-northeast-2:123456789012:environment/bdp-airflow-prod"},
                "config": {"S": json.dumps(drifted_config)},
                "fetched_at": {"S": timestamp},
                "is_latest": {"BOOL": True},
            },
        )
        yield {
            "resource_type": "MWAA",
            "resource_id": "bdp-airflow-prod",
            "drift_fields": ["min_workers", "max_workers"],
            "expected_severity": "MEDIUM",
        }
    except Exception:
        yield {}


@pytest.fixture
def inject_multi_resource_drift(
    inject_eks_drift: Dict[str, Any],
    inject_s3_security_drift: Dict[str, Any],
    inject_mwaa_drift: Dict[str, Any],
) -> Generator[Dict[str, Any], None, None]:
    """Inject multi-resource drift scenario.

    Returns dict with overall drift details.
    """
    if not inject_eks_drift or not inject_s3_security_drift or not inject_mwaa_drift:
        yield {}
        return

    yield {
        "resources": [inject_eks_drift, inject_s3_security_drift, inject_mwaa_drift],
        "total_expected_drifts": 3,
        "expected_severities": {"CRITICAL": 1, "HIGH": 1, "MEDIUM": 1},
    }
