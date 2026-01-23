"""
Cost Drift Detector with ECOD Algorithm.

ECOD 기반 비용 드리프트 탐지기.
PyOD ECOD 또는 경량 LightweightECOD를 사용하여 이상 탐지 수행.

Features:
- PyOD 설치 시: 고급 ECOD 알고리즘 사용
- PyOD 미설치 시: scipy 의존성 없는 경량 ECOD 구현 (Lambda 최적화)
- Graceful degradation: ratio 기반 fallback 지원
- Pattern-Aware Detection: 요일/추세 패턴 인식으로 False Positive 감소
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

from src.agents.bdp_compact.services.config_loader import (
    DetectionConfig,
    get_detection_config,
)
from src.agents.bdp_compact.services.cost_explorer_provider import ServiceCostData
from src.agents.bdp_compact.services.pattern_recognizers import (
    PatternChain,
    create_default_pattern_chain,
)

logger = logging.getLogger(__name__)

# PyOD graceful degradation
try:
    from pyod.models.ecod import ECOD

    PYOD_AVAILABLE = True
except ImportError:
    PYOD_AVAILABLE = False
    logger.info("PyOD not available, using lightweight ECOD implementation")


def _numpy_skew(x: np.ndarray) -> float:
    """Calculate Fisher-Pearson skewness coefficient (scipy.stats.skew replacement).

    Fisher-Pearson 왜도 계수 계산.
    scipy.stats.skew(bias=True)와 동일한 결과를 반환.

    Args:
        x: 1D numpy array

    Returns:
        Skewness value (0 for symmetric, >0 right-skewed, <0 left-skewed)
    """
    n = len(x)
    if n < 3:
        return 0.0

    mean = np.mean(x)
    std = np.std(x, ddof=0)  # Population std for bias=True

    if std == 0:
        return 0.0

    m3 = np.mean((x - mean) ** 3)
    return m3 / (std**3)


class LightweightECOD:
    """Lightweight ECOD implementation without scipy dependency.

    경량 ECOD (Empirical Cumulative Distribution Functions) 구현.
    scipy 의존성 없이 numpy만으로 ECOD 알고리즘 구현.

    ECOD 알고리즘:
    1. 각 차원의 경험적 CDF (ECDF) 계산
    2. Left-tail / Right-tail 확률 계산
    3. Skewness로 어느 tail을 강조할지 결정
    4. Tail 확률들을 결합하여 이상치 점수 산출

    Reference:
        Li et al., "ECOD: Unsupervised Outlier Detection Using
        Empirical Cumulative Distribution Functions" (2022)

    Usage:
        clf = LightweightECOD(contamination=0.1)
        clf.fit(X)
        labels = clf.labels_  # 0: normal, 1: outlier
        scores = clf.decision_scores_
    """

    def __init__(self, contamination: float = 0.1):
        """Initialize LightweightECOD.

        Args:
            contamination: Expected proportion of outliers in the data (0.0 ~ 0.5)
        """
        if not 0.0 < contamination <= 0.5:
            raise ValueError("contamination must be in (0, 0.5]")

        self.contamination = contamination
        self.labels_: Optional[np.ndarray] = None
        self.decision_scores_: Optional[np.ndarray] = None
        self.threshold_: Optional[float] = None

    def fit(self, X: np.ndarray) -> "LightweightECOD":
        """Fit the ECOD model.

        Args:
            X: Training data of shape (n_samples, n_features)

        Returns:
            self
        """
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        n_samples, n_features = X.shape

        # Calculate outlier scores for each dimension
        scores = np.zeros(n_samples)

        for dim in range(n_features):
            col = X[:, dim]

            # Calculate empirical CDF values
            # Left-tail: P(X <= x)
            left_ecdf = np.array([np.mean(col <= v) for v in col])
            # Right-tail: P(X >= x)
            right_ecdf = np.array([np.mean(col >= v) for v in col])

            # Use skewness to determine which tail to emphasize
            skew = _numpy_skew(col)

            # Add small epsilon to avoid log(0)
            eps = 1e-10

            if skew >= 0:
                # Right-skewed distribution: outliers are in the RIGHT tail (high values)
                # P(X >= x) is small for high outliers → -log(small) is large score
                scores += -np.log(np.clip(right_ecdf, eps, 1.0))
            else:
                # Left-skewed distribution: outliers are in the LEFT tail (low values)
                # P(X <= x) is small for low outliers → -log(small) is large score
                scores += -np.log(np.clip(left_ecdf, eps, 1.0))

        self.decision_scores_ = scores

        # Determine threshold based on contamination
        self.threshold_ = np.percentile(scores, 100 * (1 - self.contamination))

        # Label outliers
        self.labels_ = (scores >= self.threshold_).astype(int)

        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        """Return outlier scores for X.

        Args:
            X: Data of shape (n_samples, n_features)

        Returns:
            Outlier scores for each sample
        """
        if self.decision_scores_ is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        return self.decision_scores_


class Severity(str, Enum):
    """이상 탐지 심각도 레벨."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class CostDriftResult:
    """비용 드리프트 탐지 결과."""

    is_anomaly: bool
    confidence_score: float  # 0.0 - 1.0 (패턴 조정 후)
    severity: Severity
    service_name: str
    account_id: str
    account_name: str
    current_cost: float
    historical_average: float
    change_percent: float
    spike_duration_days: int  # 연속 상승일
    trend_direction: str  # increasing, decreasing, stable
    spike_start_date: Optional[str] = None
    detection_method: str = "ecod"
    raw_score: float = 0.0
    # Pattern-Aware Detection fields
    raw_confidence_score: Optional[float] = None  # 패턴 조정 전 원본 신뢰도
    pattern_contexts: List[str] = field(default_factory=list)  # 인식된 패턴 설명
    # Optional: full historical data for chart generation
    historical_costs: Optional[List[float]] = None
    timestamps: Optional[List[str]] = None


