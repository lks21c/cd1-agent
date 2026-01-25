# BDP Compact Agent - KakaoTalk 알람

## 한글 Rich Summary

BDP Compact Agent는 사람이 읽기 쉬운 한글 알람 메시지를 생성합니다.

## 메시지 형식

### 단일 이상 탐지 메시지

```
아테나(bdp-prod) 비용이 일평균 25만원인데 1월 14일에 58만원으로
132% 치솟았고 이 상승 추세가 3일 지속되었습니다.

[계정: bdp-prod | 심각도: 높음]
```

### 일괄 이상 탐지 메시지

```
총 5건의 비용 이상이 탐지되었습니다.

• 심각: 1건
• 높음: 2건
• 보통: 1건
• 낮음: 1건

영향 계정: bdp-prod

주요 항목:
  🚨 Athena(bdp-prod): 58만원 (+132.0%)
  ⚠️ Lambda(bdp-prod): 12만원 (+85.3%)
  ⚠️ EC2(bdp-prod): 150만원 (+67.2%)
  📊 S3(bdp-prod): 8만원 (+52.1%)
  ℹ️ DynamoDB(bdp-prod): 5만원 (+35.0%)
```

## 비용 포맷팅 규칙

### KRW (한국 원화)

| 조건 | 포맷 | 예시 |
|------|------|------|
| ≥ 1억원 | `{x}억원` | 1.5억원 |
| ≥ 1만원 | `{x}만원` | 58만원 |
| < 1만원 | `{x}원` | 5,000원 |

### USD (미국 달러)

| 조건 | 포맷 | 예시 |
|------|------|------|
| ≥ $1M | `${x}M` | $1.5M |
| ≥ $1K | `${x}K` | $58K |
| < $1K | `${x}` | $500.00 |

## 심각도 Emoji

| 심각도 | Emoji | 한글 |
|--------|-------|------|
| CRITICAL | 🚨 | 심각 |
| HIGH | ⚠️ | 높음 |
| MEDIUM | 📊 | 보통 |
| LOW | ℹ️ | 낮음 |

## 날짜 포맷팅

날짜는 한국어 형식으로 표시됩니다:

- `1월 14일` (당월)
- `12월 31일` (다른 월)
- `2024년 1월 14일` (다른 연도)

## 서비스명 번역

주요 AWS 서비스명은 한글로 번역됩니다:

| AWS 서비스명 | 한글명 |
|--------------|--------|
| Amazon Athena | 아테나 |
| AWS Lambda | 람다 |
| Amazon EC2 | EC2 |
| Amazon S3 | S3 |
| Amazon DynamoDB | 다이나모DB |
| Amazon RDS | RDS |

## 알람 발송 조건

| 심각도 | KakaoTalk 알람 |
|--------|---------------|
| CRITICAL | ✅ 즉시 발송 |
| HIGH | ✅ 즉시 발송 |
| MEDIUM | ❌ 일일 리포트만 |
| LOW | ❌ 로그만 |

## 구현 예시

```python
from src.agents.bdp_cost.services.summary_generator import SummaryGenerator

generator = SummaryGenerator(currency="KRW")

# 단일 결과 Summary
summary = generator.generate_single_summary(result)

# 배치 결과 Summary
batch_summary = generator.generate_batch_summary(results)
```
