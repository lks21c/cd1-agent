# BDP Compact Agent 개선 제안서

## 개요

Cost Agent와 BDP Compact Agent의 이상 탐지 기능을 비교 분석하고, BDP Compact Agent에 추가 가능한 기능을 제안합니다.

---

## 1. Cost Agent vs BDP Compact 비교 분석

### 1.1 탐지 알고리즘 비교

| 항목 | Cost Agent | BDP Compact |
|------|-----------|-------------|
| **주요 알고리즘** | Luminol (LinkedIn) | ECOD (PyOD/Lightweight) |
| **탐지 방법 수** | 4개 (Ratio, Stddev, Trend, Luminol) | 2개 (ECOD, Ratio) |
| **앙상블 방식** | 가중치 기반 점수 결합 | 단순 신뢰도 상승 (1.2x) |
| **패턴 인식** | ❌ 없음 | ✅ DayOfWeek, Trend 패턴 |
| **Shadow Mode** | ❌ 없음 | ✅ 패턴 인식 테스트 모드 |

### 1.2 데이터 구조 비교

**Cost Agent - CostAnomalyResult**
```python
@dataclass
class CostAnomalyResult:
    is_anomaly: bool
    confidence_score: float
    severity: str
    service_name: str
    current_value: float
    previous_value: float
    change_ratio: float
    detection_results: List[AnomalyScore]  # 각 방법별 결과
    detected_methods: List[str]
    analysis: str  # 사람이 읽을 수 있는 분석
    timestamp: str
```

**BDP Compact - CostDriftResult**
```python
@dataclass
class CostDriftResult:
    is_anomaly: bool
    confidence_score: float
    severity: Severity
    service_name: str
    account_id: str  # ✅ 계정 정보
    account_name: str  # ✅ 계정 이름
    current_cost: float
    historical_average: float
    change_percent: float
    spike_duration_days: int  # ✅ 연속 상승일
    trend_direction: str  # ✅ 트렌드 방향
    spike_start_date: Optional[str]  # ✅ 급등 시작일
    detection_method: str
    raw_score: float
    raw_confidence_score: Optional[float]  # ✅ 패턴 조정 전
    pattern_contexts: List[str]  # ✅ 패턴 설명
    historical_costs: Optional[List[float]]  # ✅ 차트용 데이터
    timestamps: Optional[List[str]]
```

### 1.3 클라이언트 기능 비교

| 기능 | Cost Agent | BDP Compact |
|------|-----------|-------------|
| **Provider 추상화** | ✅ Real/LocalStack/Mock | ✅ Real/LocalStack/Mock |
| **비용 조회** | ✅ get_cost_and_usage | ✅ (provider 내장) |
| **비용 예측** | ✅ get_cost_forecast | ❌ 없음 |
| **AWS 이상 탐지 API** | ✅ get_anomalies | ❌ 없음 |
| **서비스별 비용** | ✅ get_cost_by_service | ✅ (다른 구조) |

### 1.4 장단점 요약

**Cost Agent 장점**
- 다양한 탐지 방법으로 높은 탐지율
- 가중치 기반 앙상블로 정교한 점수 산출
- AWS 네이티브 이상 탐지 API 활용
- 비용 예측 기능 제공

**BDP Compact 장점**
- ECOD 알고리즘으로 파라미터 튜닝 불필요
- 패턴 인식으로 False Positive 감소
- 계정별 분석으로 멀티 어카운트 지원
- Lambda 최적화 (scipy 의존성 제거)

---

## 2. 추가 가능한 기능 목록

### 2.1 Stddev 기반 탐지 추가 ⭐ 권장

**설명**: 표준편차 기반 Z-score 이상 탐지 방법 추가

**장점**:
- 구현 간단 (numpy만 사용)
- 통계적으로 해석 가능한 결과
- ECOD와 다른 관점 제공

**단점**:
- 정규분포 가정 필요
- 작은 데이터셋에서 불안정

**구현 복잡도**: 낮음

**예시 코드**:
```python
def _detect_stddev(self, costs: List[float]) -> Dict[str, Any]:
    """표준편차 기반 이상 탐지."""
    if len(costs) < 2:
        return {"is_anomaly": False, "confidence": 0.0, "z_score": 0.0}

    current = costs[-1]
    historical = costs[:-1]

    mean = np.mean(historical)
    std = np.std(historical, ddof=1)

    if std == 0:
        return {"is_anomaly": current != mean, "confidence": 0.0, "z_score": 0.0}

    z_score = abs(current - mean) / std
    threshold = 3.0 - self.sensitivity  # 2.0 ~ 3.0

    is_anomaly = z_score > threshold
    confidence = min(1.0, z_score / (threshold * 2))

    return {
        "is_anomaly": is_anomaly,
        "confidence": confidence * self.sensitivity,
        "z_score": z_score,
        "threshold": threshold,
    }
```

