"""
Cost Agent LocalStack Integration Tests.

Tests cost anomaly detection using LocalStack-simulated cost data.

Run with:
    pytest tests/agents/cost/test_localstack_integration.py -m localstack -v

Requires:
    - LocalStack running: make -C infra/localstack up
    - Cost tables created: make -C infra/localstack cost-init
    - Baseline data injected: make -C infra/localstack cost-baseline
"""

import pytest
from datetime import datetime, timedelta
from typing import Any, Dict


@pytest.mark.localstack
class TestCostAgentLocalStackIntegration:
    """Integration tests for Cost Agent with LocalStack."""

    def test_localstack_provider_initialization(
        self,
        localstack_available: bool,
        cost_localstack_endpoint: str,
        cost_tables_created: bool,
    ):
        """Test LocalStackCostExplorerProvider initializes correctly."""
        if not localstack_available:
            pytest.skip("LocalStack not available")

        from src.agents.cost.services.cost_explorer_client import (
            LocalStackCostExplorerProvider,
        )

        provider = LocalStackCostExplorerProvider(
            endpoint_url=cost_localstack_endpoint,
        )

        assert provider.endpoint_url == cost_localstack_endpoint
        assert provider.table_name == "cost-service-history"

    def test_cost_client_with_localstack_provider(
        self,
        localstack_cost_client,
    ):
        """Test CostExplorerClient works with LocalStack provider."""
        assert localstack_cost_client.provider_type == "localstack"
        assert localstack_cost_client.use_mock is False

    def test_get_cost_and_usage_with_baseline_data(
        self,
        localstack_cost_client,
        inject_cost_baseline: bool,
    ):
        """Test retrieving cost data from LocalStack DynamoDB."""
        if not inject_cost_baseline:
            pytest.skip("Baseline data not injected")

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)

        result = localstack_cost_client.get_cost_and_usage(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            group_by=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        assert "results" in result
        assert len(result["results"]) > 0

        # Verify data structure
        for period in result["results"]:
            assert "start" in period
            assert "end" in period
            assert "total" in period
            assert "groups" in period

    def test_get_cost_by_service(
        self,
        localstack_cost_client,
        inject_cost_baseline: bool,
    ):
        """Test get_cost_by_service returns service-grouped costs."""
        if not inject_cost_baseline:
            pytest.skip("Baseline data not injected")

        service_costs = localstack_cost_client.get_cost_by_service(days=7)

        assert isinstance(service_costs, dict)
        assert len(service_costs) > 0

        # Should have AWS Lambda in the results
        assert any("Lambda" in service for service in service_costs.keys())

    def test_get_historical_costs_for_detector(
        self,
        localstack_cost_client,
        inject_cost_baseline: bool,
    ):
        """Test historical costs formatted for CostAnomalyDetector."""
        if not inject_cost_baseline:
            pytest.skip("Baseline data not injected")

        historical_data = localstack_cost_client.get_historical_costs_for_detector(days=7)

        assert isinstance(historical_data, dict)

        for service, data in historical_data.items():
            assert "historical_costs" in data
            assert "timestamps" in data
            assert "current_cost" in data
            assert isinstance(data["historical_costs"], list)
            assert len(data["historical_costs"]) > 0

    def test_detect_ec2_cost_spike(
        self,
        localstack_cost_handler,
        inject_ec2_cost_spike: Dict[str, Any],
    ):
        """Test detection of EC2 cost spike scenario."""
        if not inject_ec2_cost_spike:
            pytest.skip("EC2 spike not injected")

        result = localstack_cost_handler.process(
            {"days": 14, "min_cost_threshold": 1.0},
            None,
        )

        assert result["anomalies_detected"] is True
        assert result["total_anomalies"] > 0

        # Find EC2 anomaly
        ec2_anomalies = [
            a for a in result["anomalies"]
            if "EC2" in a["service_name"]
        ]

        assert len(ec2_anomalies) > 0, "EC2 anomaly should be detected"

        ec2_anomaly = ec2_anomalies[0]
        assert ec2_anomaly["severity"] in ["high", "critical"]
        assert ec2_anomaly["change_ratio"] >= 2.0

    def test_detect_lambda_cost_spike(
        self,
        localstack_cost_handler,
        inject_lambda_cost_spike: Dict[str, Any],
    ):
        """Test detection of Lambda cost spike scenario (5x increase)."""
        if not inject_lambda_cost_spike:
            pytest.skip("Lambda spike not injected")

        result = localstack_cost_handler.process(
            {"days": 14, "min_cost_threshold": 1.0},
            None,
        )

        assert result["anomalies_detected"] is True

        # Find Lambda anomaly
        lambda_anomalies = [
            a for a in result["anomalies"]
            if "Lambda" in a["service_name"]
        ]

        assert len(lambda_anomalies) > 0, "Lambda anomaly should be detected"

        lambda_anomaly = lambda_anomalies[0]
        # 5x increase should be critical
        assert lambda_anomaly["severity"] in ["high", "critical"]
        assert lambda_anomaly["change_ratio"] >= 3.0

    def test_batch_detection_multiple_services(
        self,
        localstack_cost_handler,
        inject_multi_service_spike: Dict[str, Any],
    ):
        """Test batch detection when multiple services spike simultaneously."""
        if not inject_multi_service_spike:
            pytest.skip("Multi-service spike not injected")

        result = localstack_cost_handler.process(
            {"days": 14, "min_cost_threshold": 1.0},
            None,
        )

        assert result["anomalies_detected"] is True

        # Should detect multiple anomalies
        expected_services = inject_multi_service_spike.get("services", [])
        detected_services = [a["service_name"] for a in result["anomalies"]]

        # At least 2 of the 3 services should be detected
        matched = sum(
            1 for svc in expected_services
            if any(svc in detected for detected in detected_services)
        )
        assert matched >= 2, f"Expected at least 2 services detected, got {matched}"

    def test_severity_breakdown_calculation(
        self,
        localstack_cost_handler,
        inject_lambda_cost_spike: Dict[str, Any],
    ):
        """Test severity breakdown is calculated correctly."""
        if not inject_lambda_cost_spike:
            pytest.skip("Spike not injected")

        result = localstack_cost_handler.process(
            {"days": 14},
            None,
        )

        assert "severity_breakdown" in result

        breakdown = result["severity_breakdown"]
        assert "critical" in breakdown
        assert "high" in breakdown
        assert "medium" in breakdown
        assert "low" in breakdown

        # Total should match
        total = sum(breakdown.values())
        assert total == result["total_anomalies"]

    def test_detection_summary_generation(
        self,
        localstack_cost_handler,
        inject_ec2_cost_spike: Dict[str, Any],
    ):
        """Test summary generation for detected anomalies."""
        if not inject_ec2_cost_spike:
            pytest.skip("Spike not injected")

        result = localstack_cost_handler.process(
            {"days": 14},
            None,
        )

        assert "summary" in result
        summary = result["summary"]

        # Summary should mention anomalies
        if result["anomalies_detected"]:
            assert "anomal" in summary.lower()
            assert str(result["total_anomalies"]) in summary or "detected" in summary.lower()

    def test_forecast_detection_type(
        self,
        localstack_cost_handler,
        inject_cost_baseline: bool,
    ):
        """Test forecast detection type returns forecast data."""
        if not inject_cost_baseline:
            pytest.skip("Baseline data not injected")

        result = localstack_cost_handler.process(
            {"detection_type": "forecast", "days": 7},
            None,
        )

        assert result["detection_type"] == "forecast"
        assert "total_forecast" in result
        assert "daily_forecasts" in result
        assert isinstance(result["total_forecast"], (int, float))

    def test_min_cost_threshold_filtering(
        self,
        localstack_cost_handler,
        inject_cost_baseline: bool,
    ):
        """Test that min_cost_threshold filters out low-cost services."""
        if not inject_cost_baseline:
            pytest.skip("Baseline data not injected")

        # Run with high threshold - should analyze fewer services
        high_threshold_result = localstack_cost_handler.process(
            {"days": 14, "min_cost_threshold": 100.0},
            None,
        )

        # Run with low threshold - should analyze more services
        low_threshold_result = localstack_cost_handler.process(
            {"days": 14, "min_cost_threshold": 1.0},
            None,
        )

        # Higher threshold should analyze fewer services
        assert high_threshold_result["services_analyzed"] <= low_threshold_result["services_analyzed"]


@pytest.mark.localstack
class TestLocalStackCostExplorerProvider:
    """Unit tests for LocalStackCostExplorerProvider."""

    def test_provider_handles_empty_table(
        self,
        localstack_available: bool,
        cost_localstack_endpoint: str,
        cost_tables_created: bool,
    ):
        """Test provider handles empty DynamoDB table gracefully."""
        if not localstack_available or not cost_tables_created:
            pytest.skip("LocalStack or tables not available")

        from src.agents.cost.services.cost_explorer_client import (
            LocalStackCostExplorerProvider,
        )

        provider = LocalStackCostExplorerProvider(
            endpoint_url=cost_localstack_endpoint,
        )

        # Query for a date range with no data
        result = provider.get_cost_and_usage(
            start_date="2000-01-01",
            end_date="2000-01-07",
        )

        assert result["results"] == []
        assert result["next_token"] is None

    def test_provider_get_anomalies_empty(
        self,
        localstack_available: bool,
        cost_localstack_endpoint: str,
        cost_tables_created: bool,
    ):
        """Test get_anomalies returns empty list when no anomalies exist."""
        if not localstack_available or not cost_tables_created:
            pytest.skip("LocalStack or tables not available")

        from src.agents.cost.services.cost_explorer_client import (
            LocalStackCostExplorerProvider,
        )

        provider = LocalStackCostExplorerProvider(
            endpoint_url=cost_localstack_endpoint,
        )

        anomalies = provider.get_anomalies(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert anomalies == []

    def test_provider_forecast_fallback(
        self,
        localstack_available: bool,
        cost_localstack_endpoint: str,
        cost_tables_created: bool,
        inject_cost_baseline: bool,
    ):
        """Test forecast generates from historical data when no forecast table data."""
        if not localstack_available or not cost_tables_created:
            pytest.skip("LocalStack or tables not available")

        if not inject_cost_baseline:
            pytest.skip("Baseline data not injected")

        from src.agents.cost.services.cost_explorer_client import (
            LocalStackCostExplorerProvider,
        )

        provider = LocalStackCostExplorerProvider(
            endpoint_url=cost_localstack_endpoint,
        )

        end_date = datetime.utcnow() + timedelta(days=7)
        start_date = datetime.utcnow()

        forecast = provider.get_cost_forecast(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )

        assert "total_forecast" in forecast
        assert "forecast_by_time" in forecast
        assert forecast["total_forecast"] > 0
        assert len(forecast["forecast_by_time"]) > 0


@pytest.mark.localstack
class TestCostExplorerClientProviderSelection:
    """Tests for provider selection in CostExplorerClient."""

    def test_localstack_provider_selection_by_type(self):
        """Test provider_type='localstack' creates LocalStackCostExplorerProvider."""
        import os
        from src.agents.cost.services.cost_explorer_client import (
            CostExplorerClient,
            LocalStackCostExplorerProvider,
        )

        # Clear any existing env var
        original = os.environ.pop("COST_PROVIDER", None)

        try:
            client = CostExplorerClient(
                provider_type="localstack",
                endpoint_url="http://test:4566",
            )

            assert client.provider_type == "localstack"
            assert isinstance(client._provider, LocalStackCostExplorerProvider)
            assert client.use_mock is False
        finally:
            if original:
                os.environ["COST_PROVIDER"] = original

    def test_localstack_provider_selection_by_env(self):
        """Test COST_PROVIDER=localstack env var creates LocalStackCostExplorerProvider."""
        import os
        from src.agents.cost.services.cost_explorer_client import (
            CostExplorerClient,
            LocalStackCostExplorerProvider,
        )

        original = os.environ.get("COST_PROVIDER")
        os.environ["COST_PROVIDER"] = "localstack"

        try:
            client = CostExplorerClient(endpoint_url="http://test:4566")

            assert client.provider_type == "localstack"
            assert isinstance(client._provider, LocalStackCostExplorerProvider)
        finally:
            if original:
                os.environ["COST_PROVIDER"] = original
            else:
                os.environ.pop("COST_PROVIDER", None)

    def test_mock_provider_is_default(self):
        """Test mock provider is used by default."""
        import os
        from src.agents.cost.services.cost_explorer_client import (
            CostExplorerClient,
            MockCostExplorerProvider,
        )

        # Clear any existing env var
        original = os.environ.pop("COST_PROVIDER", None)

        try:
            client = CostExplorerClient()

            assert client.provider_type == "mock"
            assert isinstance(client._provider, MockCostExplorerProvider)
            assert client.use_mock is True
        finally:
            if original:
                os.environ["COST_PROVIDER"] = original
