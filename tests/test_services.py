"""
Unit Tests for BDP Agent Services.

Tests for LLM and AWS client implementations.
"""

import pytest
from datetime import datetime, timedelta

from src.services.llm_client import LLMClient, LLMProvider, MockLLMProvider
from src.services.aws_client import AWSClient, AWSProvider, MockAWSProvider
from src.services.cost_anomaly_detector import CostAnomalyDetector, DetectionMethod
from src.services.cost_explorer_client import CostExplorerClient
from src.models.analysis_result import AnalysisResult


class TestLLMClient:
    """Test suite for LLM client."""

    def test_mock_provider_creation(self):
        """Test MockLLMProvider creation."""
        provider = MockLLMProvider()

        assert provider.call_history == []

    def test_mock_provider_generate(self):
        """Test MockLLMProvider generate method."""
        provider = MockLLMProvider()
        response = provider.generate("Test prompt")

        assert isinstance(response, str)
        assert len(provider.call_history) == 1
        assert provider.call_history[0]["method"] == "generate"

    def test_mock_provider_with_custom_response(self):
        """Test MockLLMProvider with custom responses."""
        custom_response = "Custom mock response"
        provider = MockLLMProvider(responses={"generate": custom_response})

        response = provider.generate("Test prompt")

        assert response == custom_response

    def test_llm_client_mock_provider(self):
        """Test LLMClient with mock provider."""
        client = LLMClient(provider=LLMProvider.MOCK)

        response = client.generate("Analyze this log")

        assert isinstance(response, str)
        assert "analysis" in response.lower() or "root_cause" in response.lower()

    def test_llm_client_generate_structured(self):
        """Test LLMClient structured generation."""
        client = LLMClient(provider=LLMProvider.MOCK)

        result = client.generate_structured(
            prompt="Analyze this anomaly",
            response_model=AnalysisResult,
        )

        assert isinstance(result, AnalysisResult)
        assert 0.0 <= result.confidence_score <= 1.0

    def test_llm_client_call_history(self):
        """Test LLMClient call history tracking."""
        client = LLMClient(provider=LLMProvider.MOCK)

        client.generate("First call")
        client.generate("Second call")

        assert len(client.call_history) == 2

    def test_llm_client_temperature_parameter(self):
        """Test LLMClient temperature parameter."""
        client = LLMClient(provider=LLMProvider.MOCK)

        client.generate("Test", temperature=0.5)

        assert client.call_history[0]["temperature"] == 0.5

    def test_llm_client_system_prompt(self):
        """Test LLMClient with system prompt."""
        client = LLMClient(provider=LLMProvider.MOCK)

        client.generate("Test", system_prompt="You are an expert analyst.")

        assert client.call_history[0]["system_prompt"] == "You are an expert analyst."


class TestAWSClient:
    """Test suite for AWS client."""

    def test_mock_provider_creation(self):
        """Test MockAWSProvider creation."""
        provider = MockAWSProvider()

        assert provider.call_history == []

    def test_aws_client_mock_provider(self):
        """Test AWSClient with mock provider."""
        client = AWSClient(provider=AWSProvider.MOCK)

        assert client.provider_type == AWSProvider.MOCK

    def test_get_cloudwatch_metrics(self):
        """Test CloudWatch metrics retrieval."""
        client = AWSClient(provider=AWSProvider.MOCK)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)

        result = client.get_cloudwatch_metrics(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions=[{"FunctionName": "test-function"}],
            start_time=start_time,
            end_time=end_time,
        )

        assert "namespace" in result
        assert "datapoints" in result
        assert len(client.call_history) == 1

    def test_query_cloudwatch_logs(self):
        """Test CloudWatch Logs query."""
        client = AWSClient(provider=AWSProvider.MOCK)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)

        result = client.query_cloudwatch_logs(
            log_group="/aws/lambda/test",
            query="fields @message",
            start_time=start_time,
            end_time=end_time,
        )

        assert isinstance(result, list)

    def test_put_dynamodb_item(self):
        """Test DynamoDB put item."""
        client = AWSClient(provider=AWSProvider.MOCK)

        result = client.put_dynamodb_item(
            table_name="test-table",
            item={"pk": "test-key", "data": "test-value"},
        )

        assert result["status"] == "success"

    def test_get_dynamodb_item(self):
        """Test DynamoDB get item."""
        client = AWSClient(provider=AWSProvider.MOCK)

        # First put
        client.put_dynamodb_item(
            table_name="test-table",
            item={"pk": "test-key", "data": "test-value"},
        )

        # Then get
        result = client.get_dynamodb_item(
            table_name="test-table",
            key={"pk": "test-key"},
        )

        assert result is not None
        assert result["pk"] == "test-key"

    def test_put_eventbridge_event(self):
        """Test EventBridge event publishing."""
        client = AWSClient(provider=AWSProvider.MOCK)

        result = client.put_eventbridge_event(
            event_bus="test-bus",
            source="bdp.test",
            detail_type="TestEvent",
            detail={"key": "value"},
        )

        assert result["failed_count"] == 0

    def test_retrieve_knowledge_base(self):
        """Test Knowledge Base retrieval."""
        client = AWSClient(provider=AWSProvider.MOCK)

        result = client.retrieve_knowledge_base(
            knowledge_base_id="test-kb",
            query="troubleshooting database",
        )

        assert isinstance(result, list)
        assert len(result) > 0

    def test_mock_data_injection(self):
        """Test mock data injection."""
        mock_data = {
            "cloudwatch_metrics": {
                "namespace": "Custom",
                "metric": "CustomMetric",
                "datapoints": [{"Sum": 100}],
            }
        }

        client = AWSClient(provider=AWSProvider.MOCK, mock_data=mock_data)

        result = client.get_cloudwatch_metrics(
            namespace="Custom",
            metric_name="CustomMetric",
            dimensions=[],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
        )

        assert result["namespace"] == "Custom"

    def test_get_events(self):
        """Test retrieving stored events."""
        client = AWSClient(provider=AWSProvider.MOCK)

        client.put_eventbridge_event(
            event_bus="test-bus",
            source="bdp.test",
            detail_type="TestEvent",
            detail={"key": "value"},
        )

        events = client.get_events()

        assert len(events) == 1
        assert events[0]["source"] == "bdp.test"