---

### 2.2 Luminol 통합 (선택적)

**설명**: LinkedIn의 Luminol 라이브러리를 선택적으로 사용

**장점**:
- 검증된 시계열 이상 탐지 알고리즘
- Bitmap 기반 탐지로 다양한 패턴 감지
- Cost Agent와 일관된 탐지 방식

**단점**:
- 추가 의존성 (luminol 패키지)
- Lambda 배포 크기 증가
- Python 3.11+ 호환성 확인 필요

**구현 복잡도**: 중간

**예시 코드**:
```python
# Graceful degradation
try:
    from luminol.anomaly_detector import AnomalyDetector as LuminolDetector
    from luminol.modules.time_series import TimeSeries
    LUMINOL_AVAILABLE = True
except ImportError:
    LUMINOL_AVAILABLE = False

def _detect_luminol(self, costs: List[float], timestamps: List[str]) -> Optional[Dict]:
    """Luminol 기반 이상 탐지."""
    if not LUMINOL_AVAILABLE:
        return None

    try:
        # 타임스탬프를 epoch로 변환
        ts_dict = {}
        for i, ts_str in enumerate(timestamps):
            dt = datetime.fromisoformat(ts_str)
            ts_dict[int(dt.timestamp())] = costs[i]

        ts = TimeSeries(ts_dict)
        detector = LuminolDetector(ts)
        anomalies = detector.get_anomalies()

        # 마지막 포인트 이상 여부 확인
        latest_ts = max(ts_dict.keys())
        is_anomaly = any(
            a.start_timestamp <= latest_ts <= a.end_timestamp
            for a in anomalies
        )

        max_score = max((a.anomaly_score for a in anomalies), default=0)
        normalized_score = min(1.0, max_score / 100)

        return {
            "is_anomaly": is_anomaly,
            "confidence": normalized_score,
            "raw_score": max_score,
        }
    except Exception as e:
        logger.warning(f"Luminol detection failed: {e}")
        return None
```

---

### 2.3 가중치 기반 앙상블 점수 ⭐ 권장

**설명**: 여러 탐지 방법의 결과를 가중치로 결합

**장점**:
- 단일 방법보다 안정적인 결과
- 방법별 신뢰도 조정 가능
- 새 탐지 방법 추가 용이

**단점**:
- 가중치 튜닝 필요
- 복잡도 증가

**구현 복잡도**: 낮음

**예시 코드**:
```python
def _calculate_ensemble_score(self, results: Dict[str, Dict]) -> float:
    """가중치 기반 앙상블 점수 계산."""
    weights = {
        "ecod": 0.40,      # 주력 알고리즘
        "ratio": 0.25,     # 단순 비율
        "stddev": 0.25,    # 통계적 방법
        "luminol": 0.10,   # 보조 (선택적)
    }

    total_weight = 0.0
    weighted_score = 0.0

    for method, result in results.items():
        if result and method in weights:
            weight = weights[method]
            score = result.get("confidence", 0.0)
            weighted_score += score * weight
            total_weight += weight

    return weighted_score / total_weight if total_weight > 0 else 0.0
```

---

### 2.4 AWS Cost Anomaly Detection API 통합

**설명**: AWS 네이티브 비용 이상 탐지 서비스 활용

**장점**:
- AWS가 관리하는 ML 모델 활용
- Root cause 분석 제공
- 추가 알고리즘 구현 불필요

**단점**:
- AWS 비용 발생
- LocalStack에서 지원 안됨 (Mock 필요)
- API 호출 지연

**구현 복잡도**: 중간

**예시 코드**:
```python
def get_aws_anomalies(
    self,
    start_date: str,
    end_date: str,
    monitor_arn: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """AWS Cost Anomaly Detection API 호출."""
    params = {
        "DateInterval": {"StartDate": start_date, "EndDate": end_date},
    }
    if monitor_arn:
        params["MonitorArn"] = monitor_arn

    response = self.ce_client.get_anomalies(**params)

    return [
        {
            "anomaly_id": a["AnomalyId"],
            "start_date": a["AnomalyStartDate"],
            "end_date": a.get("AnomalyEndDate"),
            "root_causes": a.get("RootCauses", []),
            "impact": {
                "max_impact": float(a.get("Impact", {}).get("MaxImpact", 0)),
                "total_impact": float(a.get("Impact", {}).get("TotalImpact", 0)),
            },
        }
        for a in response.get("Anomalies", [])
    ]
```

