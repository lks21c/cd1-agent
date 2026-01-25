# BDP Compact Agent - 심각도 분류

## 심각도 레벨

| 심각도 | 조건 | Emoji | 조치 |
|--------|------|-------|------|
| **CRITICAL** | confidence ≥ 0.9 **또는** 변화율 ≥ 200% | 🚨 | KakaoTalk 즉시 알람 + HITL 요청 |
| **HIGH** | confidence ≥ 0.7 **또는** 변화율 ≥ 100% | ⚠️ | KakaoTalk 즉시 알람 |
| **MEDIUM** | confidence ≥ 0.5 **또는** 변화율 ≥ 50% | 📊 | 일일 리포트 포함 |
| **LOW** | 기타 이상 | ℹ️ | 로그 기록 |

## 심각도 계산 로직

```python
def _calculate_severity(self, confidence: float, change_percent: float) -> Severity:
    """심각도 레벨 계산."""
    abs_change = abs(change_percent)

    if confidence >= 0.9 or abs_change >= 200:
        return Severity.CRITICAL
    elif confidence >= 0.7 or abs_change >= 100:
        return Severity.HIGH
    elif confidence >= 0.5 or abs_change >= 50:
        return Severity.MEDIUM
    else:
        return Severity.LOW
```

## 심각도별 처리

### CRITICAL (🚨)

- **즉시 알람**: KakaoTalk 메시지 발송
- **HITL 요청**: Human-in-the-Loop 요청 자동 생성
- **EventBridge 이벤트**: `action_required: true`

### HIGH (⚠️)

- **즉시 알람**: KakaoTalk 메시지 발송
- **EventBridge 이벤트**: `action_required: true`

### MEDIUM (📊)

- **일일 리포트**: 리포트에 포함
- **EventBridge 이벤트**: `action_required: false`

### LOW (ℹ️)

- **로그 기록**: 시스템 로그에만 기록
- **EventBridge 이벤트**: 발송하지 않음

## 패턴 인식과의 관계

패턴 인식 후 조정된 confidence를 사용하여 심각도를 계산합니다:

```
raw_confidence → PatternChain → adjusted_confidence → Severity 계산
```

패턴 인식으로 confidence가 낮아지면 심각도도 낮아질 수 있습니다.

## 알람 메시지 예시

### CRITICAL

```
🚨 비용 드리프트 탐지: Amazon Athena

아테나(bdp-prod) 비용이 일평균 25만원인데
1월 14일에 75만원으로 200% 치솟았습니다.

[계정: bdp-prod | 심각도: 심각]
```

### HIGH

```
⚠️ 비용 드리프트 탐지: AWS Lambda

람다(bdp-prod) 비용이 일평균 8만원인데
1월 14일에 18만원으로 125% 치솟았습니다.

[계정: bdp-prod | 심각도: 높음]
```
