# BDP Compact Agent - EventBridge 연동

## 이벤트 구조

### Cost Drift Batch Detected

```json
{
  "version": "0",
  "source": "cd1-agent.bdp-cost",
  "detail-type": "Cost Drift Batch Detected",
  "detail": {
    "alert_type": "cost_drift_batch",
    "severity": "🚨",
    "severity_level": "critical",
    "title": "🚨 비용 드리프트 탐지: 5건",
    "message": "총 5건의 비용 이상이 탐지되었습니다...",
    "affected_services": [
      {
        "service_name": "Amazon Athena",
        "account_id": "111111111111",
        "account_name": "bdp-prod",
        "current_cost": 580000,
        "historical_average": 250000,
        "change_percent": 132.0,
        "confidence_score": 0.92,
        "raw_confidence_score": 0.95,
        "pattern_contexts": ["평일 평균 대비 정상 범위"],
        "spike_duration_days": 3,
        "trend_direction": "increasing",
        "severity": "critical"
      }
    ],
    "action_required": true,
    "hitl_request_id": "uuid-if-triggered",
    "account_name": "bdp-prod",
    "detection_timestamp": "2024-01-15T10:30:00Z"
  }
}
```

### Cost Drift Detected (단일)

```json
{
  "version": "0",
  "source": "cd1-agent.bdp-cost",
  "detail-type": "Cost Drift Detected",
  "detail": {
    "alert_type": "cost_drift",
    "severity": "🚨",
    "severity_level": "critical",
    "title": "🚨 비용 드리프트 탐지: Amazon Athena",
    "message": "아테나(bdp-prod) 비용이...",
    "service_name": "Amazon Athena",
    "account_id": "111111111111",
    "account_name": "bdp-prod",
    "current_cost": 580000,
    "historical_average": 250000,
    "change_percent": 132.0,
    "confidence_score": 0.92,
    "action_required": true,
    "detection_timestamp": "2024-01-15T10:30:00Z"
  }
}
```

## EventBridge Rule 예시

### 모든 이상 탐지 이벤트 캡처

```json
{
  "source": ["cd1-agent.bdp-cost"],
  "detail-type": ["Cost Drift Detected", "Cost Drift Batch Detected"]
}
```

### Action Required 이벤트만 캡처

```json
{
  "source": ["cd1-agent.bdp-cost"],
  "detail-type": ["Cost Drift Detected", "Cost Drift Batch Detected"],
  "detail": {
    "action_required": [true]
  }
}
```

### Critical/High 심각도만 캡처

```json
{
  "source": ["cd1-agent.bdp-cost"],
  "detail-type": ["Cost Drift Detected", "Cost Drift Batch Detected"],
  "detail": {
    "severity_level": ["critical", "high"]
  }
}
```

## 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `EVENT_PROVIDER` | Event Provider (real/mock) | `mock` |
| `EVENT_BUS` | EventBridge 버스 이름 | `cd1-agent-events` |
| `AWS_REGION` | AWS 리전 | `ap-northeast-2` |

## 타겟 구성 예시

### KakaoTalk Lambda 연동

```yaml
Rule:
  Name: bdp-cost-drift-to-kakao
  EventBusName: cd1-agent-events
  EventPattern:
    source:
      - cd1-agent.bdp-cost
    detail-type:
      - Cost Drift Batch Detected
    detail:
      action_required:
        - true
  Targets:
    - Id: kakao-notifier
      Arn: arn:aws:lambda:ap-northeast-2:111111111111:function:kakao-notifier
```

### SNS 토픽 연동

```yaml
Rule:
  Name: bdp-cost-drift-to-sns
  EventBusName: cd1-agent-events
  EventPattern:
    source:
      - cd1-agent.bdp-cost
  Targets:
    - Id: sns-topic
      Arn: arn:aws:sns:ap-northeast-2:111111111111:cost-alerts
```
