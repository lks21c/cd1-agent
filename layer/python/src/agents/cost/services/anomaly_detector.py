"""
Cost Anomaly Detector with Luminol Integration.

LinkedIn's Luminol library for advanced time-series anomaly detection.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Graceful degradation for Luminol
try:
    from luminol.anomaly_detector import AnomalyDetector as LuminolDetector
    from luminol.modules.time_series import TimeSeries

    LUMINOL_AVAILABLE = True
except ImportError:
    LUMINOL_AVAILABLE = False
    logger.warning("Luminol not available, using fallback detection methods")


class DetectionMethod(str, Enum):
    """Available anomaly detection methods."""

    RATIO = "ratio"
    STDDEV = "stddev"
    TREND = "trend"
    LUMINOL = "luminol"
    ENSEMBLE = "ensemble"


@dataclass
class AnomalyScore:
    """Individual anomaly score result."""

    method: DetectionMethod
    score: float
    is_anomaly: bool
    details: Dict[str, Any]


@dataclass
class CostAnomalyResult:
    """Complete cost anomaly detection result."""

    is_anomaly: bool
    confidence_score: float
    severity: str
    service_name: str
    current_value: float
    previous_value: float
    change_ratio: float
    detection_results: List[AnomalyScore]
    detected_methods: List[str]
    analysis: str
    timestamp: str


class CostAnomalyDetector:
    """
    Cost anomaly detector with multiple detection algorithms.

    Combines statistical methods with LinkedIn's Luminol for robust detection.

    Usage:
        detector = CostAnomalyDetector(sensitivity=0.7)

        # Analyze single service
        result = detector.analyze_service(
            service_name="lambda",
            current_cost=150.0,
            historical_costs=[100.0, 102.0, 98.0, 105.0, 101.0],
            timestamps=["2024-01-01", ...]
        )

        # Batch analysis
        results = detector.analyze_batch(cost_data)
    """

    def __init__(
        self,
        sensitivity: float = 0.7,
        min_data_points: int = 7,
        anomaly_threshold: float = 0.6,
    ):
        """
        Initialize detector.

        Args:
            sensitivity: Detection sensitivity (0.0-1.0), higher = more sensitive
            min_data_points: Minimum historical data points required
            anomaly_threshold: Threshold for considering result as anomaly
        """
        self.sensitivity = sensitivity
        self.min_data_points = min_data_points
        self.anomaly_threshold = anomaly_threshold

        # Derived thresholds from sensitivity
        self.ratio_threshold = 1.0 + (1.5 - sensitivity)  # 1.5x to 2.5x
        self.stddev_threshold = 3.0 - sensitivity  # 2.0 to 3.0 std devs
        self.trend_threshold = 0.3 - (sensitivity * 0.1)  # 0.2 to 0.3

    def analyze_service(
        self,
        service_name: str,
        current_cost: float,
        historical_costs: List[float],
        timestamps: Optional[List[str]] = None,
    ) -> CostAnomalyResult:
        """
        Analyze cost anomaly for a single service.

        Args:
            service_name: AWS service name
            current_cost: Current period cost
            historical_costs: List of historical costs (oldest first)
            timestamps: Optional list of timestamps for each cost

        Returns:
            CostAnomalyResult with detection details
        """
        if len(historical_costs) < self.min_data_points:
            return self._create_insufficient_data_result(
                service_name, current_cost, historical_costs
            )

        detection_results = []
        previous_value = historical_costs[-1] if historical_costs else 0.0
        change_ratio = (
            (current_cost - previous_value) / previous_value
            if previous_value > 0
            else 0.0
        )

        # Run all detection methods
        detection_results.append(
            self._detect_ratio_anomaly(current_cost, historical_costs)
        )
        detection_results.append(
            self._detect_stddev_anomaly(current_cost, historical_costs)
        )
        detection_results.append(
            self._detect_trend_anomaly(current_cost, historical_costs)
        )

        if LUMINOL_AVAILABLE and timestamps:
            luminol_result = self._detect_luminol_anomaly(
                current_cost, historical_costs, timestamps
            )
            if luminol_result:
                detection_results.append(luminol_result)

        # Calculate ensemble score
        detected_methods = [r.method.value for r in detection_results if r.is_anomaly]
        confidence_score = self._calculate_ensemble_score(detection_results)
        is_anomaly = confidence_score >= self.anomaly_threshold

        severity = self._calculate_severity(confidence_score, change_ratio)
        analysis = self._generate_analysis(
            service_name, current_cost, previous_value, detection_results, is_anomaly
        )

        return CostAnomalyResult(
            is_anomaly=is_anomaly,
            confidence_score=confidence_score,
            severity=severity,
            service_name=service_name,
            current_value=current_cost,
            previous_value=previous_value,
            change_ratio=change_ratio,
            detection_results=detection_results,
            detected_methods=detected_methods,
            analysis=analysis,
            timestamp=datetime.utcnow().isoformat(),
        )

    def analyze_batch(
        self, cost_data: Dict[str, Dict[str, Any]]
    ) -> List[CostAnomalyResult]:
        """
        Analyze multiple services for cost anomalies.

        Args:
            cost_data: Dict of service_name -> {current_cost, historical_costs, timestamps}

        Returns:
            List of CostAnomalyResult for each service
        """
        results = []
        for service_name, data in cost_data.items():
            result = self.analyze_service(
                service_name=service_name,
                current_cost=data.get("current_cost", 0.0),
                historical_costs=data.get("historical_costs", []),
                timestamps=data.get("timestamps"),
            )
            results.append(result)

        # Sort by confidence score descending
        results.sort(key=lambda r: r.confidence_score, reverse=True)
        return results

    def _detect_ratio_anomaly(
        self, current: float, historical: List[float]
    ) -> AnomalyScore:
        """Detect anomaly using simple ratio comparison."""
        avg_historical = sum(historical) / len(historical) if historical else 0.0
        ratio = current / avg_historical if avg_historical > 0 else 0.0

        is_anomaly = ratio > self.ratio_threshold or ratio < (1 / self.ratio_threshold)
        score = min(1.0, abs(ratio - 1.0) / self.ratio_threshold)

        return AnomalyScore(
            method=DetectionMethod.RATIO,
            score=score,
            is_anomaly=is_anomaly,
            details={
                "ratio": ratio,
                "threshold": self.ratio_threshold,
                "average_historical": avg_historical,
            },
        )

    def _detect_stddev_anomaly(
        self, current: float, historical: List[float]
    ) -> AnomalyScore:
        """Detect anomaly using standard deviation."""
        import statistics

        if len(historical) < 2:
            return AnomalyScore(
                method=DetectionMethod.STDDEV,
                score=0.0,
                is_anomaly=False,
                details={"reason": "insufficient_data"},
            )

        mean = statistics.mean(historical)
        stddev = statistics.stdev(historical)

        if stddev == 0:
            is_anomaly = current != mean
            z_score = float("inf") if is_anomaly else 0.0
        else:
            z_score = abs(current - mean) / stddev
            is_anomaly = z_score > self.stddev_threshold

        score = min(1.0, z_score / (self.stddev_threshold * 2))

        return AnomalyScore(
            method=DetectionMethod.STDDEV,
            score=score,
            is_anomaly=is_anomaly,
            details={
                "z_score": z_score,
                "threshold": self.stddev_threshold,
                "mean": mean,
                "stddev": stddev,
            },
        )

    def _detect_trend_anomaly(
        self, current: float, historical: List[float]
    ) -> AnomalyScore:
        """Detect anomaly based on trend deviation."""
        if len(historical) < 3:
            return AnomalyScore(
                method=DetectionMethod.TREND,
                score=0.0,
                is_anomaly=False,
                details={"reason": "insufficient_data"},
            )

        # Calculate linear trend
        n = len(historical)
        x_mean = (n - 1) / 2
        y_mean = sum(historical) / n

        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(historical))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        # Predicted value for current period
        predicted = slope * n + intercept
        deviation = abs(current - predicted) / predicted if predicted > 0 else 0

        is_anomaly = deviation > self.trend_threshold
        score = min(1.0, deviation / (self.trend_threshold * 2))

        return AnomalyScore(
            method=DetectionMethod.TREND,
            score=score,
            is_anomaly=is_anomaly,
            details={
                "predicted": predicted,
                "deviation": deviation,
                "threshold": self.trend_threshold,
                "slope": slope,
            },
        )

    def _detect_luminol_anomaly(
        self, current: float, historical: List[float], timestamps: List[str]
    ) -> Optional[AnomalyScore]:
        """Detect anomaly using Luminol library."""
        if not LUMINOL_AVAILABLE:
            return None

        try:
            # Convert timestamps to epoch
            all_values = historical + [current]
            ts_dict = {}

            for i, ts_str in enumerate(timestamps):
                try:
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts_dict[int(dt.timestamp())] = historical[i]
                except (ValueError, IndexError):
                    ts_dict[i * 86400] = historical[i] if i < len(historical) else current

            # Add current value
            max_ts = max(ts_dict.keys()) if ts_dict else 0
            ts_dict[max_ts + 86400] = current

            # Create time series and detect
            ts = TimeSeries(ts_dict)
            detector = LuminolDetector(ts)
            anomalies = detector.get_anomalies()

            # Check if latest point is anomalous
            latest_ts = max(ts_dict.keys())
            is_anomaly = False
            max_score = 0.0

            for anomaly in anomalies:
                if latest_ts >= anomaly.start_timestamp and latest_ts <= anomaly.end_timestamp:
                    is_anomaly = True
                    max_score = max(max_score, anomaly.anomaly_score)

            # Normalize score to 0-1
            normalized_score = min(1.0, max_score / 100) if max_score > 0 else 0.0

            return AnomalyScore(
                method=DetectionMethod.LUMINOL,
                score=normalized_score,
                is_anomaly=is_anomaly,
                details={
                    "raw_score": max_score,
                    "anomaly_count": len(anomalies),
                    "algorithm": "luminol_bitmap",
                },
            )

        except Exception as e:
            logger.warning(f"Luminol detection failed: {e}")
            return None

    def _calculate_ensemble_score(self, results: List[AnomalyScore]) -> float:
        """Calculate weighted ensemble score from all methods."""
        weights = {
            DetectionMethod.RATIO: 0.2,
            DetectionMethod.STDDEV: 0.3,
            DetectionMethod.TREND: 0.2,
            DetectionMethod.LUMINOL: 0.3,
        }

        total_weight = 0.0
        weighted_score = 0.0

        for result in results:
            weight = weights.get(result.method, 0.0)
            weighted_score += result.score * weight
            total_weight += weight

        return weighted_score / total_weight if total_weight > 0 else 0.0

    def _calculate_severity(self, confidence: float, change_ratio: float) -> str:
        """Calculate severity level based on confidence and change ratio."""
        if confidence >= 0.9 or abs(change_ratio) >= 1.0:
            return "critical"
        elif confidence >= 0.7 or abs(change_ratio) >= 0.5:
            return "high"
        elif confidence >= 0.5 or abs(change_ratio) >= 0.3:
            return "medium"
        else:
            return "low"

    def _generate_analysis(
        self,
        service_name: str,
        current: float,
        previous: float,
        results: List[AnomalyScore],
        is_anomaly: bool,
    ) -> str:
        """Generate human-readable analysis."""
        if not is_anomaly:
            return f"No significant cost anomaly detected for {service_name}."

        change_pct = ((current - previous) / previous * 100) if previous > 0 else 0
        direction = "increase" if change_pct > 0 else "decrease"

        detected = [r.method.value for r in results if r.is_anomaly]
        methods_str = ", ".join(detected)

        return (
            f"Cost anomaly detected for {service_name}: "
            f"{abs(change_pct):.1f}% {direction} "
            f"(${previous:.2f} → ${current:.2f}). "
            f"Detected by: {methods_str}."
        )

    def _create_insufficient_data_result(
        self, service_name: str, current: float, historical: List[float]
    ) -> CostAnomalyResult:
        """Create result for insufficient historical data."""
        previous = historical[-1] if historical else 0.0

        return CostAnomalyResult(
            is_anomaly=False,
            confidence_score=0.0,
            severity="low",
            service_name=service_name,
            current_value=current,
            previous_value=previous,
            change_ratio=0.0,
            detection_results=[],
            detected_methods=[],
            analysis=f"Insufficient data for {service_name} (need {self.min_data_points} points, have {len(historical)})",
            timestamp=datetime.utcnow().isoformat(),
        )
