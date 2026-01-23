# BDP Compact Agent - 아키텍처

## 시스템 구성

```mermaid
flowchart TB
    subgraph trigger["Trigger"]
        mwaa["MWAA<br/>(스케줄)"]
        api["FastAPI<br/>:8005"]
    end

    subgraph bdp_compact["BDP Compact Agent"]
        handler["Handler"]
        provider["Cost Explorer<br/>Provider"]
        detector["Cost Drift<br/>Detector"]
        pattern["Pattern<br/>Recognizers"]
        summary["Summary<br/>Generator"]
        publisher["Event<br/>Publisher"]
    end

    subgraph aws["AWS Cloud"]
        ce["Cost Explorer"]
        eb["EventBridge"]
    end

    subgraph notification["Notification"]
        kakao["KakaoTalk<br/>알람"]
        hitl["HITL<br/>Store"]
    end

    mwaa --> handler
    api --> handler

    handler --> provider
    provider --> ce

    handler --> detector
    detector --> pattern
    detector --> summary
    summary --> publisher

    publisher --> eb
    eb --> kakao
    handler --> hitl
```

## 탐지 플로우

```mermaid
flowchart LR
    start["시작"] --> fetch["비용 데이터<br/>조회"]
    fetch --> filter["최소 비용<br/>필터링"]
    filter --> ecod["PyOD ECOD<br/>탐지"]
    ecod --> ratio["Ratio 기반<br/>탐지"]
    ratio --> pattern["패턴<br/>인식"]
    pattern --> ensemble{"앙상블<br/>판정"}

    ensemble -->|이상| severity["심각도<br/>분류"]
    ensemble -->|정상| end_normal["종료"]

    severity --> summary["한글 Summary<br/>생성"]
    summary --> critical{"Critical?"}

    critical -->|Yes| hitl["HITL 요청<br/>생성"]
    critical -->|No| publish["EventBridge<br/>발행"]

    hitl --> publish
    publish --> end_anomaly["종료"]
```

## 계정 설정

### Lambda 실행 역할 권한

Lambda 실행 역할에 Cost Explorer 읽기 권한이 필요합니다:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    }
  ]
}
```

### 배포 구조

각 AWS 계정에 개별 Lambda가 배포됩니다:

```
Account A (111111111111)
├── Lambda: bdp-compact-agent
└── IAM Role: bdp-compact-execution-role
    └── Cost Explorer 읽기 권한

Account B (222222222222)
├── Lambda: bdp-compact-agent
└── IAM Role: bdp-compact-execution-role
    └── Cost Explorer 읽기 권한
```

> **참고**: Cross-account 권한 획득(STS AssumeRole)이 불필요합니다.
> 각 Lambda는 자체 계정의 Cost Explorer API에 직접 접근합니다.

## 환경 변수

### 핵심 설정

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `BDP_PROVIDER` | Provider 타입 (real/localstack/mock) | `mock` |
| `BDP_ACCOUNT_NAME` | 계정 식별 이름 (로그/알람용) | `default` |
| `BDP_SENSITIVITY` | 탐지 민감도 (0.0-1.0) | `0.7` |
| `BDP_CURRENCY` | 통화 단위 (KRW/USD) | `KRW` |
| `BDP_MIN_COST_THRESHOLD` | 최소 비용 임계값 | `10000` |
| `BDP_HITL_ON_CRITICAL` | Critical시 HITL 요청 생성 | `true` |

### 패턴 인식 설정

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `BDP_PATTERN_RECOGNITION` | 패턴 인식 활성화 | `true` |
| `BDP_PATTERN_MODE` | 모드 (shadow/active) | `active` |
| `BDP_PATTERN_MAX_ADJUSTMENT` | 최대 신뢰도 조정폭 | `0.4` |

### EventBridge 설정

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `EVENT_PROVIDER` | Event Provider (real/mock) | `mock` |
| `EVENT_BUS` | EventBridge 버스 이름 | `cd1-agent-events` |
| `AWS_REGION` | AWS 리전 | `ap-northeast-2` |

### HITL 설정

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `RDS_PROVIDER` | RDS Provider (real/mock) | `mock` |

### LocalStack 설정 (테스트용)

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `LOCALSTACK_ENDPOINT` | LocalStack 엔드포인트 | `http://localhost:4566` |
