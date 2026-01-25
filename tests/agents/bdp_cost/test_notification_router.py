"""
NotificationRouter 및 KakaoNotifier 테스트.

환경별 알림 백엔드 라우팅 검증.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.agents.bdp_cost.services.anomaly_detector import (
    CostDriftDetector,
    CostDriftResult,
    Severity,
)
from src.agents.bdp_cost.services.kakao_notifier import KakaoNotifier, KakaoTokens
from src.agents.bdp_cost.services.cost_explorer_provider import ServiceCostData
from src.agents.bdp_cost.services.notification_router import (
    MockNotifier,
    NotificationBackend,
    NotificationRouter,
)
from src.agents.bdp_cost.services.summary_generator import SummaryGenerator


@pytest.fixture
def sample_spike_data() -> ServiceCostData:
    """테스트용 스파이크 데이터."""
    return ServiceCostData(
        service_name="Amazon Athena",
        account_id="111111111111",
        account_name="test-payer",
        current_cost=750000,
        historical_costs=[250000] * 13 + [750000],
        timestamps=[f"2025-01-{d:02d}" for d in range(8, 22)],
        currency="KRW",
    )


@pytest.fixture
def sample_result(sample_spike_data) -> CostDriftResult:
    """테스트용 탐지 결과."""
    detector = CostDriftDetector(sensitivity=0.7)
    return detector.analyze_service(sample_spike_data)


@pytest.fixture
def sample_summary(sample_result) -> "AlertSummary":
    """테스트용 알람 요약."""
    from src.agents.bdp_cost.services.summary_generator import AlertSummary

    generator = SummaryGenerator(currency="KRW")
    return generator.generate(sample_result)


class TestNotificationRouter:
    """NotificationRouter 테스트."""

    def test_auto_detect_mock_backend(self):
        """환경변수 없을 때 Mock 백엔드 선택."""
        # 환경변수 초기화
        with patch.dict(os.environ, {}, clear=True):
            router = NotificationRouter.from_env()
            assert router.backend == NotificationBackend.MOCK

    def test_explicit_backend_selection(self):
        """명시적 백엔드 선택."""
        router = NotificationRouter(backend=NotificationBackend.MOCK)
        assert router.backend == NotificationBackend.MOCK

    def test_env_backend_selection(self):
        """환경변수로 백엔드 선택."""
        with patch.dict(os.environ, {"NOTIFICATION_BACKEND": "mock"}):
            router = NotificationRouter.from_env()
            assert router.backend == NotificationBackend.MOCK

    def test_eventbridge_detection(self):
        """EventBridge 환경 감지."""
        with patch.dict(os.environ, {"EVENT_BUS": "test-bus"}, clear=True):
            router = NotificationRouter.from_env()
            assert router.backend == NotificationBackend.EVENTBRIDGE

    def test_kakao_detection(self):
        """카카오 환경 감지."""
        with patch.dict(
            os.environ,
            {"KAKAO_REST_API_KEY": "test-key"},
            clear=True,
        ):
            router = NotificationRouter.from_env()
            assert router.backend == NotificationBackend.KAKAO

    def test_send_alert_mock(self, sample_result, sample_summary):
        """Mock 백엔드 알람 발송."""
        router = NotificationRouter(backend=NotificationBackend.MOCK)

        result = router.send_alert(sample_result, sample_summary)

        assert result.success is True
        assert result.backend == NotificationBackend.MOCK
        assert "mock" in result.message.lower()

    def test_send_alert_with_fallback(self, sample_result, sample_summary):
        """Fallback 백엔드 테스트."""
        # Mock notifier가 실패하도록 설정
        failing_notifier = MagicMock()
        failing_notifier.send_alert.side_effect = Exception("Primary failed")

        router = NotificationRouter(
            backend=NotificationBackend.EVENTBRIDGE,
            fallback_backend=NotificationBackend.MOCK,
        )
        router._notifier = failing_notifier

        result = router.send_alert(sample_result, sample_summary)

        # Fallback(Mock)으로 성공
        assert result.success is True
        assert result.backend == NotificationBackend.MOCK


class TestMockNotifier:
    """MockNotifier 테스트."""

    def test_send_alert(self, sample_result, sample_summary):
        """Mock 알람 발송."""
        notifier = MockNotifier()

        success = notifier.send_alert(sample_result, sample_summary)

        assert success is True
        assert len(notifier.sent_alerts) == 1
        assert notifier.sent_alerts[0]["result"] == sample_result
        assert notifier.sent_alerts[0]["summary"] == sample_summary

    def test_clear_alerts(self, sample_result, sample_summary):
        """알람 기록 초기화."""
        notifier = MockNotifier()
        notifier.send_alert(sample_result, sample_summary)

        notifier.clear()

        assert len(notifier.sent_alerts) == 0


class TestKakaoNotifier:
    """KakaoNotifier 테스트."""

    def test_init_without_key(self):
        """API 키 없이 초기화 (환경변수, 설정파일 모두 없음)."""
        with patch.dict(os.environ, {}, clear=True):
            # 설정 파일 로드도 빈 결과 반환하도록 mock
            with patch.object(
                KakaoNotifier, "_load_config", return_value={}
            ):
                notifier = KakaoNotifier()
                assert notifier.rest_api_key is None

    def test_init_with_env_key(self):
        """환경변수에서 API 키 로드."""
        with patch.dict(os.environ, {"KAKAO_REST_API_KEY": "test-key"}):
            notifier = KakaoNotifier()
            assert notifier.rest_api_key == "test-key"

    def test_get_auth_url(self):
        """OAuth 인증 URL 생성."""
        notifier = KakaoNotifier(rest_api_key="test-key")

        url = notifier.get_auth_url()

        assert "kauth.kakao.com" in url
        assert "client_id=test-key" in url
        assert "response_type=code" in url

    def test_send_without_tokens(self, sample_result, sample_summary):
        """토큰 없이 발송 시도."""
        notifier = KakaoNotifier(rest_api_key="test-key")

        success = notifier.send_alert(sample_result, sample_summary)

        assert success is False

    @patch("requests.post")
    def test_send_text_message_success(self, mock_post):
        """텍스트 메시지 발송 성공."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"result_code": 0}

        notifier = KakaoNotifier(rest_api_key="test-key")
        notifier.tokens = KakaoTokens(
            access_token="test-access",
            refresh_token="test-refresh",
        )

        success = notifier.send_text_message("테스트 메시지")

        assert success is True
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_send_alert_success(self, mock_post, sample_result, sample_summary):
        """알람 발송 성공."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"result_code": 0}

        notifier = KakaoNotifier(rest_api_key="test-key")
        notifier.tokens = KakaoTokens(
            access_token="test-access",
            refresh_token="test-refresh",
        )

        success = notifier.send_alert(sample_result, sample_summary)

        assert success is True

    @patch("requests.post")
    def test_token_refresh_on_401(self, mock_post):
        """401 응답 시 토큰 갱신 후 재시도."""
        # 첫 번째 호출: 401, 두 번째(갱신): 200, 세 번째(재시도): 200
        responses = [
            MagicMock(status_code=401),  # 첫 발송 실패
            MagicMock(  # 토큰 갱신 성공
                status_code=200,
                json=lambda: {"access_token": "new-token", "refresh_token": "new-refresh"},
            ),
            MagicMock(  # 재발송 성공
                status_code=200,
                json=lambda: {"result_code": 0},
            ),
        ]
        mock_post.side_effect = responses

        notifier = KakaoNotifier(rest_api_key="test-key")
        notifier.tokens = KakaoTokens(
            access_token="old-access",
            refresh_token="old-refresh",
        )

        success = notifier.send_text_message("테스트")

        assert success is True
        assert mock_post.call_count == 3

    def test_save_and_load_tokens(self, tmp_path):
        """토큰 저장 및 로드."""
        token_file = tmp_path / "tokens.json"

        notifier = KakaoNotifier(
            rest_api_key="test-key",
            token_path=str(token_file),
        )
        notifier.tokens = KakaoTokens(
            access_token="test-access",
            refresh_token="test-refresh",
        )

        # 저장
        notifier.save_tokens()
        assert token_file.exists()

        # 새 인스턴스에서 로드
        notifier2 = KakaoNotifier(
            rest_api_key="test-key",
            token_path=str(token_file),
        )
        success = notifier2.load_tokens()

        assert success is True
        assert notifier2.tokens.access_token == "test-access"
        assert notifier2.tokens.refresh_token == "test-refresh"


class TestNotificationIntegration:
    """통합 테스트: 탐지 → 요약 → 알림."""

    def test_full_flow_with_mock(self, sample_spike_data):
        """전체 플로우 테스트 (Mock)."""
        # 1. 탐지
        detector = CostDriftDetector(sensitivity=0.7)
        result = detector.analyze_service(sample_spike_data)

        assert result.is_anomaly is True
        assert result.severity == Severity.CRITICAL

        # 2. 요약 생성
        generator = SummaryGenerator(currency="KRW")
        summary = generator.generate(result)

        assert "🚨" in summary.title or summary.severity_emoji == "🚨"

        # 3. 알림 발송 (Mock)
        router = NotificationRouter(backend=NotificationBackend.MOCK)
        notification_result = router.send_alert(result, summary)

        assert notification_result.success is True

        # 4. Mock에 기록 확인
        mock_notifier = router.notifier
        assert isinstance(mock_notifier, MockNotifier)
        assert len(mock_notifier.sent_alerts) == 1

    def test_environment_based_routing(self, sample_result, sample_summary):
        """환경변수 기반 라우팅."""
        test_cases = [
            ({"NOTIFICATION_BACKEND": "mock"}, NotificationBackend.MOCK),
            ({"NOTIFICATION_BACKEND": "eventbridge"}, NotificationBackend.EVENTBRIDGE),
            ({"NOTIFICATION_BACKEND": "kakao"}, NotificationBackend.KAKAO),
        ]

        for env_vars, expected_backend in test_cases:
            with patch.dict(os.environ, env_vars, clear=True):
                router = NotificationRouter.from_env()
                assert router.backend == expected_backend, (
                    f"Expected {expected_backend} for env {env_vars}"
                )
