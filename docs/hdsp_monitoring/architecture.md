# HDSP Monitoring Architecture

## 시스템 개요

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Prometheus    │────▶│  Alertmanager   │────▶│ HDSP Monitoring │
│    (Metrics)    │     │   (Alerts)      │     │    (Agent)      │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┼────────────────────────────────┐
                        │                                │                                │
                        ▼                                ▼                                ▼
              ┌─────────────────┐             ┌─────────────────┐             ┌─────────────────┐
              │   KakaoTalk     │             │   EventBridge   │             │   DynamoDB      │
              │ (CRITICAL/HIGH) │             │  (All Alerts)   │             │   (History)     │
              └─────────────────┘             └─────────────────┘             └─────────────────┘
```

## 컴포넌트 구성

### 1. Alert Fetcher (PrometheusAlertFetcher)

Alertmanager API에서 firing 상태의 알림을 조회합니다.

```python
# 알림 조회
fetcher = PrometheusAlertFetcher(alertmanager_url="http://alertmanager:9093")
alerts = fetcher.fetch_firing_alerts()
```

**지원 Provider:**
- `RealAlertFetcher`: 실제 Alertmanager 연동
- `MockAlertFetcher`: 테스트용 Mock 데이터

### 2. Severity Mapper (SeverityMapper)

Prometheus 알림을 3-Tier 심각도로 매핑합니다.

**매핑 우선순위:**
1. 알림 이름 오버라이드 (최우선)
2. Label 기반 매핑
3. 키워드 패턴 매칭
4. 기본값 MEDIUM

```python
mapper = SeverityMapper()
severity = mapper.map_severity(alert)  # CRITICAL, HIGH, or MEDIUM
```

### 3. Alert Processor (AlertProcessor)

알림을 처리하고 중복을 제거합니다.

**기능:**
- 네임스페이스 필터링 (include/exclude)
- 알림 그룹화 (namespace:alertname)
- 레이트 리미팅 (분당 최대 알림 수)
- 중복 제거 (fingerprint 기반)

```python
processor = AlertProcessor(
    cluster_name="on-prem-k8s",
    exclude_namespaces=["test-*", "dev-*"],
    max_notifications_per_minute=10,
)
all_processed, to_notify = processor.process_alerts(raw_alerts)
```

### 4. Summary Generator (AlertSummaryGenerator)

한글 알림 메시지를 생성합니다.

**출력 예시:**
```
🚨 K8s 알림: CrashLoopBackOff
━━━━━━━━━━━━━━━━━━━━
🏷️ 클러스터: on-prem-k8s
📍 네임스페이스: spark
🔧 리소스: 파드/spark-executor-abc123
━━━━━━━━━━━━━━━━━━━━

📋 알림 내용:
Pod가 반복적으로 재시작 중입니다.

⚠️ 조치 권고:
즉시 확인이 필요합니다.

[심각도: CRITICAL | 지속시간: 25분]
```

### 5. Notification Router (NotificationRouter)

심각도에 따라 적절한 채널로 알림을 라우팅합니다.

**라우팅 규칙:**
| 심각도 | Primary | Fallback |
|--------|---------|----------|
| CRITICAL | KakaoTalk | EventBridge |
| HIGH | KakaoTalk | EventBridge |
| MEDIUM | EventBridge | - |

### 6. Deduplication Store (DeduplicationStore)

알림 중복을 방지하는 메모리 저장소입니다.

**기능:**
- 5분 내 동일 알림 중복 제거
- 1시간 간격 반복 알림 허용
- 자동 정리 (stale 엔트리 제거)

## 데이터 흐름

```
1. Alertmanager에서 firing 알림 조회
   └─ PrometheusAlertFetcher.fetch_firing_alerts()

2. 알림 처리 및 필터링
   ├─ 네임스페이스 필터링
   ├─ 심각도 매핑
   └─ 중복 제거
   └─ AlertProcessor.process_alerts()

3. 알림 그룹화
   └─ AlertProcessor.group_alerts()

4. 한글 메시지 생성
   └─ AlertSummaryGenerator.generate_batch_summary()

5. 알림 라우팅 및 발송
   ├─ CRITICAL/HIGH → KakaoTalk → EventBridge (fallback)
   └─ MEDIUM → EventBridge
   └─ NotificationRouter.route_alerts()
```

## 통합 포인트

### bdp_common 모듈 재사용

```python
# KakaoTalk 알림
from src.agents.bdp_common.kakao.notifier import KakaoNotifier

# EventBridge 이벤트 발행
from src.agents.bdp_common.eventbridge.publisher import EventPublisher
```

### Lambda Handler

```python
# handler.py
from src.common.handlers.base_handler import BaseHandler

class HDSPMonitoringHandler(BaseHandler):
    def process(self, event, context):
        # 알림 조회 → 처리 → 발송
        ...
```

## 확장 가능성

1. **추가 알림 채널**: Slack, Teams, Email 등
2. **알림 저장**: DynamoDB, RDS에 알림 이력 저장
3. **대시보드 연동**: Grafana Loki, CloudWatch 연동
4. **머신러닝 기반 이상 탐지**: 알림 패턴 학습
