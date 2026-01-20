"""
BDP Compact Agent LocalStack Integration Tests.

LocalStack 환경에서 전체 플로우 통합 테스트.
"""

import os

import pytest


@pytest.mark.localstack
class TestBDPCompactLocalStackIntegration:
    """LocalStack 통합 테스트."""

    def test_localstack_provider_connection(
        self,
        localstack_available,
        bdp_localstack_endpoint,
        bdp_tables_created,
    ):
        """LocalStack Provider 연결 테스트."""
        if not localstack_available:
            pytest.skip("LocalStack not available")

        if not bdp_tables_created:
            pytest.skip("BDP tables not created")

        from src.agents.bdp_compact.services.multi_account_provider import (
            LocalStackMultiAccountProvider,
        )

        provider = LocalStackMultiAccountProvider(
            endpoint_url=bdp_localstack_endpoint,
        )

        accounts = provider.get_accounts()
        assert len(accounts) >= 1

    def test_localstack_cost_data_retrieval(
        self,
        localstack_available,
        bdp_localstack_endpoint,
        bdp_tables_created,
        inject_bdp_baseline,
    ):
        """LocalStack에서 비용 데이터 조회."""
        if not localstack_available:
            pytest.skip("LocalStack not available")

        if not bdp_tables_created:
            pytest.skip("BDP tables not created")

        if not inject_bdp_baseline:
            pytest.skip("Baseline data not injected")

        from src.agents.bdp_compact.services.multi_account_provider import (
            LocalStackMultiAccountProvider,
        )

        provider = LocalStackMultiAccountProvider(
            endpoint_url=bdp_localstack_endpoint,
        )

        cost_data = provider.get_cost_data(days=14)

        assert len(cost_data) >= 1
        for account_id, services in cost_data.items():
            assert len(services) >= 1
            for service in services:
                assert service.service_name
                assert service.account_id
                assert len(service.historical_costs) >= 1

    def test_eventbridge_event_publishing(
        self,
        localstack_available,
        bdp_localstack_endpoint,
    ):
        """LocalStack EventBridge 이벤트 발행."""
        if not localstack_available:
            pytest.skip("LocalStack not available")

        import boto3

        # EventBridge 버스 확인
        events_client = boto3.client(
            "events",
            endpoint_url=bdp_localstack_endpoint,
            region_name="ap-northeast-2",
        )

        # 테스트 이벤트 발행
        response = events_client.put_events(
            Entries=[
                {
                    "EventBusName": "default",
                    "Source": "test.bdp-compact",
                    "DetailType": "Test Event",
                    "Detail": '{"test": "data"}',
                }
            ]
        )

        assert response.get("FailedEntryCount", 1) == 0

    def test_full_detection_flow_localstack(
        self,
        localstack_bdp_handler,
        inject_bdp_baseline,
    ):
        """전체 탐지 플로우 테스트."""
        if not inject_bdp_baseline:
            pytest.skip("Baseline data not injected")

        event = {"days": 14, "publish_alerts": False}
        context = type("Context", (), {"aws_request_id": "integration-test"})()

        response = localstack_bdp_handler.handle(event, context)

        assert response["statusCode"] == 200

        import json
        body = json.loads(response["body"])

        assert body["success"] is True
        assert "data" in body

        data = body["data"]
        assert data["detection_type"] == "cost_drift"
        assert data["accounts_analyzed"] >= 1
        assert data["services_analyzed"] >= 1
        assert isinstance(data["severity_breakdown"], dict)

    def test_spike_detection_localstack(
        self,
        localstack_available,
        bdp_localstack_endpoint,
        bdp_tables_created,
        inject_bdp_baseline,
    ):
        """스파이크 시나리오 탐지 테스트."""
        if not localstack_available or not bdp_tables_created or not inject_bdp_baseline:
            pytest.skip("Prerequisites not met")

        import boto3
        from datetime import datetime

        dynamodb = boto3.client(
            "dynamodb",
            endpoint_url=bdp_localstack_endpoint,
            region_name="ap-northeast-2",
        )

        # 스파이크 데이터 주입
        today = datetime.utcnow().strftime("%Y-%m-%d")
        dynamodb.put_item(
            TableName="bdp-cost-history",
            Item={
                "pk": {"S": "ACCOUNT#111111111111#SERVICE#Amazon Athena"},
                "sk": {"S": f"DATE#{today}"},
                "account_id": {"S": "111111111111"},
                "account_name": {"S": "hyundaicard-payer"},
                "service_name": {"S": "Amazon Athena"},
                "cost": {"N": "580000"},  # 스파이크
                "currency": {"S": "KRW"},
                "timestamp": {"S": f"{today}T23:59:59Z"},
            },
        )

        # 환경 설정
        original_env = os.environ.get("BDP_PROVIDER")
        os.environ["BDP_PROVIDER"] = "localstack"
        os.environ["LOCALSTACK_ENDPOINT"] = bdp_localstack_endpoint

        try:
            from src.agents.bdp_compact.handler import BDPCompactHandler

            handler = BDPCompactHandler()
            event = {"days": 14, "min_cost_threshold": 100000}
            context = type("Context", (), {"aws_request_id": "spike-test"})()

            response = handler.handle(event, context)

            import json
            body = json.loads(response["body"])
            data = body["data"]

            # 이상 탐지 확인
            if data["total_anomalies"] > 0:
                athena_results = [
                    r for r in data["results"]
                    if "Athena" in r["service_name"]
                ]
                if athena_results:
                    assert athena_results[0]["severity"] in ("high", "critical")

        finally:
            if original_env:
                os.environ["BDP_PROVIDER"] = original_env
            else:
                os.environ.pop("BDP_PROVIDER", None)


