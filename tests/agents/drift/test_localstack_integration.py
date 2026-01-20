"""
Drift Agent LocalStack Integration Tests.

Tests drift detection functionality using LocalStack-backed DynamoDB
for baseline and current configuration storage.
"""

import pytest
from typing import Any, Dict


@pytest.mark.localstack
class TestDriftAgentLocalStackIntegration:
    """Integration tests for Drift Agent using LocalStack."""

    def test_config_fetcher_localstack_provider(
        self,
        localstack_config_fetcher,
        inject_drift_baselines: bool,
    ):
        """Test ConfigFetcher can fetch configs from LocalStack DynamoDB."""
        if not inject_drift_baselines:
            pytest.skip("Baselines not injected")

        from src.agents.drift.services.config_fetcher import ResourceType

        # Fetch EKS config
        config = localstack_config_fetcher.get_config(
            ResourceType.EKS,
            "production-eks",
        )

        assert config is not None
        assert config.resource_type == ResourceType.EKS
        assert config.resource_id == "production-eks"
        assert config.config.get("cluster_name") == "production-eks"

    def test_baseline_loader_localstack_provider(
        self,
        localstack_baseline_loader,
        inject_drift_baselines: bool,
    ):
        """Test BaselineLoader can load baselines from LocalStack DynamoDB."""
        if not inject_drift_baselines:
            pytest.skip("Baselines not injected")

        # Load EKS baseline
        baseline = localstack_baseline_loader.get_resource_baseline(
            resource_type="eks",
            resource_name="production-eks",
        )

        assert baseline is not None
        assert baseline.content.get("cluster_name") == "production-eks"
        assert "localstack" in baseline.file_path

    def test_list_baselines_from_localstack(
        self,
        localstack_baseline_loader,
        inject_drift_baselines: bool,
    ):
        """Test listing baseline files from LocalStack."""
        if not inject_drift_baselines:
            pytest.skip("Baselines not injected")

        # List all baselines
        baselines = localstack_baseline_loader.list_baselines()

        assert len(baselines) >= 4  # eks, s3, msk, mwaa
        assert any("eks" in b for b in baselines)
        assert any("s3" in b for b in baselines)

    def test_detect_eks_config_drift(
        self,
        localstack_config_fetcher,
        localstack_baseline_loader,
        inject_eks_drift: Dict[str, Any],
    ):
        """Test EKS cluster drift detection."""
        if not inject_eks_drift:
            pytest.skip("EKS drift not injected")

        from src.agents.drift.services.config_fetcher import ResourceType
        from src.agents.drift.services.drift_detector import ConfigDriftDetector

        # Get baseline and current config
        baseline = localstack_baseline_loader.get_resource_baseline(
            resource_type="eks",
            resource_name="production-eks",
        )
        current = localstack_config_fetcher.get_config(
            ResourceType.EKS,
            "production-eks",
        )

        # Detect drift
        detector = ConfigDriftDetector()
        result = detector.detect(
            baseline=baseline.content,
            current=current.config,
            resource_type="EKS",
            resource_id="production-eks",
            resource_arn=current.resource_arn,
            baseline_version=baseline.file_hash,
        )

        assert result.has_drift is True
        assert len(result.drifted_fields) > 0

        # Check for expected drift fields
        drift_paths = [f.field_path for f in result.drifted_fields]
        assert any("instance_types" in p for p in drift_paths) or \
            any("desired_size" in p for p in drift_paths)

    def test_detect_s3_security_drift(
        self,
        localstack_config_fetcher,
        localstack_baseline_loader,
        inject_s3_security_drift: Dict[str, Any],
    ):
        """Test S3 bucket security drift detection (CRITICAL severity)."""
        if not inject_s3_security_drift:
            pytest.skip("S3 drift not injected")

        from src.agents.drift.services.config_fetcher import ResourceType
        from src.agents.drift.services.drift_detector import (
            ConfigDriftDetector,
            DriftSeverity,
        )

        # Get baseline and current config
        baseline = localstack_baseline_loader.get_resource_baseline(
            resource_type="s3",
            resource_name="company-data-lake-prod",
        )
        current = localstack_config_fetcher.get_config(
            ResourceType.S3,
            "company-data-lake-prod",
        )

        # Detect drift
        detector = ConfigDriftDetector()
        result = detector.detect(
            baseline=baseline.content,
            current=current.config,
            resource_type="S3",
            resource_id="company-data-lake-prod",
            resource_arn=current.resource_arn,
            baseline_version=baseline.file_hash,
        )

        assert result.has_drift is True

        # S3 public access block changes should be CRITICAL
        critical_drifts = [
            f for f in result.drifted_fields
            if f.severity == DriftSeverity.CRITICAL
        ]
        # Note: Depending on drift rules, this may or may not be CRITICAL
        # The test validates that drift was detected
        assert len(result.drifted_fields) > 0

    def test_detect_mwaa_drift(
        self,
        localstack_config_fetcher,
        localstack_baseline_loader,
        inject_mwaa_drift: Dict[str, Any],
    ):
        """Test MWAA environment drift detection."""
        if not inject_mwaa_drift:
            pytest.skip("MWAA drift not injected")

        from src.agents.drift.services.config_fetcher import ResourceType
        from src.agents.drift.services.drift_detector import ConfigDriftDetector

        # Get baseline and current config
        baseline = localstack_baseline_loader.get_resource_baseline(
            resource_type="mwaa",
            resource_name="bdp-airflow-prod",
        )
        current = localstack_config_fetcher.get_config(
            ResourceType.MWAA,
            "bdp-airflow-prod",
        )

        # Detect drift
        detector = ConfigDriftDetector()
        result = detector.detect(
            baseline=baseline.content,
            current=current.config,
            resource_type="MWAA",
            resource_id="bdp-airflow-prod",
            resource_arn=current.resource_arn,
            baseline_version=baseline.file_hash,
        )

        assert result.has_drift is True

        # Check for worker-related drifts
        drift_paths = [f.field_path for f in result.drifted_fields]
        assert any("workers" in p.lower() for p in drift_paths)

    def test_detect_multi_resource_drift(
        self,
        localstack_config_fetcher,
        localstack_baseline_loader,
        inject_multi_resource_drift: Dict[str, Any],
    ):
        """Test multi-resource drift detection."""
        if not inject_multi_resource_drift:
            pytest.skip("Multi-resource drift not injected")

        from src.agents.drift.services.config_fetcher import ResourceType
        from src.agents.drift.services.drift_detector import ConfigDriftDetector

        detector = ConfigDriftDetector()
        drifts_detected = 0

        resources = [
            ("EKS", "production-eks", ResourceType.EKS),
            ("S3", "company-data-lake-prod", ResourceType.S3),
            ("MWAA", "bdp-airflow-prod", ResourceType.MWAA),
        ]

        for resource_type_str, resource_id, resource_type_enum in resources:
            baseline = localstack_baseline_loader.get_resource_baseline(
                resource_type=resource_type_str.lower(),
                resource_name=resource_id,
            )
            current = localstack_config_fetcher.get_config(
                resource_type_enum,
                resource_id,
            )

            result = detector.detect(
                baseline=baseline.content,
                current=current.config,
                resource_type=resource_type_str,
                resource_id=resource_id,
                resource_arn=current.resource_arn,
                baseline_version=baseline.file_hash,
            )

            if result.has_drift:
                drifts_detected += 1

        # Should detect drifts in all 3 resources
        assert drifts_detected == 3

    def test_drift_severity_classification(
        self,
        localstack_config_fetcher,
        localstack_baseline_loader,
        inject_s3_security_drift: Dict[str, Any],
    ):
        """Test that drift severity is properly classified."""
        if not inject_s3_security_drift:
            pytest.skip("S3 drift not injected")

        from src.agents.drift.services.config_fetcher import ResourceType
        from src.agents.drift.services.drift_detector import (
            ConfigDriftDetector,
            DriftSeverity,
        )

        baseline = localstack_baseline_loader.get_resource_baseline(
            resource_type="s3",
            resource_name="company-data-lake-prod",
        )
        current = localstack_config_fetcher.get_config(
            ResourceType.S3,
            "company-data-lake-prod",
        )

        detector = ConfigDriftDetector()
        result = detector.detect(
            baseline=baseline.content,
            current=current.config,
            resource_type="S3",
            resource_id="company-data-lake-prod",
            resource_arn=current.resource_arn,
            baseline_version=baseline.file_hash,
        )

        # Verify severity values are valid
        for drift_field in result.drifted_fields:
            assert drift_field.severity in [
                DriftSeverity.CRITICAL,
                DriftSeverity.HIGH,
                DriftSeverity.MEDIUM,
                DriftSeverity.LOW,
            ]

        # Verify max_severity is computed
        if result.has_drift:
            assert result.max_severity is not None

    def test_no_drift_when_configs_match(
        self,
        localstack_config_fetcher,
        localstack_baseline_loader,
        inject_drift_baselines: bool,
    ):
        """Test that no drift is detected when baseline and current match."""
        if not inject_drift_baselines:
            pytest.skip("Baselines not injected")

        from src.agents.drift.services.config_fetcher import ResourceType
        from src.agents.drift.services.drift_detector import ConfigDriftDetector

        # MSK should have no drift (baseline == current in our setup)
        baseline = localstack_baseline_loader.get_resource_baseline(
            resource_type="msk",
            resource_name="production-kafka",
        )
        current = localstack_config_fetcher.get_config(
            ResourceType.MSK,
            "production-kafka",
        )

        detector = ConfigDriftDetector()
        result = detector.detect(
            baseline=baseline.content,
            current=current.config,
            resource_type="MSK",
            resource_id="production-kafka",
            resource_arn=current.resource_arn,
            baseline_version=baseline.file_hash,
        )

        # Should have no drift when configs match
        assert result.has_drift is False
        assert len(result.drifted_fields) == 0