---

### 2.5 비용 예측 기능 추가

**설명**: 향후 비용 예측 및 예산 초과 경고

**장점**:
- 사전 예방적 비용 관리
- 예산 계획 지원
- 이상 탐지와 결합하여 정확도 향상

**단점**:
- 예측 정확도 한계
- 추가 API 호출
- 신규 서비스는 예측 어려움

**구현 복잡도**: 중간

**예시 코드**:
```python
def get_cost_forecast(
    self,
    days_ahead: int = 7,
    granularity: str = "DAILY",
) -> Dict[str, Any]:
    """향후 비용 예측."""
    start = datetime.utcnow()
    end = start + timedelta(days=days_ahead)

    response = self.ce_client.get_cost_forecast(
        TimePeriod={
            "Start": start.strftime("%Y-%m-%d"),
            "End": end.strftime("%Y-%m-%d"),
        },
        Granularity=granularity,
        Metric="UNBLENDED_COST",
    )

    return {
        "total_forecast": float(response.get("Total", {}).get("Amount", 0)),
        "forecast_by_day": [
            {
                "date": item["TimePeriod"]["Start"],
                "mean": float(item.get("MeanValue", 0)),
                "min": float(item.get("PredictionIntervalLowerBound", 0)),
                "max": float(item.get("PredictionIntervalUpperBound", 0)),
            }
            for item in response.get("ForecastResultsByTime", [])
        ],
    }
```

---

### 2.6 추가 패턴 인식기 ⭐ 권장

**설명**: 월말/월초 패턴, 계절성 패턴 인식기 추가

**장점**:
- False Positive 추가 감소
- 비즈니스 사이클 반영
- 기존 PatternChain 활용

**단점**:
- 패턴 학습 데이터 필요 (최소 30일)
- 서비스별 특성 차이

**구현 복잡도**: 낮음

**예시 코드**:
```python
class MonthCycleRecognizer:
    """월말/월초 패턴 인식기.

    결제 주기, 월말 배치 작업 등으로 인한 비용 급등 패턴 인식.
    """

    MONTH_CYCLE_ADJUSTMENT = -0.15

    def recognize(self, data: "ServiceCostData") -> Optional[PatternContext]:
        """월말/월초 패턴 인식."""
        if len(data.timestamps) < 30:
            return None

        current_date = datetime.fromisoformat(data.timestamps[-1])
        day_of_month = current_date.day

        # 월초 (1-5일) 또는 월말 (26-31일)
        is_month_boundary = day_of_month <= 5 or day_of_month >= 26

        if not is_month_boundary:
            return None

        # 같은 기간의 과거 데이터와 비교
        boundary_costs = self._get_boundary_costs(data, day_of_month <= 5)

        if len(boundary_costs) < 2:
            return None

        expected = float(np.mean(boundary_costs))
        actual = data.current_cost

        ratio = actual / expected if expected > 0 else 0

        if 0.7 <= ratio <= 1.3:  # ±30% 범위
            return PatternContext(
                pattern_type=PatternType.MONTH_CYCLE,
                expected_value=expected,
                actual_value=actual,
                confidence_adjustment=self.MONTH_CYCLE_ADJUSTMENT,
                explanation="월말/월초 정상 범위",
            )

        return None


class ServiceProfileRecognizer:
    """서비스 특성 기반 패턴 인식기.

    Lambda, Batch 등 스파이크 패턴이 정상인 서비스 인식.
    """

    SPIKE_NORMAL_SERVICES = {"AWS Lambda", "AWS Batch", "AWS Glue"}
    SERVICE_ADJUSTMENT = -0.10

    def recognize(self, data: "ServiceCostData") -> Optional[PatternContext]:
        """서비스 특성 패턴 인식."""
        if data.service_name not in self.SPIKE_NORMAL_SERVICES:
            return None

        # 해당 서비스는 일시적 스파이크가 정상
        if data.current_cost > 0:
            return PatternContext(
                pattern_type=PatternType.SERVICE_PROFILE,
                expected_value=data.historical_average,
                actual_value=data.current_cost,
                confidence_adjustment=self.SERVICE_ADJUSTMENT,
                explanation=f"{data.service_name} 스파이크 패턴 정상",
            )

        return None
```

---

### 2.7 사람이 읽을 수 있는 분석 생성 ⭐ 권장

**설명**: 탐지 결과를 자연어로 설명

**장점**:
- 비기술 담당자도 이해 가능
- KakaoTalk 알림에 활용
- 디버깅 용이

**단점**:
- 구현 필요
- 다국어 지원 고려

**구현 복잡도**: 낮음