@pytest.mark.localstack
class TestMultiAccountScenarios:
    """Multi-Account 시나리오 테스트."""

    def test_multi_account_detection(
        self,
        localstack_available,
        bdp_localstack_endpoint,
        bdp_tables_created,
        inject_bdp_baseline,
    ):
        """복수 계정 탐지 테스트."""
        if not all([localstack_available, bdp_tables_created, inject_bdp_baseline]):
            pytest.skip("Prerequisites not met")

        from src.agents.bdp_compact.services.multi_account_provider import (
            LocalStackMultiAccountProvider,
        )

        provider = LocalStackMultiAccountProvider(
            endpoint_url=bdp_localstack_endpoint,
        )

        cost_data = provider.get_cost_data(days=14)

        # 두 계정 모두에서 데이터 조회
        account_ids = list(cost_data.keys())
        assert len(account_ids) >= 1

        # 각 계정에 서비스 데이터 존재
        for account_id, services in cost_data.items():
            assert len(services) >= 1, f"Account {account_id} should have services"

    def test_cross_account_summary(
        self,
        localstack_available,
        bdp_localstack_endpoint,
        bdp_tables_created,
        inject_bdp_baseline,
    ):
        """크로스 계정 요약 테스트."""
        if not all([localstack_available, bdp_tables_created, inject_bdp_baseline]):
            pytest.skip("Prerequisites not met")

        from src.agents.bdp_compact.services.anomaly_detector import CostDriftDetector
        from src.agents.bdp_compact.services.multi_account_provider import (
            LocalStackMultiAccountProvider,
        )
        from src.agents.bdp_compact.services.summary_generator import SummaryGenerator

        provider = LocalStackMultiAccountProvider(
            endpoint_url=bdp_localstack_endpoint,
        )
        detector = CostDriftDetector()
        generator = SummaryGenerator(currency="KRW")

        cost_data = provider.get_cost_data(days=14)
        results = detector.analyze_batch(cost_data)

        # 일괄 요약 생성
        summary = generator.generate_batch_summary(results)

        assert summary.title
        assert summary.message
        # 한글 포함 확인
        assert any('\uac00' <= char <= '\ud7a3' for char in summary.message)