class TestCostAnomalyDetector:
    """Test suite for cost anomaly detector."""

    def test_detector_creation(self):
        """Test CostAnomalyDetector creation."""
        detector = CostAnomalyDetector(sensitivity=0.7)

        assert detector.sensitivity == 0.7

    def test_analyze_service_normal(self):
        """Test analyzing service with normal costs."""
        detector = CostAnomalyDetector()

        result = detector.analyze_service(
            service_name="Lambda",
            current_cost=105.0,
            historical_costs=[100.0, 102.0, 98.0, 105.0, 101.0, 103.0, 100.0],
        )

        assert result.is_anomaly is False
        assert result.service_name == "Lambda"

    def test_analyze_service_anomaly(self):
        """Test analyzing service with anomalous costs."""
        detector = CostAnomalyDetector()

        result = detector.analyze_service(
            service_name="Lambda",
            current_cost=250.0,  # 2.5x increase
            historical_costs=[100.0, 102.0, 98.0, 105.0, 101.0, 103.0, 100.0],
        )

        assert result.is_anomaly is True
        assert result.confidence_score > 0.5

    def test_analyze_service_insufficient_data(self):
        """Test analyzing service with insufficient data."""
        detector = CostAnomalyDetector(min_data_points=7)

        result = detector.analyze_service(
            service_name="Lambda",
            current_cost=150.0,
            historical_costs=[100.0, 102.0],  # Only 2 points
        )

        assert result.is_anomaly is False
        assert "insufficient" in result.analysis.lower()

    def test_analyze_batch(self, sample_cost_data):
        """Test batch analysis."""
        detector = CostAnomalyDetector()

        results = detector.analyze_batch(sample_cost_data)

        assert len(results) == 2
        # Results should be sorted by confidence

    def test_detection_methods(self):
        """Test individual detection methods."""
        detector = CostAnomalyDetector()

        # Ratio method
        ratio_result = detector._detect_ratio_anomaly(
            current=200.0,
            historical=[100.0, 100.0, 100.0, 100.0, 100.0],
        )

        assert ratio_result.method == DetectionMethod.RATIO
        assert ratio_result.is_anomaly is True

    def test_severity_calculation(self):
        """Test severity calculation."""
        detector = CostAnomalyDetector()

        # High confidence, high change ratio
        assert detector._calculate_severity(0.9, 1.0) == "critical"

        # Medium confidence
        assert detector._calculate_severity(0.6, 0.3) == "medium"


class TestCostExplorerClient:
    """Test suite for Cost Explorer client."""

    def test_client_creation(self):
        """Test CostExplorerClient creation."""
        client = CostExplorerClient(use_mock=True)

        assert client.use_mock is True

    def test_get_cost_and_usage(self):
        """Test cost and usage retrieval."""
        client = CostExplorerClient(use_mock=True)

        result = client.get_cost_and_usage(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert "results" in result
        assert len(result["results"]) > 0

    def test_get_cost_by_service(self):
        """Test cost by service retrieval."""
        client = CostExplorerClient(use_mock=True)

        result = client.get_cost_by_service(days=7)

        assert isinstance(result, dict)
        # Should have service entries

    def test_get_historical_costs_for_detector(self):
        """Test historical costs formatted for detector."""
        client = CostExplorerClient(use_mock=True)

        result = client.get_historical_costs_for_detector(days=14)

        assert isinstance(result, dict)
        for service, data in result.items():
            assert "current_cost" in data
            assert "historical_costs" in data
            assert "timestamps" in data

    def test_get_cost_forecast(self):
        """Test cost forecast."""
        client = CostExplorerClient(use_mock=True)

        result = client.get_cost_forecast(
            start_date="2024-02-01",
            end_date="2024-02-15",
        )

        assert "total_forecast" in result
        assert result["total_forecast"] > 0
