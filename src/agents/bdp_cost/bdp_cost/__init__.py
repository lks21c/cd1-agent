"""
BDP Compact Agent - Multi-Account Cost Drift Detection.

Standalone package for AWS Cost Explorer based cost drift detection
with KakaoTalk alert integration via EventBridge.
"""

from bdp_cost.handler import BDPCostHandler, handler
from bdp_cost.services.anomaly_detector import (
    CostDriftDetector,
    CostDriftResult,
    Severity,
)
from bdp_cost.services.multi_account_provider import (
    AccountConfig,
    BaseMultiAccountProvider,
    ServiceCostData,
    create_provider,
)
from bdp_cost.services.summary_generator import AlertSummary, SummaryGenerator
from bdp_cost.services.event_publisher import EventPublisher, AlertEvent

__version__ = "0.1.0"

__all__ = [
    # Handler
    "BDPCostHandler",
    "handler",
    # Detector
    "CostDriftDetector",
    "CostDriftResult",
    "Severity",
    # Provider
    "AccountConfig",
    "BaseMultiAccountProvider",
    "ServiceCostData",
    "create_provider",
    # Summary
    "AlertSummary",
    "SummaryGenerator",
    # Event
    "EventPublisher",
    "AlertEvent",
]
