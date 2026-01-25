# Severity Levels Guide

## 3-Tier 심각도 시스템

HDSP Monitoring은 Prometheus 알림을 3단계 심각도로 분류합니다.

### CRITICAL (🚨 심각)

**정의**: 서비스 다운 또는 데이터 손실 위험

**알림 채널**: KakaoTalk (즉시) + EventBridge

**대표 알림**:
| 알림 이름 | 설명 |
|-----------|------|
| KubePodCrashLooping | Pod가 반복적으로 재시작 |
| KubeContainerOOMKilled | 메모리 부족으로 종료됨 |
| KubeNodeNotReady | 노드가 Ready 상태가 아님 |
| TargetDown | 모니터링 대상 다운 |
| KubeAPIDown | K8s API 서버 다운 |
| EtcdClusterUnavailable | etcd 클러스터 불가용 |
| PrometheusDown | Prometheus 다운 |

**권장 조치**: 즉시 확인 및 대응

---

### HIGH (⚠️ 높음)

**정의**: 성능 저하 또는 안정성 문제

**알림 채널**: KakaoTalk (즉시) + EventBridge

**대표 알림**:
| 알림 이름 | 설명 |
|-----------|------|
| KubeNodeMemoryPressure | 노드 메모리 부족 |
| KubeNodeDiskPressure | 노드 디스크 부족 |
| KubeDeploymentReplicasMismatch | 레플리카 불일치 |
| KubePersistentVolumeFillingUp | PV 용량 부족 |
| ContainerCPUUsageHigh | 컨테이너 CPU 높음 |
| ContainerMemoryUsageHigh | 컨테이너 메모리 높음 |
| KubeContainerWaiting | 컨테이너 대기 상태 |

**권장 조치**: 빠른 확인 및 대응 계획 수립

---

### MEDIUM (📊 보통)

**정의**: 주의가 필요한 상황

**알림 채널**: EventBridge만

**대표 알림**:
| 알림 이름 | 설명 |
|-----------|------|
| KubeQuotaAlmostFull | 리소스 쿼터 임계치 도달 |
| KubeVersionMismatch | K8s 버전 불일치 |
| NodeClockSkewDetected | 노드 시간 동기화 오류 |
| KubeClientErrors | K8s 클라이언트 오류 |

**권장 조치**: 모니터링 및 적절한 시점에 대응

---

## 심각도 매핑 규칙

### 1. 알림 이름 오버라이드 (최우선)

특정 알림 이름은 항상 지정된 심각도로 매핑됩니다:

```python
ALERT_OVERRIDES = {
    "KubePodCrashLooping": CRITICAL,
    "KubeNodeMemoryPressure": HIGH,
    "KubeQuotaAlmostFull": MEDIUM,
}
```

### 2. Label 기반 매핑

Prometheus `severity` 레이블 값에 따라 매핑:

| Label 값 | 심각도 |
|----------|--------|
| critical, error, page | CRITICAL |
| warning, high, warn | HIGH |
| info, medium, low | MEDIUM |

### 3. 키워드 패턴 매칭

알림 이름에 특정 키워드가 포함되면 자동 매핑:

**CRITICAL 키워드**: down, failed, crash, oom, killed, unreachable
**HIGH 키워드**: pressure, mismatch, filling, high, degraded

### 4. 기본값

위 규칙에 해당하지 않으면 **MEDIUM**으로 분류

---

## 커스터마이징

### 알림 오버라이드 추가

```python
from src.agents.hdsp_monitoring.hdsp_monitoring.services.severity_mapper import (
    SeverityMapper,
    AlertSeverity,
)

mapper = SeverityMapper()

# 커스텀 알림을 CRITICAL로 지정
mapper.add_override("MyAppCriticalError", AlertSeverity.CRITICAL)

# 기존 오버라이드 제거
mapper.remove_override("KubeQuotaAlmostFull")  # 이제 label 기반으로 매핑
```

### 설정 파일 수정

`conf/detection_config.json`:

```json
{
  "severity_mapping": {
    "critical_alerts": [
      "KubePodCrashLooping",
      "MyCustomCriticalAlert"
    ],
    "high_alerts": [
      "KubeNodeMemoryPressure",
      "MyCustomHighAlert"
    ]
  }
}
```

---

## 알림 예시

### CRITICAL 알림 메시지

```
🚨 K8s 알림: CrashLoopBackOff
━━━━━━━━━━━━━━━━━━━━
🏷️ 클러스터: on-prem-k8s
📍 네임스페이스: spark
🔧 리소스: 파드/spark-executor-abc123
━━━━━━━━━━━━━━━━━━━━

📋 알림 내용:
Pod spark/spark-executor-abc123이 반복적으로
재시작 중입니다.

⚠️ 조치 권고:
즉시 확인이 필요합니다.
서비스에 영향을 줄 수 있는 상황입니다.

[심각도: CRITICAL | 지속시간: 25분]
```

### HIGH 알림 메시지

```
⚠️ K8s 알림: 메모리 부족
━━━━━━━━━━━━━━━━━━━━
🏷️ 클러스터: on-prem-k8s
📍 네임스페이스: kube-system
🔧 리소스: 노드/worker-node-3
━━━━━━━━━━━━━━━━━━━━

📋 알림 내용:
노드 메모리 사용률이 90%를 초과했습니다.

📢 조치 권고:
빠른 확인을 권장합니다.
성능 저하 또는 안정성 문제가 발생할 수 있습니다.

[심각도: HIGH | 지속시간: 15분]
```
