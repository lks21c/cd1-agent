# BDP Compact Agent - Pattern-Aware Detection

## 개요

Pattern-Aware Detection은 비용 데이터의 일반적인 패턴을 인식하여 False Positive를 줄이는 전략입니다.

## 문제 정의

### 현재 탐지 방식의 한계

- **모든 날을 동일하게 처리** → 요일별 패턴 무시
- **단순 임계값 기반** → 맥락 없는 판단
- **서비스 특성 무시** → Athena(변동 큼)와 EC2(안정적)를 동일 기준 적용

### False Positive 시나리오 분석

| 시나리오 | 발생 상황 | 현재 문제점 |
|---------|----------|-------------|
| **요일 패턴** | 주말 비용 낮음 → 월요일 급증 | 월요일을 anomaly로 오탐 |
| **월말/월초** | 정산 작업으로 비용 상승 | 매월 반복되는 정상 패턴 오탐 |
| **점진적 성장** | 비즈니스 성장으로 자연스러운 증가 | 성장을 anomaly로 오탐 |
| **서비스 특성** | Athena는 원래 변동이 큼 | 정상 변동을 anomaly로 오탐 |
| **일시적 스파이크** | 배치 작업 후 다음 날 정상화 | 정상화되었는데도 알람 |

## 설계 원칙

1. **Pluggable Architecture**: 새 패턴을 쉽게 추가 가능한 구조
2. **Confidence Adjustment**: 패턴 매칭 시 신뢰도 점수 조정 (anomaly 아님 → 신뢰도 하향)
3. **Lambda-Friendly**: numpy만 사용, scipy/pandas 의존성 최소화
4. **Gradual Rollout**: Shadow Mode → A/B 테스트 → 완전 적용

## 아키텍처

### PatternRecognizer 인터페이스

```python
from typing import Protocol, Optional
from dataclasses import dataclass
from enum import Enum

class PatternType(Enum):
    DAY_OF_WEEK = "day_of_week"      # 요일 패턴
    MONTH_CYCLE = "month_cycle"       # 월말/월초
    TREND = "trend"                   # 점진적 추세
    SERVICE_PROFILE = "service"       # 서비스 특성
    SEASONALITY = "seasonality"       # 계절성

@dataclass
class PatternContext:
    pattern_type: PatternType
    expected_value: float              # 패턴 기반 예상 비용
    actual_value: float                # 실제 비용
    confidence_adjustment: float       # -0.3 ~ +0.1 범위
    explanation: str                   # 한글 설명

class PatternRecognizer(Protocol):
    """패턴 인식기 인터페이스"""
    def recognize(self, data: ServiceCostData) -> Optional[PatternContext]:
        """패턴을 인식하고 맥락 정보 반환. 패턴 미발견 시 None."""
        ...
```

### PatternChain (책임 연쇄 패턴)

```python
class PatternChain:
    """여러 패턴 인식기를 체인으로 연결"""

    def __init__(self, recognizers: List[PatternRecognizer]):
        self.recognizers = recognizers

    def recognize_all(self, data: ServiceCostData) -> List[PatternContext]:
        """모든 인식된 패턴 반환"""
        contexts = []
        for recognizer in self.recognizers:
            ctx = recognizer.recognize(data)
            if ctx:
                contexts.append(ctx)
        return contexts

    def get_total_adjustment(self, data: ServiceCostData) -> float:
        """모든 패턴의 신뢰도 조정값 합산 (최대 -0.4)"""
        contexts = self.recognize_all(data)
        total = sum(ctx.confidence_adjustment for ctx in contexts)
        return max(total, -0.4)  # 최대 40% 하향
```

## 구현된 패턴 인식기

### Phase 1 (MVP)

#### DayOfWeekRecognizer (요일 패턴)

평일/주말 패턴을 인식하여 같은 타입의 요일끼리 비교합니다.

**동작 방식:**
1. 현재 날짜의 요일 타입 확인 (평일/주말)
2. 과거 데이터에서 같은 요일 타입의 비용만 추출
3. 같은 타입 평균 대비 현재 비용이 정상 범위(±30%)면 신뢰도 하향

**조정값:** -0.20 (20% 하향)

```python
# 예시: 월요일 비용이 평일 평균 대비 정상 범위
# → confidence_adjustment = -0.20
# → "평일 평균 대비 정상 범위"
```

