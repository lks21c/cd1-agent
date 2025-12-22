"""
Cost Anomaly Detector for CD1 Agent.

복합 이상 탐지 알고리즘:
1. 비율 기반 (RATIO): 전 기간 대비 X% 이상 증가
2. 표준편차 기반 (STDDEV): 최근 N일 평균에서 2σ 이상
3. 추세 분석 (TREND): 연속 N일 이상 증가 패턴
4. Luminol (LUMINOL): LinkedIn의 시계열 이상 탐지 라이브러리

복합 점수: 가중치 기반 종합 신뢰도 계산

Root Cause Analysis:
- Luminol Correlator를 사용한 메트릭 간 상관관계 분석
- CloudWatch 메트릭과의 상관관계로 원인 추적
"""
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import structlog

# Luminol imports (with graceful fallback)
try:
    from luminol.anomaly_detector import AnomalyDetector as LuminolDetector
    from luminol.correlator import Correlator as LuminolCorrelator
    LUMINOL_AVAILABLE = True
except ImportError:
    LUMINOL_AVAILABLE = False
    LuminolDetector = None
    LuminolCorrelator = None

logger = structlog.get_logger()


class AnomalyType(str, Enum):
    """이상 유형."""
    RATIO = "ratio"           # 급격한 증가/감소
    STDDEV = "stddev"         # 표준편차 기반 이상
    TREND = "trend"           # 지속적 증가 추세
    LUMINOL = "luminol"       # Luminol 라이브러리 기반 탐지
    COMBINED = "combined"     # 복합 이상


class Severity(str, Enum):
    """심각도 레벨."""
    HIGH = "high"       # 0.8 이상
    MEDIUM = "medium"   # 0.5 ~ 0.8
    LOW = "low"         # 0.5 미만


@dataclass
class AnomalyThresholds:
    """이상 탐지 임계값 설정."""

    # 비율 기반 임계값
    ratio_threshold: float = 0.5        # 50% 이상 증가
    ratio_decrease_threshold: float = 0.3  # 30% 이상 감소

    # 표준편차 기반 임계값
    stddev_multiplier: float = 2.0      # 2 시그마

    # 추세 분석 임계값
    trend_consecutive_days: int = 3     # 연속 3일 이상 증가
    trend_min_increase_rate: float = 0.05  # 일 5% 이상 증가

    # Luminol 임계값
    luminol_score_threshold: float = 2.0  # Luminol anomaly score 임계값
    luminol_algorithm: str = "default_detector"  # bitmap_detector, derivative_detector, exp_avg_detector

    # 가중치 (Luminol 포함 시 재분배)
    ratio_weight: float = 0.30
    stddev_weight: float = 0.25
    trend_weight: float = 0.20
    luminol_weight: float = 0.25        # Luminol 가중치 추가

    # Luminol 비활성화 시 가중치 (원래 가중치로 복원)
    ratio_weight_no_luminol: float = 0.40
    stddev_weight_no_luminol: float = 0.35
    trend_weight_no_luminol: float = 0.25

    # 심각도 임계값
    severity_high_threshold: float = 0.8
    severity_medium_threshold: float = 0.5

    # 최소 데이터 요구 사항
    min_data_points: int = 7            # 최소 7일 데이터

    # Root Cause Correlation
    correlation_threshold: float = 0.7  # 상관계수 임계값
    max_correlation_shift: int = 3      # 최대 시간 이동 (일)


@dataclass
class DetectionResult:
    """개별 탐지 결과."""
    detected: bool
    score: float
    anomaly_type: AnomalyType
    details: Dict[str, any] = field(default_factory=dict)


@dataclass
class CorrelationResult:
    """메트릭 상관관계 결과."""
    metric_name: str
    coefficient: float
    shift: int  # 시간 이동 (양수: 해당 메트릭이 뒤처짐, 음수: 앞섬)
    is_likely_cause: bool  # shift가 음수면 원인일 가능성


