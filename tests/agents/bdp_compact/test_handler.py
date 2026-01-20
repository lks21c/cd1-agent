"""
BDPCompactHandler 테스트.

Lambda/FastAPI 핸들러 단위 테스트.
"""

import pytest


class TestBDPCompactHandler:
    """BDPCompactHandler 테스트."""

    def test_handler_initialization(self, bdp_handler_mock):
        """핸들러 초기화."""
        assert bdp_handler_mock is not None
        assert bdp_handler_mock.provider is not None
        assert bdp_handler_mock.detector is not None
        assert bdp_handler_mock.summary_generator is not None
        assert bdp_handler_mock.event_publisher is not None

    def test_process_returns_expected_structure(self, bdp_handler_mock):
        """process 메서드 결과 구조."""
        event = {"days": 14}
        context = type("Context", (), {"aws_request_id": "test-123"})()

        response = bdp_handler_mock.handle(event, context)

        assert response["statusCode"] == 200
        body = __import__("json").loads(response["body"])
        assert body["success"] is True
        assert "data" in body

        data = body["data"]
        assert "detection_type" in data
        assert "period_days" in data
        assert "accounts_analyzed" in data
        assert "services_analyzed" in data
        assert "anomalies_detected" in data
        assert "total_anomalies" in data
        assert "severity_breakdown" in data
        assert "summary" in data
        assert "results" in data
        assert "detection_timestamp" in data

    def test_process_with_custom_days(self, bdp_handler_mock):
        """사용자 정의 기간."""
        event = {"days": 7}
        context = type("Context", (), {"aws_request_id": "test-123"})()

        response = bdp_handler_mock.handle(event, context)
        body = __import__("json").loads(response["body"])
        data = body["data"]

        assert data["period_days"] == 7

    def test_process_with_min_cost_threshold(self, bdp_handler_mock):
        """최소 비용 임계값 적용."""
        event = {"days": 14, "min_cost_threshold": 100000}
        context = type("Context", (), {"aws_request_id": "test-123"})()

        response = bdp_handler_mock.handle(event, context)
        body = __import__("json").loads(response["body"])
        data = body["data"]

        # 임계값 이하 서비스는 필터링됨
        for result in data.get("results", []):
            assert (
                result["current_cost"] >= 100000 or
                result["historical_average"] >= 100000
            )

    def test_severity_breakdown_structure(self, bdp_handler_mock):
        """심각도 분류 구조."""
        event = {"days": 14}
        context = type("Context", (), {"aws_request_id": "test-123"})()

        response = bdp_handler_mock.handle(event, context)
        body = __import__("json").loads(response["body"])
        data = body["data"]

        severity_breakdown = data["severity_breakdown"]
        assert "critical" in severity_breakdown
        assert "high" in severity_breakdown
        assert "medium" in severity_breakdown
        assert "low" in severity_breakdown

    def test_result_contains_korean_summary(self, bdp_handler_mock, mock_spike_provider):
        """결과에 한글 요약 포함."""
        # Mock provider를 스파이크 데이터로 교체
        bdp_handler_mock.provider = mock_spike_provider

        event = {"days": 14}
        context = type("Context", (), {"aws_request_id": "test-123"})()

        response = bdp_handler_mock.handle(event, context)
        body = __import__("json").loads(response["body"])
        data = body["data"]

        if data["results"]:
            # 한글 문자가 포함되어 있는지 확인
            result = data["results"][0]
            if "summary" in result:
                # 한글 유니코드 범위 확인
                has_korean = any('\uac00' <= char <= '\ud7a3' for char in result["summary"])
                assert has_korean, "Summary should contain Korean characters"

    def test_publish_alerts_false_skips_event(self, bdp_handler_mock):
        """publish_alerts=False일 때 이벤트 발행 건너뜀."""
        event = {"days": 14, "publish_alerts": False}
        context = type("Context", (), {"aws_request_id": "test-123"})()

        # Mock provider로 이벤트 발행 확인
        bdp_handler_mock.event_publisher.clear_published_events()

        response = bdp_handler_mock.handle(event, context)

        # 이벤트가 발행되지 않아야 함
        published = bdp_handler_mock.event_publisher.get_published_events()
        assert len(published) == 0

    def test_parse_body_from_api_gateway(self, bdp_handler_mock):
        """API Gateway 형식 body 파싱."""
        import json

        event = {
            "body": json.dumps({"days": 21, "min_cost_threshold": 50000})
        }
        context = type("Context", (), {"aws_request_id": "test-123"})()

        response = bdp_handler_mock.handle(event, context)
        body = json.loads(response["body"])
        data = body["data"]

        assert data["period_days"] == 21


class TestBDPCompactHandlerLocalStack:
    """LocalStack 통합 테스트."""

    @pytest.mark.localstack
    def test_localstack_detection(self, localstack_bdp_handler, inject_bdp_baseline):
        """LocalStack 연동 탐지 테스트."""
        if not inject_bdp_baseline:
            pytest.skip("Baseline data not injected")

        event = {"days": 14}
        context = type("Context", (), {"aws_request_id": "test-123"})()

        response = localstack_bdp_handler.handle(event, context)

        assert response["statusCode"] == 200
        body = __import__("json").loads(response["body"])
        data = body["data"]

        assert data["accounts_analyzed"] >= 1
        assert data["services_analyzed"] >= 1
