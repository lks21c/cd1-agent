"""
KakaoTalk Notification Provider (Common).

카카오톡 "나에게 보내기" API 공통 모듈.
bdp_cost, bdp_drift 등 여러 에이전트에서 공유.

Setup:
1. https://developers.kakao.com 에서 앱 생성
2. REST API 키 발급
3. 카카오 로그인 활성화 + Redirect URI 설정
4. 토큰 발급 스크립트 실행

Reference:
- https://developers.kakao.com/docs/latest/ko/kakaotalk-message/rest-api
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from src.agents.bdp_common.kakao.models import KakaoTokens

logger = logging.getLogger(__name__)


class KakaoNotifier:
    """
    카카오톡 나에게 보내기 알림 발송기.

    공통 모듈로 토큰 관리 및 기본 메시지 발송 기능 제공.
    도메인별 알림 로직은 각 에이전트에서 구현.

    Usage:
        notifier = KakaoNotifier(rest_api_key="YOUR_KEY")
        notifier.load_tokens("kakao_tokens.json")
        success = notifier.send_text_message("테스트 메시지")
    """

    # API Endpoints
    AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
    TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    SEND_ME_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

    def __init__(
        self,
        rest_api_key: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: str = "https://localhost:5000",
        token_path: Optional[str] = None,
        config_dir: Optional[str] = None,
    ):
        """KakaoNotifier 초기화.

        Args:
            rest_api_key: Kakao REST API 키 (없으면 환경변수 또는 설정파일에서 로드)
            client_secret: Kakao Client Secret (없으면 설정파일에서 로드)
            redirect_uri: OAuth redirect URI
            token_path: 토큰 저장 파일 경로
            config_dir: 설정 디렉토리 경로 (없으면 기본값 사용)
        """
        self._config_dir = config_dir
        config = self._load_config()
        self.rest_api_key = rest_api_key or config.get("rest_api_key")
        self.client_secret = client_secret or config.get("client_secret")
        self.redirect_uri = redirect_uri
        self.token_path = token_path or self._default_token_path()
        self.tokens: Optional[KakaoTokens] = None

        if not self.rest_api_key:
            logger.warning(
                "KAKAO_REST_API_KEY not set. "
                "KakaoNotifier will not work without it."
            )

    def _default_token_path(self) -> str:
        """기본 토큰 파일 경로."""
        if self._config_dir:
            return str(Path(self._config_dir) / "kakao_tokens.json")
        module_dir = Path(__file__).parent.parent
        return str(module_dir / "conf" / "kakao_tokens.json")

    def _load_config(self) -> Dict[str, Any]:
        """설정 로드 (환경변수 → 설정파일 순서).

        Returns:
            설정 딕셔너리 (rest_api_key, client_secret 등)
        """
        config: Dict[str, Any] = {}

        # 1. 환경변수에서 로드
        if os.getenv("KAKAO_REST_API_KEY"):
            config["rest_api_key"] = os.getenv("KAKAO_REST_API_KEY")
        if os.getenv("KAKAO_CLIENT_SECRET"):
            config["client_secret"] = os.getenv("KAKAO_CLIENT_SECRET")

        # 2. 설정 파일에서 로드 (환경변수가 없는 항목만)
        if self._config_dir:
            config_path = Path(self._config_dir) / "kakao_config.json"
        else:
            config_path = Path(__file__).parent.parent / "conf" / "kakao_config.json"

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    file_config = json.load(f)
                for key in ["rest_api_key", "client_secret"]:
                    if key not in config and key in file_config:
                        config[key] = file_config[key]
                if config:
                    logger.info(f"Loaded REST API key from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load kakao_config.json: {e}")

        return config

    # =========================================================================
    # Token Management
    # =========================================================================

    def get_auth_url(self) -> str:
        """OAuth 인증 URL 생성.

        브라우저에서 이 URL을 열어 로그인하면 redirect_uri로 code가 전달됨.

        Returns:
            인증 URL
        """
        params = {
            "client_id": self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "talk_message",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def get_tokens_from_code(self, auth_code: str) -> KakaoTokens:
        """인증 코드로 토큰 발급.

        Args:
            auth_code: OAuth 인증 후 받은 code

        Returns:
            KakaoTokens 객체
        """
        data: Dict[str, Any] = {
            "grant_type": "authorization_code",
            "client_id": self.rest_api_key,
            "redirect_uri": self.redirect_uri,
            "code": auth_code,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret

        response = requests.post(self.TOKEN_URL, data=data, timeout=10)
        response.raise_for_status()
        result = response.json()

        self.tokens = KakaoTokens(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
        )

        self.save_tokens()
        logger.info("Kakao tokens obtained successfully")
        return self.tokens

    def refresh_access_token(self) -> bool:
        """Refresh token으로 access token 갱신.

        Returns:
            갱신 성공 여부
        """
        if not self.tokens or not self.tokens.refresh_token:
            logger.error("No refresh token available")
            return False

        data: Dict[str, Any] = {
            "grant_type": "refresh_token",
            "client_id": self.rest_api_key,
            "refresh_token": self.tokens.refresh_token,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret

        try:
            response = requests.post(self.TOKEN_URL, data=data, timeout=10)
            response.raise_for_status()
            result = response.json()

            self.tokens.access_token = result["access_token"]
            if "refresh_token" in result:
                self.tokens.refresh_token = result["refresh_token"]

            self.save_tokens()
            logger.info("Kakao access token refreshed")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return False

    def save_tokens(self, path: Optional[str] = None) -> None:
        """토큰을 파일에 저장.

        Args:
            path: 저장 경로 (없으면 기본 경로 사용)
        """
        if not self.tokens:
            return

        save_path = path or self.token_path

        data = {
            "access_token": self.tokens.access_token,
            "refresh_token": self.tokens.refresh_token,
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Tokens saved to {save_path}")

    def load_tokens(self, path: Optional[str] = None) -> bool:
        """파일에서 토큰 로드.

        Args:
            path: 로드 경로 (없으면 기본 경로 사용)

        Returns:
            로드 성공 여부
        """
        load_path = path or self.token_path

        try:
            with open(load_path, encoding="utf-8") as f:
                data = json.load(f)

            self.tokens = KakaoTokens(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
            )

            logger.info(f"Tokens loaded from {load_path}")
            return True

        except FileNotFoundError:
            logger.warning(f"Token file not found: {load_path}")
            return False
        except Exception as e:
            logger.error(f"Failed to load tokens: {e}")
            return False

    # =========================================================================
    # Message Sending
    # =========================================================================

    def send_text_message(self, text: str) -> bool:
        """텍스트 메시지 발송.

        Args:
            text: 발송할 텍스트

        Returns:
            발송 성공 여부
        """
        if not self.tokens:
            logger.error("No tokens available. Call load_tokens() first.")
            return False

        template_object = {
            "object_type": "text",
            "text": text,
            "link": {
                "web_url": "https://developers.kakao.com",
                "mobile_web_url": "https://developers.kakao.com",
            },
        }

        return self._send_memo(template_object)

    def send_feed_message(
        self,
        title: str,
        description: str,
        image_url: Optional[str] = None,
        link_url: Optional[str] = None,
    ) -> bool:
        """피드 형식 메시지 발송.

        Args:
            title: 제목
            description: 설명
            image_url: 이미지 URL (선택)
            link_url: 링크 URL (선택)

        Returns:
            발송 성공 여부
        """
        if not self.tokens:
            logger.error("No tokens available. Call load_tokens() first.")
            return False

        template_object: Dict[str, Any] = {
            "object_type": "feed",
            "content": {
                "title": title,
                "description": description,
                "link": {
                    "web_url": link_url or "https://developers.kakao.com",
                    "mobile_web_url": link_url or "https://developers.kakao.com",
                },
            },
        }

        if image_url:
            template_object["content"]["image_url"] = image_url

        return self._send_memo(template_object)

    def send_feed_with_items(
        self,
        title: str,
        description: str,
        items: List[Dict[str, str]],
        image_url: Optional[str] = None,
        link_url: Optional[str] = None,
    ) -> bool:
        """피드 B형 메시지 발송 (item_content 포함).

        item_content를 사용하면 상세 항목을 최대 5개까지 표시할 수 있음.

        Args:
            title: 메시지 제목
            description: 간단한 설명
            items: 상세 항목 리스트 [{"item": "항목명", "item_op": "값"}, ...]
            image_url: 차트/이미지 URL
            link_url: 클릭 시 이동할 URL

        Returns:
            발송 성공 여부
        """
        if not self.tokens:
            logger.error("No tokens available. Call load_tokens() first.")
            return False

        template_object: Dict[str, Any] = {
            "object_type": "feed",
            "content": {
                "title": title,
                "description": description,
                "link": {
                    "web_url": link_url or "https://developers.kakao.com",
                    "mobile_web_url": link_url or "https://developers.kakao.com",
                },
            },
            "item_content": {
                "items": items[:5],
            },
        }

        if image_url:
            template_object["content"]["image_url"] = image_url
            template_object["content"]["image_link"] = {
                "web_url": image_url,
                "mobile_web_url": image_url,
            }

        return self._send_memo(template_object)

    def send_image_message(
        self,
        title: str,
        description: str,
        image_url: str,
        button_title: str = "🔍 이미지 확대 보기",
    ) -> bool:
        """이미지 메시지 발송 (버튼으로 확대 보기).

        Args:
            title: 제목
            description: 설명
            image_url: 이미지 URL
            button_title: 버튼 텍스트

        Returns:
            발송 성공 여부
        """
        if not self.tokens:
            logger.error("No tokens available. Call load_tokens() first.")
            return False

        template_object: Dict[str, Any] = {
            "object_type": "feed",
            "content": {
                "title": title,
                "description": description,
                "image_url": image_url,
                "link": {
                    "web_url": image_url,
                    "mobile_web_url": image_url,
                },
            },
            "buttons": [
                {
                    "title": button_title,
                    "link": {
                        "web_url": image_url,
                        "mobile_web_url": image_url,
                    },
                },
            ],
        }

        return self._send_memo(template_object)

    def _send_memo(self, template_object: Dict[str, Any]) -> bool:
        """나에게 메시지 발송 API 호출.

        Args:
            template_object: 메시지 템플릿 객체

        Returns:
            발송 성공 여부
        """
        if not self.tokens:
            logger.error("No tokens available")
            return False

        headers = {
            "Authorization": f"Bearer {self.tokens.access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {
            "template_object": json.dumps(template_object),
        }

        try:
            response = requests.post(
                self.SEND_ME_URL,
                headers=headers,
                data=data,
                timeout=10,
            )

            # 토큰 만료 시 갱신 후 재시도
            if response.status_code == 401:
                logger.info("Access token expired, refreshing...")
                if self.refresh_access_token():
                    headers["Authorization"] = f"Bearer {self.tokens.access_token}"
                    response = requests.post(
                        self.SEND_ME_URL,
                        headers=headers,
                        data=data,
                        timeout=10,
                    )
                else:
                    return False

            response.raise_for_status()

            result = response.json()
            if result.get("result_code") == 0:
                logger.info("KakaoTalk message sent successfully")
                return True
            else:
                logger.error(f"KakaoTalk send failed: {result}")
                return False

        except Exception as e:
            logger.error(f"Failed to send KakaoTalk message: {e}")
            return False


# =============================================================================
# CLI Tool for Token Setup
# =============================================================================


def setup_kakao_tokens():
    """카카오 토큰 설정 CLI 도구.

    Usage:
        python -m src.agents.bdp_common.kakao.notifier
    """
    import sys

    print("=" * 60)
    print("카카오톡 나에게 보내기 - 토큰 설정")
    print("=" * 60)

    rest_api_key = os.getenv("KAKAO_REST_API_KEY")
    if not rest_api_key:
        rest_api_key = input("REST API 키를 입력하세요: ").strip()

    notifier = KakaoNotifier(rest_api_key=rest_api_key)

    print("\n1. 아래 URL을 브라우저에서 열어 로그인하세요:")
    print("-" * 60)
    print(notifier.get_auth_url())
    print("-" * 60)

    print("\n2. 로그인 후 리다이렉트된 URL에서 code= 값을 복사하세요.")
    print("   예: https://localhost:5000?code=XXXXXX")

    auth_code = input("\n인증 코드를 입력하세요: ").strip()

    try:
        tokens = notifier.get_tokens_from_code(auth_code)
        print(f"\n✅ 토큰 발급 성공!")
        print(f"   저장 위치: {notifier.token_path}")

        test = input("\n테스트 메시지를 보내시겠습니까? (y/n): ").strip().lower()
        if test == "y":
            success = notifier.send_text_message(
                "🎉 CD1 Agent 카카오톡 알림 설정 완료!\n\n"
                "이제 비용 이상 탐지 시 카카오톡으로 알림을 받을 수 있습니다."
            )
            if success:
                print("✅ 테스트 메시지 발송 성공!")
            else:
                print("❌ 테스트 메시지 발송 실패")

    except Exception as e:
        print(f"\n❌ 토큰 발급 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    setup_kakao_tokens()