#### TrendRecognizer (추세 패턴)

점진적 증가/감소 추세를 인식하여 추세선 기반 예상값과 비교합니다.

**동작 방식:**
1. 선형 회귀로 추세선 계산
2. 추세선 기반 예상값 산출
3. 실제 비용이 추세선 대비 ±15% 이내면 신뢰도 하향

**조정값:** -0.15 (15% 하향)

```python
# 예시: 비즈니스 성장으로 비용이 점진적 증가
# → 추세선 대비 정상 범위면 confidence_adjustment = -0.15
# → "추세선 기반 예상 범위 내 (편차: 5.2%)"
```

### Phase 2 (계획)

- **ServiceProfileRecognizer**: 서비스별 변동성 특성 학습
- **MonthCycleRecognizer**: 월말/월초 패턴 인식

### Phase 3 (계획)

- **SeasonalityRecognizer**: 계절성 패턴 인식
- 자동 튜닝 및 A/B 테스트 프레임워크

## CostDriftDetector 통합

```python
class CostDriftDetector:
    def __init__(
        self,
        sensitivity: float = 0.7,
        pattern_recognition_enabled: bool = True,  # 신규
    ):
        self.sensitivity = sensitivity
        self.pattern_chain = PatternChain([
            DayOfWeekRecognizer(),
            TrendRecognizer(),
        ]) if pattern_recognition_enabled else None

    def analyze_service(self, data: ServiceCostData) -> CostDriftResult:
        # 1. 기존 ECOD + Ratio 탐지
        ecod_result = self._detect_ecod(data)
        ratio_result = self._detect_ratio(data)
        raw_confidence = self._ensemble_confidence(ecod_result, ratio_result)

        # 2. [신규] 패턴 인식 기반 조정
        adjusted_confidence = raw_confidence
        pattern_explanations = []

        if self.pattern_chain:
            adjustment = self.pattern_chain.get_total_adjustment(data)
            adjusted_confidence = max(0.0, raw_confidence + adjustment)
            contexts = self.pattern_chain.recognize_all(data)
            pattern_explanations = [ctx.explanation for ctx in contexts]

        # 3. 최종 판정
        is_anomaly = adjusted_confidence >= self._get_threshold()

        return CostDriftResult(
            is_anomaly=is_anomaly,
            confidence=adjusted_confidence,
            raw_confidence=raw_confidence,  # 디버깅용
            pattern_contexts=pattern_explanations,
            ...
        )
```

## 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `BDP_PATTERN_RECOGNITION` | 패턴 인식 활성화 | `true` |
| `BDP_PATTERN_MODE` | 모드 (shadow/active) | `active` |
| `BDP_PATTERN_MAX_ADJUSTMENT` | 최대 조정폭 | `0.4` |

### Shadow Mode

Shadow Mode에서는 패턴 인식 결과를 로그로만 기록하고 실제 탐지 결과에는 반영하지 않습니다:

```bash
export BDP_PATTERN_MODE=shadow
```

## 검증 방법

### 1. Shadow Mode 테스트

기존 탐지 결과와 병렬 실행하여 로그로 비교합니다.

### 2. 단위 테스트

각 패턴 인식기별 테스트 케이스:

```python
def test_weekday_pattern_reduces_confidence():
    """월요일 비용 증가가 평일 평균 범위 내면 confidence 하향"""

def test_weekend_pattern_reduces_confidence():
    """주말 비용 감소가 주말 평균 범위 내면 confidence 하향"""

def test_trend_pattern_reduces_confidence():
    """점진적 증가가 추세선 내면 confidence 하향"""

def test_no_pattern_keeps_confidence():
    """패턴 미인식 시 기존 confidence 유지"""

def test_multiple_patterns_combine():
    """여러 패턴 동시 인식 시 조정값 합산 (최대 제한)"""
```

### 3. 통합 테스트

실제 비용 데이터 기반 false positive 비율 측정.

## 구현 로드맵

| Phase | 내용 | 상태 |
|-------|------|------|
| **Phase 1 (MVP)** | 요일 패턴 + 추세 인식 | ✅ 완료 |
| **Phase 2** | 서비스 특성 + 월별 패턴 | 📋 계획 |
| **Phase 3** | 계절성 + A/B 테스트 | 📋 계획 |
