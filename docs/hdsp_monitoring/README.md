# HDSP Monitoring Agent

Prometheus Alertmanager 기반 K8s 모니터링 시스템으로, 알림을 심각도별로 분류하여 KakaoTalk으로 발송합니다.

## 주요 기능

- **3-Tier 심각도 분류**: CRITICAL, HIGH, MEDIUM
- **KakaoTalk 알림**: CRITICAL/HIGH 알림 즉시 발송
- **EventBridge 연동**: 모든 알림 이벤트 발행
- **알림 중복 제거**: 동일 알림 반복 발송 방지
- **한글 메시지**: 알림 내용 한글화

## 빠른 시작

### 1. 환경 변수 설정

```bash
# Alertmanager 연결
export ALERTMANAGER_URL=http://localhost:9093
export PROMETHEUS_MOCK=false  # 실제 연결 시

# 클러스터 설정
export HDSP_CLUSTER_NAME=on-prem-k8s

# KakaoTalk 설정
export KAKAO_ENABLED=true

# EventBridge 설정
export EVENT_BUS=cd1-agent-events
```

### 2. 테스트 실행

```bash
# Mock 모드로 테스트
PROMETHEUS_MOCK=true python -m src.agents.hdsp_monitoring.handler

# 테스트 스크립트 실행
python src/agents/hdsp_monitoring/scripts/test_alerts.py
```

### 3. Lambda 핸들러

```python
from src.agents.hdsp_monitoring.handler import handler

event = {
    "publish_notifications": True,
    "min_severity": "medium",
}

result = handler(event, None)
```

### 4. FastAPI 서버 (개발용)

```bash
python src/agents/hdsp_monitoring/server.py --port 8080

# 헬스체크
curl http://localhost:8080/health

# 모니터링 실행
curl -X POST http://localhost:8080/monitor
```

## 심각도 분류

| 레벨 | 이모지 | 설명 | 알림 채널 |
|------|--------|------|-----------|
| CRITICAL | 🚨 | 서비스 다운, 데이터 손실 위험 | KakaoTalk + EventBridge |
| HIGH | ⚠️ | 성능 저하, 주의 필요 | KakaoTalk + EventBridge |
| MEDIUM | 📊 | 경고, 모니터링 필요 | EventBridge만 |

## 디렉토리 구조

```
src/agents/hdsp_monitoring/
├── __init__.py
├── handler.py              # Lambda 핸들러
├── server.py               # FastAPI 서버
├── hdsp_monitoring/
│   └── services/
│       ├── models.py                   # 데이터 모델
│       ├── prometheus_alert_fetcher.py # Alertmanager 연동
│       ├── alert_processor.py          # 알림 처리
│       ├── severity_mapper.py          # 심각도 매핑
│       ├── summary_generator.py        # 한글 메시지 생성
│       ├── notification_router.py      # 알림 라우팅
│       └── deduplication_store.py      # 중복 제거
├── conf/
│   ├── detection_config.json
│   ├── alerting_rules.json
│   └── eventbridge_config.json
└── scripts/
    └── test_alerts.py
```

## 관련 문서

- [아키텍처](architecture.md)
- [설정 가이드](configuration.md)
- [심각도 분류](severity_levels.md)
- [KakaoTalk 설정](kakao_setup.md)
- [문제 해결](troubleshooting.md)