class CostDriftDetector:
    """
    ECOD 기반 Cost Drift 탐지기.

    ECOD (Empirical Cumulative Distribution Functions) 특징:
    - Parameter-free: 하이퍼파라미터 튜닝 불필요
    - Fast training/inference
    - 다변량 이상 탐지에 효과적
    - Python 3.11+ 지원

    구현 방식:
    - PyOD 설치 시: pyod.models.ecod.ECOD 사용 (detection_method: "ecod")
    - PyOD 미설치 시: LightweightECOD 사용 (detection_method: "ecod_lite")
    - 앙상블 탐지 시: "ensemble" 또는 "ensemble_lite"

    Pattern-Aware Detection:
    - 요일 패턴, 추세 패턴 인식으로 False Positive 감소
    - 패턴 인식 결과에 따라 신뢰도 조정

    Usage:
        detector = CostDriftDetector(sensitivity=0.7)
        result = detector.analyze_service(service_data)
        results = detector.analyze_batch(all_service_data)
    """

    def __init__(
        self,
        sensitivity: float = 0.7,
        min_data_points: int = 7,
        ratio_threshold: float = 1.5,
        contamination: float = 0.1,
        pattern_recognition_enabled: Optional[bool] = None,
    ):
        """탐지기 초기화.

        Args:
            sensitivity: 탐지 민감도 (0.0-1.0), 높을수록 민감
            min_data_points: 최소 필요 데이터 포인트 수
            ratio_threshold: Ratio 기반 탐지 임계값 (배수)
            contamination: ECOD 이상치 비율 추정값
            pattern_recognition_enabled: 패턴 인식 활성화 (None이면 환경 변수 사용)
        """
        self.sensitivity = sensitivity
        self.min_data_points = min_data_points
        self.ratio_threshold = ratio_threshold
        self.contamination = contamination

        # 민감도 기반 임계값 조정
        self.confidence_threshold = 0.6 - (sensitivity * 0.1)  # 0.5 ~ 0.6

        # Pattern-Aware Detection
        self.pattern_chain = create_default_pattern_chain(
            enabled=pattern_recognition_enabled
        )

        # Shadow mode check
        self.pattern_shadow_mode = os.getenv("BDP_PATTERN_MODE", "active") == "shadow"
        if self.pattern_chain and self.pattern_shadow_mode:
            logger.info("Pattern recognition running in shadow mode")

    def analyze_service(self, service_data: ServiceCostData) -> CostDriftResult:
        """단일 서비스의 비용 드리프트 분석.

        Args:
            service_data: 서비스 비용 데이터

        Returns:
            CostDriftResult 탐지 결과
        """
        historical = service_data.historical_costs
        timestamps = service_data.timestamps

        if len(historical) < self.min_data_points:
            return self._insufficient_data_result(service_data)

        # 개별 탐지 방법 실행
        ecod_result = self._detect_ecod(historical)
        ratio_result = self._detect_ratio(historical)
        stddev_result = self._detect_stddev(historical)

        # 앙상블 스코어 계산
        ensemble_result = self._calculate_ensemble_score(
            ecod_result, ratio_result, stddev_result
        )

        is_anomaly = ensemble_result["is_anomaly"]
        raw_confidence = ensemble_result["confidence"]
        raw_score = ensemble_result["raw_score"]
        detection_method = ensemble_result["method"] + ensemble_result["method_suffix"]

        # 트렌드 분석
        trend_direction = self._analyze_trend(historical)
        spike_duration, spike_start_idx = self._calculate_spike_duration(historical)
        spike_start_date = (
            timestamps[spike_start_idx] if spike_start_idx is not None else None
        )

        # 통계
        historical_avg = np.mean(historical[:-1]) if len(historical) > 1 else historical[0]
        current_cost = service_data.current_cost
        change_percent = (
            ((current_cost - historical_avg) / historical_avg * 100)
            if historical_avg > 0
            else 0
        )

        # Pattern-Aware Detection: 패턴 인식 기반 신뢰도 조정
        adjusted_confidence = raw_confidence
        pattern_explanations: List[str] = []

        if self.pattern_chain:
            adjustment = self.pattern_chain.get_total_adjustment(service_data)
            pattern_explanations = self.pattern_chain.get_explanations(service_data)

            if self.pattern_shadow_mode:
                # Shadow mode: 로그만 기록, 실제 조정하지 않음
                logger.info(
                    f"[Shadow] Pattern adjustment for {service_data.service_name}: "
                    f"raw={raw_confidence:.3f}, adjustment={adjustment:.3f}, "
                    f"patterns={pattern_explanations}"
                )
            else:
                # Active mode: 실제 조정 적용
                adjusted_confidence = max(0.0, raw_confidence + adjustment)
                if adjustment != 0:
                    logger.debug(
                        f"Pattern adjustment for {service_data.service_name}: "
                        f"raw={raw_confidence:.3f} -> adjusted={adjusted_confidence:.3f}, "
                        f"patterns={pattern_explanations}"
                    )

        # 조정된 신뢰도로 최종 anomaly 판정
        final_is_anomaly = is_anomaly and adjusted_confidence >= self.confidence_threshold

        severity = self._calculate_severity(adjusted_confidence, change_percent)

        return CostDriftResult(
            is_anomaly=final_is_anomaly,
            confidence_score=round(adjusted_confidence, 3),
            severity=severity,
            service_name=service_data.service_name,
            account_id=service_data.account_id,
            account_name=service_data.account_name,
            current_cost=current_cost,
            historical_average=round(historical_avg, 2),
            change_percent=round(change_percent, 1),
            spike_duration_days=spike_duration,
            trend_direction=trend_direction,
            spike_start_date=spike_start_date,
            detection_method=detection_method,
            raw_score=round(raw_score, 4),
            raw_confidence_score=round(raw_confidence, 3),
            pattern_contexts=pattern_explanations,
            historical_costs=historical,
            timestamps=timestamps,
        )

    def analyze_batch(
        self, cost_data: Dict[str, List[ServiceCostData]]
    ) -> List[CostDriftResult]:
        """여러 계정의 모든 서비스 일괄 분석.

        Args:
            cost_data: account_id -> List[ServiceCostData] 매핑

        Returns:
            모든 서비스의 CostDriftResult 목록 (신뢰도 내림차순)
        """
        results = []

        for account_id, services in cost_data.items():
            for service_data in services:
                result = self.analyze_service(service_data)
                results.append(result)

        # 신뢰도 내림차순 정렬
        results.sort(key=lambda r: r.confidence_score, reverse=True)
        return results

    def _detect_ecod(self, costs: List[float]) -> Optional[Dict[str, Any]]:
        """ECOD 기반 이상 탐지 (PyOD 또는 경량 버전 사용).

        PyOD가 설치된 경우 PyOD ECOD를 사용하고,
        그렇지 않은 경우 경량 LightweightECOD를 사용.

        Args:
            costs: 비용 시계열 데이터

        Returns:
            탐지 결과 dict 또는 None (탐지 실패시)
        """
        try:
            # 데이터 준비 (2D array 필요)
            X = np.array(costs).reshape(-1, 1)

            # PyOD 사용 가능하면 PyOD, 아니면 경량 버전
            if PYOD_AVAILABLE:
                clf = ECOD(contamination=self.contamination)
                method_suffix = ""
            else:
                clf = LightweightECOD(contamination=self.contamination)
                method_suffix = "_lite"

            clf.fit(X)

            # 마지막 포인트(현재)의 이상 여부 확인
            labels = clf.labels_
            scores = clf.decision_scores_

            is_anomaly = bool(labels[-1] == 1)
            raw_score = float(scores[-1])

            # 점수 정규화 (0-1 범위)
            score_range = scores.max() - scores.min()
            if score_range > 0:
                normalized_score = (raw_score - scores.min()) / score_range
            else:
                normalized_score = 0.0

            # 민감도 적용
            confidence = min(1.0, normalized_score * (1 + self.sensitivity * 0.5))

            return {
                "is_anomaly": is_anomaly or confidence >= self.confidence_threshold,
                "confidence": confidence,
                "raw_score": raw_score,
                "method_suffix": method_suffix,
            }

        except Exception as e:
            logger.warning(f"ECOD detection failed: {e}")
            return None

    def _detect_ratio(self, costs: List[float]) -> Dict[str, Any]:
        """Ratio 기반 이상 탐지 (fallback).

        Args:
            costs: 비용 시계열 데이터

        Returns:
            탐지 결과 dict
        """
        if len(costs) < 2:
            return {"is_anomaly": False, "confidence": 0.0, "ratio": 0.0}

        current = costs[-1]
        historical = costs[:-1]
        avg = np.mean(historical)

        if avg <= 0:
            return {"is_anomaly": False, "confidence": 0.0, "ratio": 0.0}

        ratio = current / avg

        # 임계값 초과 여부
        is_anomaly = ratio > self.ratio_threshold or ratio < (1 / self.ratio_threshold)

        # 신뢰도 계산
        if ratio > 1:
            confidence = min(1.0, (ratio - 1) / self.ratio_threshold)
        else:
            confidence = min(1.0, (1 / ratio - 1) / self.ratio_threshold)

        return {
            "is_anomaly": is_anomaly,
            "confidence": confidence * self.sensitivity,
            "ratio": ratio,
        }

    def _detect_stddev(self, costs: List[float]) -> Optional[Dict[str, Any]]:
        """Z-Score (표준편차) 기반 이상 탐지.

        Args:
            costs: 비용 시계열 데이터

        Returns:
            탐지 결과 dict 또는 None (탐지 실패시)
        """
        config = get_detection_config()
        min_points = config.stddev.min_data_points
        z_threshold = config.stddev.z_score_threshold

        if len(costs) < min_points:
            return None

        try:
            current = costs[-1]
            historical = np.array(costs[:-1])

            mean = np.mean(historical)
            std = np.std(historical, ddof=1)  # Sample std

            if std == 0:
                return None

            z_score = (current - mean) / std
            abs_z = abs(z_score)

            # Threshold adjusted by sensitivity (2.0 ~ 3.0 range)
            adjusted_threshold = z_threshold - self.sensitivity

            is_anomaly = abs_z > adjusted_threshold

            # Confidence: min(1.0, abs(z_score) / 4.0) * sensitivity
            confidence = min(1.0, abs_z / 4.0) * self.sensitivity

            return {
                "is_anomaly": is_anomaly,
                "confidence": confidence,
                "z_score": z_score,
                "mean": mean,
                "std": std,
            }

        except Exception as e:
            logger.warning(f"Stddev detection failed: {e}")
            return None

    def _calculate_ensemble_score(
        self,
        ecod_result: Optional[Dict[str, Any]],
        ratio_result: Dict[str, Any],
        stddev_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """가중치 기반 앙상블 스코어 계산.

        Args:
            ecod_result: ECOD 탐지 결과
            ratio_result: Ratio 탐지 결과
            stddev_result: Stddev 탐지 결과

        Returns:
            앙상블 결과 dict (is_anomaly, confidence, method)
        """
        config = get_detection_config()
        weights = config.ensemble

        # Collect valid results
        valid_results = []
        total_weight = 0.0

        if ecod_result:
            valid_results.append((ecod_result, weights.ecod_weight, "ecod"))
            total_weight += weights.ecod_weight

        if ratio_result:
            valid_results.append((ratio_result, weights.ratio_weight, "ratio"))
            total_weight += weights.ratio_weight

        if stddev_result:
            valid_results.append((stddev_result, weights.stddev_weight, "stddev"))
            total_weight += weights.stddev_weight

        if total_weight == 0 or not valid_results:
            return {
                "is_anomaly": False,
                "confidence": 0.0,
                "raw_score": 0.0,
                "method": "insufficient_data",
                "method_suffix": "",
            }

        # Normalize weights
        normalized_weights = [(r, w / total_weight, m) for r, w, m in valid_results]

        # Calculate weighted confidence
        weighted_confidence = sum(
            r["confidence"] * w for r, w, _ in normalized_weights
        )

        # Count anomaly votes (weighted)
        anomaly_vote_weight = sum(
            w for r, w, _ in normalized_weights if r.get("is_anomaly", False)
        )

        # Anomaly if majority of weight votes anomaly
        is_anomaly = anomaly_vote_weight > 0.5

        # Determine primary method and suffix
        if ecod_result:
            method_suffix = ecod_result.get("method_suffix", "")
            if len([r for r, _, _ in normalized_weights if r.get("is_anomaly")]) >= 2:
                method = "ensemble"
            else:
                method = "ecod"
        elif stddev_result and stddev_result.get("is_anomaly"):
            method = "stddev"
            method_suffix = ""
        else:
            method = "ratio"
            method_suffix = ""

        # Raw score: use max score from available methods
        raw_scores = []
        if ecod_result:
            raw_scores.append(ecod_result.get("raw_score", 0))
        if ratio_result:
            raw_scores.append(ratio_result.get("ratio", 0))
        if stddev_result:
            raw_scores.append(abs(stddev_result.get("z_score", 0)))

        raw_score = max(raw_scores) if raw_scores else 0.0

        return {
            "is_anomaly": is_anomaly,
            "confidence": weighted_confidence,
            "raw_score": raw_score,
            "method": method,
            "method_suffix": method_suffix,
        }

    def _analyze_trend(self, costs: List[float]) -> str:
        """트렌드 방향 분석.

        Args:
            costs: 비용 시계열

        Returns:
            'increasing', 'decreasing', 'stable' 중 하나
        """
        if len(costs) < 3:
            return "stable"

        # 선형 회귀로 기울기 계산
        x = np.arange(len(costs))
        slope = np.polyfit(x, costs, 1)[0]

        # 평균 대비 기울기 비율
        avg = np.mean(costs)
        if avg == 0:
            return "stable"

        slope_ratio = slope / avg

        if slope_ratio > 0.05:
            return "increasing"
        elif slope_ratio < -0.05:
            return "decreasing"
        else:
            return "stable"

    def _calculate_spike_duration(
        self, costs: List[float]
    ) -> tuple[int, Optional[int]]:
        """연속 상승일 계산.

        Args:
            costs: 비용 시계열

        Returns:
            (연속 상승일, 상승 시작 인덱스)
        """
        if len(costs) < 2:
            return 0, None

        avg = np.mean(costs[:-1])
        threshold = avg * 1.2  # 20% 이상 상승을 spike로 간주

        # 뒤에서부터 연속으로 threshold 초과하는 일수 계산
        duration = 0
        start_idx = None

        for i in range(len(costs) - 1, -1, -1):
            if costs[i] > threshold:
                duration += 1
                start_idx = i
            else:
                break

        return duration, start_idx

    def _calculate_severity(self, confidence: float, change_percent: float) -> Severity:
        """심각도 레벨 계산.

        Args:
            confidence: 신뢰도 점수
            change_percent: 변화율 (%)

        Returns:
            Severity 레벨
        """
        abs_change = abs(change_percent)

        if confidence >= 0.9 or abs_change >= 200:
            return Severity.CRITICAL
        elif confidence >= 0.7 or abs_change >= 100:
            return Severity.HIGH
        elif confidence >= 0.5 or abs_change >= 50:
            return Severity.MEDIUM
        else:
            return Severity.LOW

    def _insufficient_data_result(self, service_data: ServiceCostData) -> CostDriftResult:
        """데이터 부족시 결과 생성."""
        return CostDriftResult(
            is_anomaly=False,
            confidence_score=0.0,
            severity=Severity.LOW,
            service_name=service_data.service_name,
            account_id=service_data.account_id,
            account_name=service_data.account_name,
            current_cost=service_data.current_cost,
            historical_average=0.0,
            change_percent=0.0,
            spike_duration_days=0,
            trend_direction="stable",
            detection_method="insufficient_data",
            raw_confidence_score=0.0,
            pattern_contexts=[],
            historical_costs=service_data.historical_costs,
            timestamps=service_data.timestamps,
        )
