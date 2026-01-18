"""HDSP Agent - On-Prem Kubernetes Detection Agent."""

from src.agents.hdsp.handler import HDSPDetectionHandler, handler

__all__ = [
    "HDSPDetectionHandler",
    "handler",
]