**예시 코드**:
```python
def generate_analysis(self, result: CostDriftResult) -> str:
    """사람이 읽을 수 있는 분석 생성."""
    if not result.is_anomaly:
        return f"{result.service_name}에서 이상 비용이 감지되지 않았습니다."

    direction = "증가" if result.change_percent > 0 else "감소"
    abs_change = abs(result.change_percent)

    # 기본 분석
    analysis = (
        f"🚨 {result.service_name} 비용 이상 감지\n"
        f"• {abs_change:.1f}% {direction} "
        f"(${result.historical_average:.2f} → ${result.current_cost:.2f})\n"
        f"• 심각도: {result.severity.value.upper()}\n"
        f"• 탐지 방법: {result.detection_method}\n"
    )

    # 추가 컨텍스트
    if result.spike_duration_days > 1:
        analysis += f"• 연속 상승: {result.spike_duration_days}일\n"

    if result.trend_direction == "increasing":
        analysis += "• 추세: 지속적 상승 중\n"

    # 패턴 컨텍스트
    if result.pattern_contexts:
        analysis += f"• 패턴: {', '.join(result.pattern_contexts)}\n"

    return analysis
```

---

## 3. 구현 우선순위 및 권장사항

### 3.1 우선순위 매트릭스

| 순위 | 기능 | 효과 | 복잡도 | 권장 |
|:---:|------|:---:|:---:|:---:|
| 1 | Stddev 탐지 추가 | 높음 | 낮음 | ⭐⭐⭐ |
| 2 | 가중치 앙상블 | 높음 | 낮음 | ⭐⭐⭐ |
| 3 | 분석 문장 생성 | 중간 | 낮음 | ⭐⭐⭐ |
| 4 | 추가 패턴 인식기 | 중간 | 낮음 | ⭐⭐ |
| 5 | 비용 예측 | 중간 | 중간 | ⭐⭐ |
| 6 | AWS Anomaly API | 중간 | 중간 | ⭐ |
| 7 | Luminol 통합 | 낮음 | 중간 | ⭐ |

### 3.2 단계별 구현 권장

**Phase 1: 빠른 개선 (1-2일)**
1. Stddev 탐지 방법 추가
2. 가중치 기반 앙상블 구현
3. 분석 문장 생성 함수 추가

**Phase 2: 패턴 강화 (2-3일)**
1. MonthCycleRecognizer 추가
2. ServiceProfileRecognizer 추가
3. 패턴 테스트 및 튜닝

**Phase 3: 고급 기능 (선택적)**
1. AWS Cost Anomaly Detection API 통합
2. 비용 예측 기능 추가
3. Luminol 통합 (필요시)

### 3.3 고려사항

**Lambda 배포 제약**
- scipy 의존성 제거 유지 (현재 경량 ECOD 사용)
- 패키지 크기 250MB 제한
- Luminol 추가 시 Layer 분리 고려

**테스트 전략**
- 새 탐지 방법은 Shadow Mode로 먼저 검증
- 기존 데이터로 False Positive/Negative 비교
- 환경 변수로 점진적 활성화

**설정 관리**
```python
# 권장 환경 변수
BDP_DETECTION_METHODS="ecod,ratio,stddev"  # 활성화할 방법
BDP_ENSEMBLE_WEIGHTS='{"ecod":0.4,"ratio":0.3,"stddev":0.3}'
BDP_PATTERN_RECOGNITION="true"
BDP_PATTERN_MODE="active"  # or "shadow"
```

---

## 4. 참조 코드 위치

| 구성 요소 | 파일 경로 |
|----------|----------|
| Cost Agent 탐지기 | `src/agents/cost/services/anomaly_detector.py` |
| Cost Explorer 클라이언트 | `src/agents/cost/services/cost_explorer_client.py` |
| BDP Compact 탐지기 | `src/agents/bdp_compact/services/anomaly_detector.py` |
| 패턴 인식기 | `src/agents/bdp_compact/services/pattern_recognizers.py` |

---

## 부록: 데이터 흐름 비교

```
[Cost Agent]
Cost Explorer API → CostExplorerClient → CostAnomalyDetector
                                         ├─ Ratio Detection
                                         ├─ Stddev Detection
                                         ├─ Trend Detection
                                         └─ Luminol Detection
                                              ↓
                                         Ensemble Score → CostAnomalyResult

[BDP Compact]
Cost Explorer API → CostExplorerProvider → CostDriftDetector
                                           ├─ ECOD Detection
                                           └─ Ratio Detection
                                                ↓
                                           PatternChain
                                           ├─ DayOfWeekRecognizer
                                           └─ TrendRecognizer
                                                ↓
                                           Adjusted Score → CostDriftResult
```
