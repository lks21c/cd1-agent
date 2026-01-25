# BDP Compact Agent - 탐지 알고리즘

## 개요

BDP Compact는 ECOD + Ratio 앙상블 알고리즘과 패턴 인식 기반 신뢰도 조정을 사용합니다.

## PyOD ECOD (Empirical Cumulative Distribution Functions)

[PyOD](https://github.com/yzhao062/pyod) 라이브러리의 ECOD 알고리즘을 기본 탐지기로 사용합니다.

### ECOD 특징

- **Parameter-free**: 하이퍼파라미터 튜닝 불필요
- **Fast**: O(n) 학습/추론 시간복잡도
- **Multivariate**: 다변량 이상 탐지에 효과적
- **Active Maintenance**: Python 3.11+ 지원 (Luminol 대비 장점)

### 사용 예시

```python
from pyod.models.ecod import ECOD

# 비용 데이터 준비
X = np.array(costs).reshape(-1, 1)

# ECOD 모델 학습
clf = ECOD(contamination=0.1)  # 이상치 비율 10% 추정
clf.fit(X)

# 이상 탐지
labels = clf.labels_      # 0: 정상, 1: 이상
scores = clf.decision_scores_  # 이상 점수
```

### Lambda 경량 버전 (LightweightECOD)

PyOD가 설치되지 않은 Lambda 환경에서는 scipy 의존성 없는 경량 ECOD 구현을 사용합니다:

```python
from src.agents.bdp_cost.services.anomaly_detector import LightweightECOD

clf = LightweightECOD(contamination=0.1)
clf.fit(X)
```

## Ratio 기반 탐지 (Fallback/앙상블)

ECOD와 함께 Ratio 기반 탐지를 앙상블로 사용합니다.

```python
# 현재 비용 / 과거 평균
ratio = current_cost / historical_average

# 임계값 판정 (기본: 1.5배)
is_anomaly = ratio > ratio_threshold or ratio < (1 / ratio_threshold)
```

## 앙상블 판정

| 탐지 결과 | 최종 판정 | 신뢰도 |
|-----------|----------|--------|
| ECOD: 이상, Ratio: 이상 | **이상** | 신뢰도 × 1.2 (앙상블 보정) |
| ECOD: 이상, Ratio: 정상 | **이상** | ECOD 신뢰도 사용 |
| ECOD: 정상, Ratio: 이상 | **이상** | Ratio 신뢰도 사용 |
| ECOD: 정상, Ratio: 정상 | **정상** | - |

## 패턴 인식 기반 조정

앙상블 탐지 후, 패턴 인식기가 신뢰도를 조정합니다:

```
raw_confidence → PatternChain → adjusted_confidence
```

패턴 인식 상세 내용은 [pattern_aware.md](pattern_aware.md)를 참조하세요.

## 트렌드 분석

선형 회귀로 비용 추세를 분석합니다.

```python
# 선형 회귀 기울기
slope = np.polyfit(x, costs, 1)[0]
slope_ratio = slope / np.mean(costs)

# 트렌드 분류
if slope_ratio > 0.05:   return "increasing"
elif slope_ratio < -0.05: return "decreasing"
else:                     return "stable"
```

## 스파이크 지속 기간

평균 대비 120% 이상인 날이 연속으로 몇 일인지 계산합니다.

```python
threshold = historical_average * 1.2  # 20% 이상 상승
spike_duration = count_consecutive_days_above_threshold(costs, threshold)
```

## 탐지 방법 식별

결과의 `detection_method` 필드로 사용된 알고리즘을 식별할 수 있습니다:

| 값 | 설명 |
|----|------|
| `ecod` | PyOD ECOD 사용 |
| `ecod_lite` | LightweightECOD 사용 |
| `ratio` | Ratio 기반 탐지만 사용 |
| `ensemble` | PyOD ECOD + Ratio 앙상블 |
| `ensemble_lite` | LightweightECOD + Ratio 앙상블 |
| `insufficient_data` | 데이터 부족 |

## 참고 문헌

- [PyOD Documentation](https://pyod.readthedocs.io/)
- [ECOD Paper](https://arxiv.org/abs/2201.00382) - Li et al., "ECOD: Unsupervised Outlier Detection Using Empirical Cumulative Distribution Functions" (2022)
