"""
BDP Compact Agent - Multi-Account Cost Drift Detection.

Quick-win agent for AWS Cost Explorer based cost drift detection
with KakaoTalk alert integration via EventBridge.
"""

from src.agents.bdp_cost.handler import BDPCostHandler, handler

__all__ = ["BDPCostHandler", "handler"]