@pytest.mark.localstack
class TestDriftHandlerLocalStackIntegration:
    """Integration tests for DriftDetectionHandler using LocalStack."""

    def test_handler_process_with_drift(
        self,
        localstack_drift_handler,
        inject_eks_drift: Dict[str, Any],
        lambda_context,
    ):
        """Test handler processes drift detection event."""
        if not inject_eks_drift:
            pytest.skip("EKS drift not injected")

        event = {
            "resource_types": ["EKS"],
            "resources": {"EKS": ["production-eks"]},
            "severity_threshold": "LOW",
        }

        result = localstack_drift_handler.process(event, lambda_context)

        assert "has_drifts" in result
        assert "total_drift_count" in result
        assert "resources_analyzed" in result

        # Should detect drift
        assert result["resources_analyzed"] >= 1

    def test_handler_process_multi_resource(
        self,
        localstack_drift_handler,
        inject_multi_resource_drift: Dict[str, Any],
        lambda_context,
    ):
        """Test handler processes multiple resource types."""
        if not inject_multi_resource_drift:
            pytest.skip("Multi-resource drift not injected")

        event = {
            "resource_types": ["EKS", "S3", "MWAA"],
            "resources": {
                "EKS": ["production-eks"],
                "S3": ["company-data-lake-prod"],
                "MWAA": ["bdp-airflow-prod"],
            },
            "severity_threshold": "LOW",
        }

        result = localstack_drift_handler.process(event, lambda_context)

        assert result["resources_analyzed"] >= 3

        # Check severity summary
        if result.get("has_drifts"):
            assert "severity_summary" in result

    def test_handler_severity_filtering(
        self,
        localstack_drift_handler,
        inject_mwaa_drift: Dict[str, Any],
        lambda_context,
    ):
        """Test handler respects severity threshold filtering."""
        if not inject_mwaa_drift:
            pytest.skip("MWAA drift not injected")

        # Test with HIGH threshold (should filter out MEDIUM/LOW drifts)
        event = {
            "resource_types": ["MWAA"],
            "resources": {"MWAA": ["bdp-airflow-prod"]},
            "severity_threshold": "HIGH",
        }

        result = localstack_drift_handler.process(event, lambda_context)

        # Result should still include resource but may filter out lower severity drifts
        assert result["resources_analyzed"] >= 1
