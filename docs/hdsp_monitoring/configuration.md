# HDSP Monitoring Configuration

## 환경 변수

### Alertmanager 연결

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ALERTMANAGER_URL` | `http://localhost:9093` | Alertmanager API URL |
| `PROMETHEUS_URL` | `http://localhost:9090` | Prometheus URL (참조용) |
| `PROMETHEUS_MOCK` | `false` | Mock 모드 활성화 |

### 클러스터 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `HDSP_CLUSTER_NAME` | `on-prem-k8s` | 클러스터 식별자 |
| `HDSP_INCLUDE_NAMESPACES` | (all) | 포함할 네임스페이스 (쉼표 구분) |
| `HDSP_EXCLUDE_NAMESPACES` | `test-*,dev-*` | 제외할 네임스페이스 |

### KakaoTalk 알림

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `KAKAO_ENABLED` | `true` | KakaoTalk 알림 활성화 |
| `KAKAO_REST_API_KEY` | - | Kakao REST API 키 |

### EventBridge 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `EVENT_BUS` | `cd1-agent-events` | EventBridge 버스 이름 |
| `EVENTBRIDGE_ENABLED` | `true` | EventBridge 활성화 |

### 기타

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NOTIFICATION_MOCK` | `false` | 알림 Mock 모드 |
| `LOG_LEVEL` | `INFO` | 로그 레벨 |

## 설정 파일

### conf/detection_config.json

알림 탐지 관련 설정:

```json
{
  "alertmanager": {
    "url": "${ALERTMANAGER_URL:-http://localhost:9093}",
    "timeout_seconds": 30
  },
  "severity_mapping": {
    "critical_alerts": ["KubePodCrashLooping", "KubeContainerOOMKilled"],
    "high_alerts": ["KubeNodeMemoryPressure", "KubeDeploymentReplicasMismatch"],
    "label_mapping": {
      "critical": "critical",
      "warning": "high",
      "info": "medium"
    }
  },
  "deduplication": {
    "enabled": true,
    "window_seconds": 300,
    "repeat_interval_seconds": 3600
  },
  "grouping": {
    "group_by": ["namespace", "alertname"],
    "group_wait_seconds": 30
  },
  "rate_limiting": {
    "max_notifications_per_minute": 10
  },
  "namespaces": {
    "include": null,
    "exclude": ["test-*", "dev-*"]
  }
}
```

### conf/alerting_rules.json

알림 라우팅 규칙:

```json
{
  "routing": {
    "critical": {
      "primary": "kakao",
      "fallback": "eventbridge",
      "immediate": true
    },
    "high": {
      "primary": "kakao",
      "fallback": "eventbridge",
      "immediate": true
    },
    "medium": {
      "primary": "eventbridge",
      "fallback": null,
      "immediate": false
    }
  },
  "channels": {
    "kakao": {
      "enabled": true,
      "max_message_length": 1000
    },
    "eventbridge": {
      "enabled": true
    }
  }
}
```

### conf/eventbridge_config.json

EventBridge 이벤트 설정:

```json
{
  "EventBusName": "cd1-agent-events",
  "Source": "cd1-agent.hdsp-monitoring",
  "DetailType": "K8s Alert"
}
```

## 심각도 매핑 커스터마이징

### 알림 이름 오버라이드 추가

```python
from src.agents.hdsp_monitoring.hdsp_monitoring.services.severity_mapper import SeverityMapper
from src.agents.hdsp_monitoring.hdsp_monitoring.services.models import AlertSeverity

mapper = SeverityMapper()

# 커스텀 알림을 CRITICAL로 매핑
mapper.add_override("MyCustomCriticalAlert", AlertSeverity.CRITICAL)
```

### 네임스페이스 필터링

```python
from src.agents.hdsp_monitoring.hdsp_monitoring.services.alert_processor import AlertProcessor

processor = AlertProcessor(
    include_namespaces=["production", "staging"],
    exclude_namespaces=["test-*", "dev-*", "sandbox"],
)
```

## Lambda 설정 예시

### SAM Template

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  HDSPMonitoringFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: src.agents.hdsp_monitoring.handler.handler
      Runtime: python3.11
      Timeout: 60
      MemorySize: 256
      Environment:
        Variables:
          ALERTMANAGER_URL: !Ref AlertmanagerUrl
          HDSP_CLUSTER_NAME: !Ref ClusterName
          KAKAO_ENABLED: "true"
          EVENT_BUS: !Ref EventBus
      Events:
        ScheduledCheck:
          Type: Schedule
          Properties:
            Schedule: rate(1 minute)
```

### EventBridge Rule 예시

```yaml
# CRITICAL 알림 대상 규칙
HDSPCriticalAlertRule:
  Type: AWS::Events::Rule
  Properties:
    EventBusName: cd1-agent-events
    EventPattern:
      source:
        - cd1-agent.hdsp-monitoring
      detail-type:
        - K8s Alert
      detail:
        severity_level:
          - critical
    Targets:
      - Arn: !GetAtt AlertHandlerFunction.Arn
        Id: CriticalAlertHandler
```
