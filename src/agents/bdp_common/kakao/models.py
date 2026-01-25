"""
Kakao API models.

Data classes for Kakao API integration.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class KakaoTokens:
    """카카오 OAuth 토큰."""

    access_token: str
    refresh_token: str
    expires_at: Optional[datetime] = None
