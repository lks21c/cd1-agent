"""BDP Agent - AWS CloudWatch/Logs Detection Agent."""

from src.agents.bdp.handler import DetectionHandler, handler

__all__ = [
    "DetectionHandler",
    "handler",
]
