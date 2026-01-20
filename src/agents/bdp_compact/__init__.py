"""
BDP Compact Agent - Multi-Account Cost Drift Detection.

Quick-win agent for AWS Cost Explorer based cost drift detection
with KakaoTalk alert integration via EventBridge.
"""

from src.agents.bdp_compact.handler import BDPCompactHandler, handler

__all__ = ["BDPCompactHandler", "handler"]
