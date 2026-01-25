# HDSP Monitoring Troubleshooting

## 일반적인 문제

### 알림이 수신되지 않음

**증상**: 모니터링은 실행되지만 KakaoTalk 알림이 오지 않음

**체크리스트**:
1. KakaoTalk 활성화 확인:
   ```bash
   echo $KAKAO_ENABLED  # true여야 함
   ```

2. 토큰 파일 존재 확인:
   ```bash
   cat src/agents/bdp_common/conf/kakao_tokens.json
   ```

3. 심각도 확인:
   - MEDIUM 알림은 KakaoTalk으로 발송되지 않음
   - CRITICAL/HIGH만 KakaoTalk 발송

4. Mock 모드 확인:
   ```bash
   echo $PROMETHEUS_MOCK  # false여야 실제 연동
   echo $NOTIFICATION_MOCK  # false여야 실제 발송
   ```

---

### Alertmanager 연결 실패

**증상**: `Failed to fetch alerts` 오류

**해결 방법**:
1. Alertmanager URL 확인:
   ```bash
   curl http://localhost:9093/api/v2/alerts
   ```

2. 네트워크 접근 확인:
   ```bash
   # Alertmanager 포트 접근 테스트
   nc -zv alertmanager-host 9093
   ```

3. 환경 변수 확인:
   ```bash
   echo $ALERTMANAGER_URL
   ```

4. Mock 모드로 테스트:
   ```bash
   PROMETHEUS_MOCK=true python -m src.agents.hdsp_monitoring.handler
   ```

---

### 토큰 만료 오류

**증상**: `token expired` 또는 `invalid token` 오류

**해결 방법**:
1. 토큰 재발급:
   ```bash
   python -m src.agents.bdp_common.kakao.notifier
   ```

2. 토큰 파일 권한 확인:
   ```bash
   ls -la src/agents/bdp_common/conf/kakao_tokens.json
   ```

3. 자동 갱신 로그 확인:
   - "Access token expired, refreshing..." 메시지 확인

---

### 중복 알림 발생

**증상**: 동일한 알림이 여러 번 수신됨

**체크리스트**:
1. 중복 제거 설정 확인:
   ```json
   {
     "deduplication": {
       "enabled": true,
       "window_seconds": 300
     }
   }
   ```

2. 여러 인스턴스 실행 여부 확인:
   - Lambda 동시 실행
   - 여러 스케줄 트리거

3. 메모리 저장소 상태:
   - 인스턴스 재시작 시 중복 제거 초기화됨

---

### 알림 메시지 잘림

**증상**: KakaoTalk 메시지가 `...`로 끝남

**원인**: KakaoTalk 메시지 길이 제한 (1000자)

**해결 방법**:
- 메시지가 자동으로 1000자에서 잘림
- 상세 정보는 EventBridge 이벤트 확인

---

## 디버깅 방법

### 로그 레벨 조정

```bash
export LOG_LEVEL=DEBUG
python -m src.agents.hdsp_monitoring.handler
```

### 단계별 테스트

```python
# 1. Alert Fetcher 테스트
from src.agents.hdsp_monitoring.hdsp_monitoring.services.prometheus_alert_fetcher import (
    PrometheusAlertFetcher,
)

fetcher = PrometheusAlertFetcher(use_mock=False)
alerts = fetcher.fetch_firing_alerts()
print(f"Fetched {len(alerts)} alerts")

# 2. Severity Mapper 테스트
from src.agents.hdsp_monitoring.hdsp_monitoring.services.severity_mapper import (
    SeverityMapper,
)

mapper = SeverityMapper()
for alert in alerts:
    severity = mapper.map_severity(alert)
    print(f"{alert.alert_name}: {severity}")

# 3. KakaoTalk 테스트
from src.agents.bdp_common.kakao.notifier import KakaoNotifier

notifier = KakaoNotifier()
if notifier.load_tokens():
    success = notifier.send_text_message("테스트")
    print(f"Send result: {success}")
```

### Mock 모드 테스트

```bash
# 전체 Mock 테스트
PROMETHEUS_MOCK=true \
NOTIFICATION_MOCK=true \
python src/agents/hdsp_monitoring/scripts/test_alerts.py
```

---

## 성능 문제

### 알림 처리 지연

**증상**: 알림 발송까지 오래 걸림

**체크리스트**:
1. Alertmanager 응답 시간:
   ```bash
   time curl http://localhost:9093/api/v2/alerts
   ```

2. 알림 수 확인:
   - 많은 수의 알림이 있으면 처리 시간 증가

3. 레이트 리미팅:
   - `max_notifications_per_minute` 설정 확인

### 메모리 사용량 증가

**증상**: 메모리 사용량이 계속 증가

**해결 방법**:
1. 중복 제거 저장소 정리:
   ```python
   from src.agents.hdsp_monitoring.hdsp_monitoring.services.deduplication_store import (
       get_deduplication_store,
   )

   store = get_deduplication_store()
   store.clear()
   ```

2. Lambda 메모리 설정 조정

---

## EventBridge 문제

### 이벤트 미발행

**체크리스트**:
1. EventBridge 설정:
   ```bash
   echo $EVENT_BUS
   echo $EVENTBRIDGE_ENABLED
   ```

2. AWS 권한:
   - `events:PutEvents` 권한 필요

3. 이벤트 버스 존재 확인:
   ```bash
   aws events describe-event-bus --name cd1-agent-events
   ```

### 이벤트 규칙 미작동

1. 규칙 패턴 확인:
   ```bash
   aws events describe-rule --name HDSPAlertRule
   ```

2. 대상 설정 확인:
   ```bash
   aws events list-targets-by-rule --rule HDSPAlertRule
   ```

---

## 자주 묻는 질문

### Q: Mock 모드에서 실제 모드로 전환하려면?

```bash
# Mock 비활성화
export PROMETHEUS_MOCK=false
export NOTIFICATION_MOCK=false
export KAKAO_ENABLED=true

# Alertmanager URL 설정
export ALERTMANAGER_URL=http://your-alertmanager:9093
```

### Q: 특정 네임스페이스만 모니터링하려면?

```bash
export HDSP_INCLUDE_NAMESPACES=production,staging
export HDSP_EXCLUDE_NAMESPACES=test-*
```

### Q: 알림 빈도를 줄이려면?

`conf/detection_config.json` 수정:
```json
{
  "deduplication": {
    "repeat_interval_seconds": 7200  // 2시간
  },
  "rate_limiting": {
    "max_notifications_per_minute": 5
  }
}
```

### Q: 커스텀 알림을 CRITICAL로 만들려면?

```python
from src.agents.hdsp_monitoring.hdsp_monitoring.services.severity_mapper import (
    SeverityMapper,
    AlertSeverity,
)

mapper = SeverityMapper()
mapper.add_override("MyCustomAlert", AlertSeverity.CRITICAL)
```