@dataclass
class AnomalyResult:
    """이상 탐지 종합 결과."""
    is_anomaly: bool
    confidence_score: float
    severity: Severity
    service_name: str
    current_cost: float
    previous_cost: float
    cost_change_ratio: float
    detection_results: List[DetectionResult]
    detected_methods: List[str]
    analysis: str
    date: str
    # Luminol 추가 필드
    anomaly_window: Optional[Tuple[int, int]] = None  # (start, end) timestamp
    correlated_metrics: List[CorrelationResult] = field(default_factory=list)


class CostAnomalyDetector:
    """비용 이상 탐지 엔진."""

    def __init__(
        self,
        thresholds: Optional[AnomalyThresholds] = None,
        use_luminol: bool = True
    ):
        """
        초기화.

        Args:
            thresholds: 이상 탐지 임계값 설정
            use_luminol: Luminol 라이브러리 사용 여부 (기본: True)
        """
        self.thresholds = thresholds or AnomalyThresholds()
        self.use_luminol = use_luminol and LUMINOL_AVAILABLE
        self.logger = logger.bind(service="cost_anomaly_detector")

        if use_luminol and not LUMINOL_AVAILABLE:
            self.logger.warning(
                "luminol_not_available",
                message="Luminol is not installed. Falling back to basic detection."
            )

    def detect_anomaly(
        self,
        service_name: str,
        costs_by_date: Dict[str, float],
        target_date: Optional[str] = None
    ) -> Optional[AnomalyResult]:
        """
        특정 서비스의 비용 이상 탐지.

        Args:
            service_name: 서비스 이름
            costs_by_date: 날짜별 비용 딕셔너리 (정렬된 순서)
            target_date: 분석 대상 날짜 (None이면 최근 날짜)

        Returns:
            AnomalyResult 또는 None (데이터 부족 시)
        """
        sorted_dates = sorted(costs_by_date.keys())
        costs = [costs_by_date[d] for d in sorted_dates]

        if len(costs) < self.thresholds.min_data_points:
            self.logger.warning(
                "insufficient_data",
                service=service_name,
                data_points=len(costs),
                required=self.thresholds.min_data_points
            )
            return None

        if target_date is None:
            target_date = sorted_dates[-1]

        target_idx = sorted_dates.index(target_date) if target_date in sorted_dates else -1
        if target_idx < 0:
            target_idx = len(costs) - 1
            target_date = sorted_dates[-1]

        current_cost = costs[target_idx]
        previous_cost = costs[target_idx - 1] if target_idx > 0 else costs[0]

        # 각 방법으로 이상 탐지
        ratio_result = self._detect_ratio_anomaly(costs, target_idx)
        stddev_result = self._detect_stddev_anomaly(costs, target_idx)
        trend_result = self._detect_trend_anomaly(costs, target_idx)

        detection_results = [ratio_result, stddev_result, trend_result]

        # Luminol 탐지 (활성화된 경우)
        luminol_result = None
        anomaly_window = None
        if self.use_luminol:
            luminol_result, anomaly_window = self._detect_luminol_anomaly(
                costs_by_date, target_date
            )
            if luminol_result:
                detection_results.append(luminol_result)

        # 복합 점수 계산
        combined_score = self._calculate_combined_score(
            ratio_result.score,
            stddev_result.score,
            trend_result.score,
            luminol_result.score if luminol_result else 0.0
        )

        # 탐지된 방법들
        detected_methods = [
            r.anomaly_type.value for r in detection_results if r.detected
        ]

        # 이상 여부 판정: 2개 이상 방법에서 탐지 또는 confidence > 0.6
        is_anomaly = len(detected_methods) >= 2 or combined_score > 0.6

        # 심각도 결정
        severity = self._determine_severity(combined_score)

        # 분석 텍스트 생성
        analysis = self._generate_analysis(
            service_name=service_name,
            current_cost=current_cost,
            previous_cost=previous_cost,
            detection_results=detection_results,
            combined_score=combined_score
        )

        # 비용 변화율 계산
        if previous_cost > 0:
            cost_change_ratio = (current_cost - previous_cost) / previous_cost
        else:
            cost_change_ratio = 1.0 if current_cost > 0 else 0.0

        return AnomalyResult(
            is_anomaly=is_anomaly,
            confidence_score=combined_score,
            severity=severity,
            service_name=service_name,
            current_cost=current_cost,
            previous_cost=previous_cost,
            cost_change_ratio=cost_change_ratio,
            detection_results=detection_results,
            detected_methods=detected_methods,
            analysis=analysis,
            date=target_date,
            anomaly_window=anomaly_window
        )

    def detect_all_services(
        self,
        costs_data: Dict[str, Dict[str, float]],
        target_date: Optional[str] = None
    ) -> List[AnomalyResult]:
        """
        모든 서비스에 대해 이상 탐지 수행.

        Args:
            costs_data: {service_name: {date: cost}} 형태의 데이터
            target_date: 분석 대상 날짜

        Returns:
            이상이 탐지된 결과 목록 (심각도 순 정렬)
        """
        results = []

        for service_name, costs_by_date in costs_data.items():
            result = self.detect_anomaly(
                service_name=service_name,
                costs_by_date=costs_by_date,
                target_date=target_date
            )
            if result and result.is_anomaly:
                results.append(result)

        # 심각도 및 신뢰도 순 정렬
        severity_order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
        results.sort(key=lambda x: (severity_order[x.severity], -x.confidence_score))

        self.logger.info(
            "anomaly_detection_complete",
            total_services=len(costs_data),
            anomalies_found=len(results)
        )

        return results

    def _detect_ratio_anomaly(
        self,
        costs: List[float],
        target_idx: int
    ) -> DetectionResult:
        """비율 기반 이상 탐지."""
        current = costs[target_idx]
        previous = costs[target_idx - 1] if target_idx > 0 else costs[0]

        if previous <= 0:
            return DetectionResult(
                detected=current > 0,
                score=0.5 if current > 0 else 0.0,
                anomaly_type=AnomalyType.RATIO,
                details={"reason": "previous_cost_zero", "current": current}
            )

        ratio = (current - previous) / previous

        # 증가 이상
        if ratio >= self.thresholds.ratio_threshold:
            # 점수 계산: ratio가 threshold의 2배면 1.0
            score = min(1.0, ratio / (self.thresholds.ratio_threshold * 2))
            return DetectionResult(
                detected=True,
                score=score,
                anomaly_type=AnomalyType.RATIO,
                details={
                    "change_ratio": ratio,
                    "threshold": self.thresholds.ratio_threshold,
                    "direction": "increase"
                }
            )

        # 감소 이상
        if ratio <= -self.thresholds.ratio_decrease_threshold:
            score = min(1.0, abs(ratio) / (self.thresholds.ratio_decrease_threshold * 2))
            return DetectionResult(
                detected=True,
                score=score,
                anomaly_type=AnomalyType.RATIO,
                details={
                    "change_ratio": ratio,
                    "threshold": -self.thresholds.ratio_decrease_threshold,
                    "direction": "decrease"
                }
            )

        return DetectionResult(
            detected=False,
            score=0.0,
            anomaly_type=AnomalyType.RATIO,
            details={"change_ratio": ratio}
        )

    def _detect_stddev_anomaly(
        self,
        costs: List[float],
        target_idx: int
    ) -> DetectionResult:
        """표준편차 기반 이상 탐지."""
        # 대상 날짜 이전 데이터로 통계 계산
        historical_costs = costs[:target_idx] if target_idx > 0 else costs[:-1]

        if len(historical_costs) < 3:
            return DetectionResult(
                detected=False,
                score=0.0,
                anomaly_type=AnomalyType.STDDEV,
                details={"reason": "insufficient_historical_data"}
            )

        mean = statistics.mean(historical_costs)
        stdev = statistics.stdev(historical_costs) if len(historical_costs) > 1 else 0

        if stdev == 0:
            return DetectionResult(
                detected=False,
                score=0.0,
                anomaly_type=AnomalyType.STDDEV,
                details={"reason": "zero_stdev", "mean": mean}
            )

        current = costs[target_idx]
        z_score = (current - mean) / stdev

        threshold = self.thresholds.stddev_multiplier

        if abs(z_score) >= threshold:
            # 점수: z_score가 threshold의 2배면 1.0
            score = min(1.0, abs(z_score) / (threshold * 2))
            return DetectionResult(
                detected=True,
                score=score,
                anomaly_type=AnomalyType.STDDEV,
                details={
                    "z_score": z_score,
                    "mean": mean,
                    "stdev": stdev,
                    "threshold": threshold,
                    "direction": "above" if z_score > 0 else "below"
                }
            )

        return DetectionResult(
            detected=False,
            score=0.0,
            anomaly_type=AnomalyType.STDDEV,
            details={"z_score": z_score, "mean": mean, "stdev": stdev}
        )

    def _detect_trend_anomaly(
        self,
        costs: List[float],
        target_idx: int
    ) -> DetectionResult:
        """추세 분석 기반 이상 탐지."""
        required_days = self.thresholds.trend_consecutive_days
        min_rate = self.thresholds.trend_min_increase_rate

        if target_idx < required_days:
            return DetectionResult(
                detected=False,
                score=0.0,
                anomaly_type=AnomalyType.TREND,
                details={"reason": "insufficient_data_for_trend"}
            )

        # 최근 N일 연속 증가 패턴 확인
        consecutive_increases = 0
        increase_rates = []

        for i in range(target_idx, max(0, target_idx - required_days), -1):
            if i == 0:
                break

            current = costs[i]
            previous = costs[i - 1]

            if previous > 0:
                rate = (current - previous) / previous
                if rate >= min_rate:
                    consecutive_increases += 1
                    increase_rates.append(rate)
                else:
                    break
            else:
                break

        if consecutive_increases >= required_days:
            avg_rate = sum(increase_rates) / len(increase_rates) if increase_rates else 0
            # 점수: 연속 일수와 평균 증가율 기반
            days_factor = min(1.0, consecutive_increases / (required_days * 2))
            rate_factor = min(1.0, avg_rate / (min_rate * 3))
            score = (days_factor + rate_factor) / 2

            return DetectionResult(
                detected=True,
                score=score,
                anomaly_type=AnomalyType.TREND,
                details={
                    "consecutive_days": consecutive_increases,
                    "average_increase_rate": avg_rate,
                    "increase_rates": increase_rates
                }
            )

        return DetectionResult(
            detected=False,
            score=0.0,
            anomaly_type=AnomalyType.TREND,
            details={
                "consecutive_days": consecutive_increases,
                "required_days": required_days
            }
        )

    def _detect_luminol_anomaly(
        self,
        costs_by_date: Dict[str, float],
        target_date: str
    ) -> Tuple[Optional[DetectionResult], Optional[Tuple[int, int]]]:
        """
        Luminol 라이브러리를 사용한 이상 탐지.

        Args:
            costs_by_date: 날짜별 비용 딕셔너리
            target_date: 분석 대상 날짜

        Returns:
            (DetectionResult, anomaly_window) 튜플
        """
        if not LUMINOL_AVAILABLE or LuminolDetector is None:
            return None, None

        try:
            # 날짜를 타임스탬프 인덱스로 변환
            sorted_dates = sorted(costs_by_date.keys())
            ts_data = {i: costs_by_date[d] for i, d in enumerate(sorted_dates)}

            # Luminol 탐지기 실행
            detector = LuminolDetector(
                ts_data,
                algorithm_name=self.thresholds.luminol_algorithm
            )

            anomalies = detector.get_anomalies()

            if not anomalies:
                return DetectionResult(
                    detected=False,
                    score=0.0,
                    anomaly_type=AnomalyType.LUMINOL,
                    details={"message": "No anomalies detected by Luminol"}
                ), None

            # target_date에 해당하는 이상 현상 찾기
            target_idx = sorted_dates.index(target_date) if target_date in sorted_dates else -1

            relevant_anomaly = None
            for anomaly in anomalies:
                if anomaly.start_timestamp <= target_idx <= anomaly.end_timestamp:
                    relevant_anomaly = anomaly
                    break
                # 가장 가까운 이상도 고려
                if relevant_anomaly is None or \
                   abs(anomaly.exact_timestamp - target_idx) < abs(relevant_anomaly.exact_timestamp - target_idx):
                    relevant_anomaly = anomaly

            if relevant_anomaly is None:
                return DetectionResult(
                    detected=False,
                    score=0.0,
                    anomaly_type=AnomalyType.LUMINOL,
                    details={"total_anomalies": len(anomalies)}
                ), None

            # 점수 정규화 (Luminol score는 0-10+ 범위)
            normalized_score = min(1.0, relevant_anomaly.anomaly_score / 10.0)

            # 임계값 확인
            detected = relevant_anomaly.anomaly_score >= self.thresholds.luminol_score_threshold

            anomaly_window = (
                int(relevant_anomaly.start_timestamp),
                int(relevant_anomaly.end_timestamp)
            )

            # 날짜로 변환
            start_date = sorted_dates[anomaly_window[0]] if anomaly_window[0] < len(sorted_dates) else "N/A"
            end_date = sorted_dates[anomaly_window[1]] if anomaly_window[1] < len(sorted_dates) else "N/A"

            return DetectionResult(
                detected=detected,
                score=normalized_score if detected else normalized_score * 0.5,
                anomaly_type=AnomalyType.LUMINOL,
                details={
                    "luminol_score": relevant_anomaly.anomaly_score,
                    "exact_timestamp": relevant_anomaly.exact_timestamp,
                    "window_start": start_date,
                    "window_end": end_date,
                    "total_anomalies": len(anomalies)
                }
            ), anomaly_window

        except Exception as e:
            self.logger.error("luminol_detection_error", error=str(e))
            return DetectionResult(
                detected=False,
                score=0.0,
                anomaly_type=AnomalyType.LUMINOL,
                details={"error": str(e)}
            ), None

    def _calculate_combined_score(
        self,
        ratio_score: float,
        stddev_score: float,
        trend_score: float,
        luminol_score: float = 0.0
    ) -> float:
        """복합 신뢰도 점수 계산."""
        if self.use_luminol and luminol_score > 0:
            # Luminol 포함 가중치
            score = (
                ratio_score * self.thresholds.ratio_weight +
                stddev_score * self.thresholds.stddev_weight +
                trend_score * self.thresholds.trend_weight +
                luminol_score * self.thresholds.luminol_weight
            )
        else:
            # Luminol 없이 기존 가중치
            score = (
                ratio_score * self.thresholds.ratio_weight_no_luminol +
                stddev_score * self.thresholds.stddev_weight_no_luminol +
                trend_score * self.thresholds.trend_weight_no_luminol
            )
        return round(min(1.0, max(0.0, score)), 3)

    def _determine_severity(self, score: float) -> Severity:
        """심각도 결정."""
        if score >= self.thresholds.severity_high_threshold:
            return Severity.HIGH
        elif score >= self.thresholds.severity_medium_threshold:
            return Severity.MEDIUM
        else:
            return Severity.LOW

    def correlate_with_metrics(
        self,
        cost_ts: Dict[str, float],
        related_metrics: Dict[str, Dict[str, float]]
    ) -> List[CorrelationResult]:
        """
        비용 시계열과 관련 메트릭 간의 상관관계 분석.

        Luminol Correlator를 사용하여 비용 변화의 잠재적 원인을 추적합니다.
        시간 이동(shift)이 음수인 메트릭은 비용 변화 이전에 발생했으므로
        원인일 가능성이 높습니다.

        Args:
            cost_ts: 비용 시계열 {date: cost}
            related_metrics: 관련 메트릭 {metric_name: {date: value}}
                예: {"CPUUtilization": {...}, "RequestCount": {...}}

        Returns:
            상관관계 결과 목록 (상관계수 높은 순 정렬)
        """
        if not LUMINOL_AVAILABLE or LuminolCorrelator is None:
            self.logger.warning(
                "correlator_unavailable",
                message="Luminol Correlator not available"
            )
            return []

        results = []

        try:
            # 비용 데이터를 타임스탬프 기반으로 변환
            sorted_dates = sorted(cost_ts.keys())
            cost_ts_indexed = {i: cost_ts[d] for i, d in enumerate(sorted_dates)}

            for metric_name, metric_ts in related_metrics.items():
                try:
                    # 메트릭 데이터도 동일한 날짜 기준으로 변환
                    metric_ts_indexed = {}
                    for i, d in enumerate(sorted_dates):
                        if d in metric_ts:
                            metric_ts_indexed[i] = metric_ts[d]

                    if len(metric_ts_indexed) < self.thresholds.min_data_points:
                        self.logger.debug(
                            "skipping_metric_insufficient_data",
                            metric=metric_name,
                            data_points=len(metric_ts_indexed)
                        )
                        continue

                    # Luminol Correlator 실행
                    correlator = LuminolCorrelator(
                        cost_ts_indexed,
                        metric_ts_indexed,
                        max_shift_seconds=self.thresholds.max_correlation_shift
                    )

                    correlation = correlator.correlation_result
                    coefficient = correlation.coefficient
                    shift = correlation.shift

                    # 유의미한 상관관계만 포함
                    if abs(coefficient) >= self.thresholds.correlation_threshold:
                        is_likely_cause = shift < 0  # 음수 shift = 해당 메트릭이 앞섬

                        results.append(CorrelationResult(
                            metric_name=metric_name,
                            coefficient=round(coefficient, 3),
                            shift=shift,
                            is_likely_cause=is_likely_cause
                        ))

                        self.logger.debug(
                            "correlation_found",
                            metric=metric_name,
                            coefficient=coefficient,
                            shift=shift,
                            is_likely_cause=is_likely_cause
                        )

                except Exception as e:
                    self.logger.warning(
                        "metric_correlation_error",
                        metric=metric_name,
                        error=str(e)
                    )
                    continue

            # 상관계수 절댓값 기준 정렬, 원인 가능성 있는 것 우선
            results.sort(key=lambda x: (-x.is_likely_cause, -abs(x.coefficient)))

            self.logger.info(
                "correlation_analysis_complete",
                total_metrics=len(related_metrics),
                correlated_metrics=len(results)
            )

        except Exception as e:
            self.logger.error("correlation_analysis_error", error=str(e))

        return results

    def _generate_analysis(
        self,
        service_name: str,
        current_cost: float,
        previous_cost: float,
        detection_results: List[DetectionResult],
        combined_score: float
    ) -> str:
        """분석 텍스트 생성."""
        change_pct = 0
        if previous_cost > 0:
            change_pct = ((current_cost - previous_cost) / previous_cost) * 100

        direction = "increased" if change_pct > 0 else "decreased"
        detected_methods = [r for r in detection_results if r.detected]

        analysis_parts = []

        # 기본 변화 설명
        analysis_parts.append(
            f"{service_name} cost {direction} by {abs(change_pct):.1f}% "
            f"(${previous_cost:.2f} → ${current_cost:.2f})"
        )

        # 탐지 방법별 상세
        for result in detected_methods:
            if result.anomaly_type == AnomalyType.RATIO:
                analysis_parts.append(
                    f"Ratio alert: {result.details.get('direction', 'change')} "
                    f"of {abs(result.details.get('change_ratio', 0)) * 100:.1f}%"
                )
            elif result.anomaly_type == AnomalyType.STDDEV:
                z_score = result.details.get('z_score', 0)
                analysis_parts.append(
                    f"Statistical alert: {abs(z_score):.2f} standard deviations "
                    f"{result.details.get('direction', '')} average"
                )
            elif result.anomaly_type == AnomalyType.TREND:
                days = result.details.get('consecutive_days', 0)
                avg_rate = result.details.get('average_increase_rate', 0) * 100
                analysis_parts.append(
                    f"Trend alert: {days} consecutive days of ~{avg_rate:.1f}% increase"
                )
            elif result.anomaly_type == AnomalyType.LUMINOL:
                luminol_score = result.details.get('luminol_score', 0)
                window_start = result.details.get('window_start', 'N/A')
                window_end = result.details.get('window_end', 'N/A')
                analysis_parts.append(
                    f"Luminol alert: anomaly score {luminol_score:.2f} "
                    f"(window: {window_start} ~ {window_end})"
                )

        # 종합 신뢰도
        analysis_parts.append(f"Combined confidence: {combined_score:.2f}")

        return ". ".join(analysis_parts)


