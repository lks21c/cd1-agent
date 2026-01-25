"""
Detection Config Loader for BDP Compact Agent.

탐지 설정 로더 - conf/detection_config.json에서 설정을 로드합니다.
파일이 없거나 로드 실패 시 기본값을 사용합니다.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default config file path (relative to this module)
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "conf" / "detection_config.json"


@dataclass
class EnsembleConfig:
    """앙상블 탐지 설정."""

    ecod_weight: float = 0.4
    ratio_weight: float = 0.3
    stddev_weight: float = 0.3


@dataclass
class StddevConfig:
    """Z-Score 탐지 설정."""

    z_score_threshold: float = 3.0
    min_data_points: int = 7


@dataclass
class DayOfWeekConfig:
    """요일 패턴 설정."""

    enabled: bool = True
    adjustment: float = -0.20
    tolerance_ratio: float = 0.30


@dataclass
class TrendConfig:
    """추세 패턴 설정."""

    enabled: bool = True
    adjustment: float = -0.15
    deviation_threshold: float = 0.15


@dataclass
class MonthCycleConfig:
    """월초/월말 패턴 설정."""

    enabled: bool = False
    adjustment: float = -0.15
    month_start_days: List[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])
    month_end_days: List[int] = field(default_factory=lambda: [26, 27, 28, 29, 30, 31])
    tolerance_ratio: float = 0.30


@dataclass
class ServiceProfileConfig:
    """서비스 프로파일 패턴 설정."""

    enabled: bool = False
    adjustment: float = -0.10
    spike_normal_services: List[str] = field(
        default_factory=lambda: [
            "AWS Lambda",
            "AWS Batch",
            "AWS Glue",
            "Amazon Athena",
            "AWS Step Functions",
        ]
    )


@dataclass
class PatternsConfig:
    """패턴 인식 설정."""

    enabled: bool = True
    mode: str = "active"  # "active" or "shadow"
    max_adjustment: float = 0.4
    day_of_week: DayOfWeekConfig = field(default_factory=DayOfWeekConfig)
    trend: TrendConfig = field(default_factory=TrendConfig)
    month_cycle: MonthCycleConfig = field(default_factory=MonthCycleConfig)
    service_profile: ServiceProfileConfig = field(default_factory=ServiceProfileConfig)


@dataclass
class DetectionConfig:
    """전체 탐지 설정."""

    ensemble: EnsembleConfig = field(default_factory=EnsembleConfig)
    stddev: StddevConfig = field(default_factory=StddevConfig)
    patterns: PatternsConfig = field(default_factory=PatternsConfig)


def _parse_ensemble_config(data: Dict[str, Any]) -> EnsembleConfig:
    """앙상블 설정 파싱."""
    weights = data.get("weights", {})
    return EnsembleConfig(
        ecod_weight=weights.get("ecod", 0.4),
        ratio_weight=weights.get("ratio", 0.3),
        stddev_weight=weights.get("stddev", 0.3),
    )


def _parse_stddev_config(data: Dict[str, Any]) -> StddevConfig:
    """Stddev 설정 파싱."""
    return StddevConfig(
        z_score_threshold=data.get("z_score_threshold", 3.0),
        min_data_points=data.get("min_data_points", 7),
    )


def _parse_patterns_config(data: Dict[str, Any]) -> PatternsConfig:
    """패턴 설정 파싱."""
    dow_data = data.get("day_of_week", {})
    trend_data = data.get("trend", {})
    mc_data = data.get("month_cycle", {})
    sp_data = data.get("service_profile", {})

    return PatternsConfig(
        enabled=data.get("enabled", True),
        mode=data.get("mode", "active"),
        max_adjustment=data.get("max_adjustment", 0.4),
        day_of_week=DayOfWeekConfig(
            enabled=dow_data.get("enabled", True),
            adjustment=dow_data.get("adjustment", -0.20),
            tolerance_ratio=dow_data.get("tolerance_ratio", 0.30),
        ),
        trend=TrendConfig(
            enabled=trend_data.get("enabled", True),
            adjustment=trend_data.get("adjustment", -0.15),
            deviation_threshold=trend_data.get("deviation_threshold", 0.15),
        ),
        month_cycle=MonthCycleConfig(
            enabled=mc_data.get("enabled", False),
            adjustment=mc_data.get("adjustment", -0.15),
            month_start_days=mc_data.get("month_start_days", [1, 2, 3, 4, 5]),
            month_end_days=mc_data.get("month_end_days", [26, 27, 28, 29, 30, 31]),
            tolerance_ratio=mc_data.get("tolerance_ratio", 0.30),
        ),
        service_profile=ServiceProfileConfig(
            enabled=sp_data.get("enabled", False),
            adjustment=sp_data.get("adjustment", -0.10),
            spike_normal_services=sp_data.get(
                "spike_normal_services",
                ["AWS Lambda", "AWS Batch", "AWS Glue", "Amazon Athena", "AWS Step Functions"],
            ),
        ),
    )


def load_detection_config(config_path: Optional[Path] = None) -> DetectionConfig:
    """탐지 설정 로드.

    conf/detection_config.json 파일에서 설정을 로드합니다.
    파일이 없거나 로드 실패 시 기본값을 사용합니다.

    Args:
        config_path: 설정 파일 경로 (기본: conf/detection_config.json)

    Returns:
        DetectionConfig 인스턴스
    """
    if config_path is None:
        # 환경 변수로 경로 오버라이드 가능
        env_path = os.getenv("BDP_DETECTION_CONFIG_PATH")
        if env_path:
            config_path = Path(env_path)
        else:
            config_path = DEFAULT_CONFIG_PATH

    try:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            config = DetectionConfig(
                ensemble=_parse_ensemble_config(data.get("ensemble", {})),
                stddev=_parse_stddev_config(data.get("stddev", {})),
                patterns=_parse_patterns_config(data.get("patterns", {})),
            )

            logger.info(f"Detection config loaded from {config_path}")
            return config

        else:
            logger.info(f"Config file not found at {config_path}, using defaults")
            return DetectionConfig()

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to parse config file {config_path}: {e}, using defaults")
        return DetectionConfig()

    except Exception as e:
        logger.warning(f"Unexpected error loading config: {e}, using defaults")
        return DetectionConfig()


# Singleton cached config
_cached_config: Optional[DetectionConfig] = None


def get_detection_config(force_reload: bool = False) -> DetectionConfig:
    """캐시된 탐지 설정 반환.

    Args:
        force_reload: True이면 설정 파일을 다시 로드

    Returns:
        DetectionConfig 인스턴스
    """
    global _cached_config

    if _cached_config is None or force_reload:
        _cached_config = load_detection_config()

    return _cached_config


def reset_config_cache() -> None:
    """설정 캐시 초기화 (테스트용)."""
    global _cached_config
    _cached_config = None
