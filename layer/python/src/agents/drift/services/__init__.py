"""Drift Agent Services."""

from src.agents.drift.services.config_fetcher import (
    ConfigFetcher,
    ConfigProvider,
    ResourceType,
    ResourceConfig,
)
from src.agents.drift.services.drift_detector import (
    ConfigDriftDetector,
    DriftType,
    DriftSeverity,
    DriftedField,
    DriftResult,
    AggregatedDriftResult,
)
from src.agents.drift.services.baseline_loader import (
    BaselineLoader,
    BaselineProvider,
    BaselineFile,
)
from src.agents.drift.services.drift_analyzer import (
    DriftAnalyzer,
    BaseDriftAnalyzerProvider,
    RealDriftAnalyzerProvider,
    MockDriftAnalyzerProvider,
    AnalysisState,
    analyze_drift,
)

# Backward compatibility aliases
GitLabClient = BaselineLoader
GitLabProvider = BaselineProvider

__all__ = [
    # Config fetcher
    "ConfigFetcher",
    "ConfigProvider",
    "ResourceType",
    "ResourceConfig",
    # Drift detector
    "ConfigDriftDetector",
    "DriftType",
    "DriftSeverity",
    "DriftedField",
    "DriftResult",
    "AggregatedDriftResult",
    # Baseline loader
    "BaselineLoader",
    "BaselineProvider",
    "BaselineFile",
    # Drift analyzer (LLM-based)
    "DriftAnalyzer",
    "BaseDriftAnalyzerProvider",
    "RealDriftAnalyzerProvider",
    "MockDriftAnalyzerProvider",
    "AnalysisState",
    "analyze_drift",
    # Backward compatibility aliases
    "GitLabClient",
    "GitLabProvider",
]