def transform_costs_for_detection(
    costs_by_date: Dict[str, Dict[str, float]]
) -> Dict[str, Dict[str, float]]:
    """
    Cost Explorer 응답을 탐지기 입력 형식으로 변환.

    Args:
        costs_by_date: {date: {service: cost}} 형태

    Returns:
        {service: {date: cost}} 형태
    """
    result: Dict[str, Dict[str, float]] = {}

    for date, services in costs_by_date.items():
        for service, cost in services.items():
            if service not in result:
                result[service] = {}
            result[service][date] = cost

    return result


# 사용 예시
if __name__ == "__main__":
    from datetime import timedelta

    # 테스트 데이터 생성
    def generate_test_data(days: int = 14) -> Dict[str, Dict[str, float]]:
        """테스트용 비용 데이터 생성."""
        import random
        random.seed(42)

        services = ["Amazon EC2", "Amazon RDS", "Amazon S3"]
        data = {}

        for service in services:
            data[service] = {}
            base_cost = random.uniform(50, 200)

            for i in range(days):
                date = (datetime.now() - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
                variance = random.uniform(-0.1, 0.1)

                # EC2에 이상 현상 주입 (마지막 3일 급증)
                if service == "Amazon EC2" and i >= days - 3:
                    cost = base_cost * (1.5 + (i - (days - 3)) * 0.3)
                # RDS에 점진적 증가 패턴
                elif service == "Amazon RDS":
                    cost = base_cost * (1 + i * 0.05 + variance)
                else:
                    cost = base_cost * (1 + variance)

                data[service][date] = round(cost, 2)

        return data

    # 탐지기 초기화
    detector = CostAnomalyDetector()

    # 테스트 데이터 생성
    test_data = generate_test_data(14)

    print("=== Cost Anomaly Detection Test ===\n")

    # 개별 서비스 탐지
    for service, costs in test_data.items():
        result = detector.detect_anomaly(service, costs)
        if result:
            print(f"Service: {service}")
            print(f"  Is Anomaly: {result.is_anomaly}")
            print(f"  Severity: {result.severity.value}")
            print(f"  Confidence: {result.confidence_score:.3f}")
            print(f"  Cost Change: {result.cost_change_ratio * 100:.1f}%")
            print(f"  Detected Methods: {result.detected_methods}")
            print(f"  Analysis: {result.analysis}")
            print()

    # 전체 서비스 탐지
    print("=== All Services Summary ===\n")
    all_results = detector.detect_all_services(test_data)
    print(f"Anomalies found: {len(all_results)}")
    for r in all_results:
        print(f"  [{r.severity.value.upper()}] {r.service_name}: "
              f"score={r.confidence_score:.2f}, change={r.cost_change_ratio * 100:.1f}%")
