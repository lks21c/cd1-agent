# BDP Agent Architecture

## Overview

BDP (Big Data Platform) Agent는 AWS Lambda 기반 서버리스 아키텍처로 구현된 지능형 로그 분석 및 자동 복구 시스템입니다.

### LLM Provider 아키텍처

| 환경 | Provider | 설명 |
|------|----------|------|
| **On-Premise** | vLLM | 자체 호스팅 LLM 서버 (OpenAI Compatible API) |
| **Public/Mock** | Gemini | Google Gemini 2.5 Pro/Flash API |

### 핵심 특징
- **ReAct 패턴**: Plan → Execute → Reflect → Replan 사이클
- **신뢰도 기반 자동화**: 0.85+ 자동 실행, 0.5-0.85 승인 요청
- **비용 최적화**: Field Indexing, Hierarchical Summarization, Deduplication
- **서버리스**: Lambda + Step Functions + EventBridge

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            BDP Agent Architecture                            │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │   EventBridge    │
                              │   (5-10분 주기)   │
                              └────────┬─────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Detection Phase                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  CloudWatch  │    │     RDS      │    │  CloudWatch  │                   │
│  │   Metrics    │    │ 통합로그     │    │    Logs      │                   │
│  │ + Anomaly    │    │(Field Index) │    │              │                   │
│  │  Detection   │    │              │    │              │                   │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                   │
│         │                   │                   │                            │
│         └───────────────────┼───────────────────┘                            │
│                             ▼                                                │
│                   ┌──────────────────┐                                       │
│                   │  Lambda:         │                                       │
│                   │  Detection       │──────▶ DynamoDB (Deduplication)      │
│                   │  (512MB, ARM64)  │                                       │
│                   └────────┬─────────┘                                       │
└────────────────────────────┼─────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Step Functions Orchestration                          │
│                                                                               │
│    ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐              │
│    │ Detect  │────▶│ Analyze │────▶│Evaluate │────▶│Execute/ │              │
│    │Anomaly  │     │RootCause│     │Confidence│    │ Approve │              │
│    └─────────┘     └─────────┘     └─────────┘     └─────────┘              │
│                          │                              │                    │
│                          ▼                              ▼                    │
│                   ┌─────────────┐              ┌─────────────┐               │
│                   │ vLLM/Gemini │              │  Remediate  │               │
│                   │    (LLM)    │              │   Actions   │               │
│                   └─────────────┘              └─────────────┘               │
│                                                      │                       │
│                                                      ▼                       │
│                                               ┌─────────────┐                │
│                                               │   Reflect   │                │
│                                               │  & Replan   │────┐           │
│                                               └─────────────┘    │           │
│                                                      ▲           │           │
│                                                      └───────────┘           │
└──────────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Remediation Actions                                 │
│                                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Lambda     │  │     RDS      │  │ Auto Scaling │  │  EventBridge │     │
│  │   Restart    │  │  Parameter   │  │   Adjust     │  │    Event     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                               │              │
│                                                               ▼              │
│                                                    ┌──────────────────┐      │
│                                                    │ 외부 알림 시스템  │      │
│                                                    │ (Slack, Teams등) │      │
│                                                    └──────────────────┘      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Detection Layer

#### Lambda: bdp-detection
| 속성 | 값 |
|------|-----|
| Runtime | Python 3.11 |
| Architecture | ARM64 (Graviton2) |
| Memory | 512MB |
| Timeout | 60s |
| Trigger | EventBridge (configurable 5-10 min) |

**주요 기능**:
1. CloudWatch Anomaly Detection 결과 조회
2. RDS 통합로그 쿼리 (Field Indexing 사용)
3. CloudWatch Logs 필터링
4. Deduplication (DynamoDB 기반)

#### 데이터 소스 통합

```python
# RDS 통합로그 스키마 예시
{
    "id": "log-uuid",
    "timestamp": "2024-01-15T10:30:00Z",
    "service_name": "api-gateway",
    "log_level": "ERROR",
    "message": "Connection timeout",
    "metadata": "{\"request_id\": \"abc-123\", \"user_id\": \"user-456\"}"  # JSON string
}
```

### 2. Analysis Layer

#### Lambda: bdp-analysis
| 속성 | 값 |
|------|-----|
| Runtime | Python 3.11 |
| Architecture | ARM64 |
| Memory | 1024MB |
| Timeout | 120s |
| Trigger | Step Functions |

**주요 기능**:
1. Hierarchical Log Summarization (토큰 80-90% 절감)
2. Knowledge Base 로딩 (Mini RAG)
3. vLLM 또는 Gemini 분석 요청
4. Reflection Engine을 통한 신뢰도 평가

#### LLM Integration

**vLLM (On-Premise)** - OpenAI Compatible API:
```python
# vLLM 설정
VLLM_BASE_URL = "http://your-vllm-server:8000/v1"
VLLM_MODEL_NAME = "your-model-name"

# 분석 요청 구조 (OpenAI Compatible)
{
    "model": VLLM_MODEL_NAME,
    "max_tokens": 4096,
    "temperature": 0.3,
    "messages": [
        {"role": "user", "content": formatted_prompt}
    ]
}
```

**Gemini (Public Mock)** - Google AI API:
```python
# Gemini 설정
GEMINI_MODEL_ID = "gemini-2.5-pro"  # 또는 "gemini-2.5-flash"

# 분석 요청 구조
{
    "contents": [
        {"role": "user", "parts": [{"text": formatted_prompt}]}
    ],
    "generationConfig": {
        "maxOutputTokens": 4096,
        "temperature": 0.3
    }
}
```

### 3. Remediation Layer

#### Lambda: bdp-remediation
| 속성 | 값 |
|------|-----|
| Runtime | Python 3.11 |
| Architecture | ARM64 |
| Memory | 512MB |
| Timeout | 60s |
| Trigger | Step Functions |

**지원 액션**:

| Action Type | 설명 | 예시 파라미터 |
|-------------|------|---------------|
| `lambda_restart` | Lambda 함수 재시작 | `{"function_name": "api-handler"}` |
| `rds_parameter` | RDS 파라미터 변경 | `{"parameter_name": "max_connections", "new_value": "200"}` |
| `auto_scaling` | Auto Scaling 조정 | `{"resource_type": "ECS", "action": "scale_up", "amount": 2}` |
| `eventbridge_event` | 이벤트 발행 | `{"event_type": "ALERT", "detail": {...}}` |

### 4. State Management

#### DynamoDB Tables

**bdp-anomaly-tracking**
```
PK: signature (String) - Anomaly 해시
Attributes:
  - last_seen (String)
  - anomaly_type (String)
  - occurrence_count (Number)
  - ttl (Number) - 7일 후 자동 삭제
```

**bdp-workflow-state**
```
PK: workflow_id (String)
SK: timestamp (String)
Attributes:
  - phase (String)
  - analysis_result (Map)
  - remediation_status (String)
```

**bdp-remediation-history**
```
PK: resource_id (String)
SK: execution_time (String)
Attributes:
  - action_type (String)
  - parameters (Map)
  - result (Map)
  - rollback_available (Boolean)
```

---

## Data Flow

### 1. Detection Flow

```
EventBridge Trigger (5-10 min)
         │
         ▼
┌─────────────────────────────────────────────┐
│ 1. Query Pre-aggregated Metrics             │
│    - CloudWatch GetMetricData               │
│    - Check anomaly bands                    │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 2. Query RDS Logs (if anomaly detected)     │
│    - Use Field Indexing (67% cost reduction)│
│    - Parse JSON string columns              │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 3. Deduplicate Anomalies                    │
│    - Check DynamoDB for recent occurrences  │
│    - Filter out duplicates (1hr window)     │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
         Step Functions Start
```

### 2. Analysis Flow

```
Step Functions: AnalyzeRootCause
         │
         ▼
┌─────────────────────────────────────────────┐
│ 1. Hierarchical Summarization               │
│    - Group by error type                    │
│    - Sample representative logs (max 5)     │
│    - Extract key fields only                │
│    Result: 80-90% token reduction           │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 2. Load Knowledge Base                      │
│    - Detect relevant library/error patterns │
│    - Load remediation playbooks             │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 3. Format Analysis Prompt                   │
│    - Inject anomaly data                    │
│    - Add log summary                        │
│    - Include knowledge context              │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 4. Invoke Bedrock Claude                    │
│    - Send formatted prompt                  │
│    - Parse JSON response                    │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 5. Reflection & Confidence Scoring          │
│    - Evaluate evidence sufficiency          │
│    - Check logical consistency              │
│    - Assess actionability                   │
│    - Calculate overall confidence (0.0-1.0) │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
         Return Analysis Result
```

### 3. Remediation Decision Flow

```
                  Analysis Result
                        │
                        ▼
              ┌─────────────────┐
              │ Confidence >= 0.85? │
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          │ Yes        │            │ No
          ▼            │            ▼
    ┌───────────┐      │     ┌───────────────┐
    │ Auto      │      │     │ Confidence    │
    │ Execute   │      │     │ >= 0.5?       │
    └─────┬─────┘      │     └───────┬───────┘
          │            │             │
          │            │    ┌────────┼────────┐
          │            │    │ Yes    │        │ No
          │            │    ▼        │        ▼
          │            │ ┌────────┐  │  ┌───────────┐
          │            │ │Request │  │  │ Escalate  │
          │            │ │Approval│  │  │ to Human  │
          │            │ └───┬────┘  │  └───────────┘
          │            │     │       │
          │            │     ▼       │
          │            │ ┌────────┐  │
          │            │ │Approved│  │
          │            │ │?       │  │
          │            │ └───┬────┘  │
          │            │     │       │
          └────────────┼─────┘       │
                       ▼             │
                 ┌───────────┐       │
                 │ Execute   │       │
                 │Remediation│       │
                 └─────┬─────┘       │
                       │             │
                       ▼             │
                 ┌───────────┐       │
                 │ Reflect   │       │
                 │ on Result │       │
                 └─────┬─────┘       │
                       │             │
              ┌────────┼─────────────┘
              │        │
              ▼        ▼
        ┌───────────────────┐
        │ Success?          │
        └────────┬──────────┘
                 │
        ┌────────┼────────┐
        │ Yes    │        │ No
        ▼        │        ▼
   ┌─────────┐   │   ┌─────────┐
   │ Notify  │   │   │ Replan  │
   │ Success │   │   │ & Retry │
   └─────────┘   │   └─────────┘
                 │
              [End]
```

---

## AWS Resources Summary

### Lambda Functions

| Function | Memory | Timeout | Architecture | Trigger |
|----------|--------|---------|--------------|---------|
| bdp-detection | 512MB | 60s | ARM64 | EventBridge |
| bdp-analysis | 1024MB | 120s | ARM64 | Step Functions |
| bdp-remediation | 512MB | 60s | ARM64 | Step Functions |
| bdp-approval | 256MB | 30s | ARM64 | API Gateway |
| bdp-warmup | 128MB | 5s | ARM64 | EventBridge (5min) |

### DynamoDB Tables

| Table | Billing | TTL | Purpose |
|-------|---------|-----|---------|
| bdp-anomaly-tracking | On-Demand | 7 days | Deduplication |
| bdp-workflow-state | On-Demand | 30 days | Workflow state |
| bdp-remediation-history | On-Demand | 90 days | Audit trail |

### EventBridge Rules

| Rule | Schedule | Target |
|------|----------|--------|
| bdp-detection-schedule | rate(5 minutes) | bdp-detection |
| bdp-warmup-schedule | rate(5 minutes) | bdp-warmup |

### Step Functions

| State Machine | Purpose |
|---------------|---------|
| bdp-main-workflow | Main detection → analysis → remediation flow |
| bdp-approval-workflow | Human approval sub-workflow |

### IAM Roles

| Role | Permissions |
|------|-------------|
| bdp-detection-role | CloudWatch Logs, RDS Data API, DynamoDB |
| bdp-analysis-role | VPC (vLLM 접근), Secrets Manager (API Keys), S3 (knowledge base), DynamoDB |
| bdp-remediation-role | Lambda, RDS, Auto Scaling, EventBridge |

> **Note**: vLLM 사용 시 Lambda가 On-Prem 서버에 접근하려면 VPC 설정 및 적절한 네트워크 구성이 필요합니다.

---

## Security Considerations

### IAM Best Practices
- 최소 권한 원칙 적용
- 리소스 기반 정책으로 범위 제한
- 크로스 계정 접근 시 AssumeRole 사용

### Data Protection
- DynamoDB 암호화 활성화 (AWS managed key)
- CloudWatch Logs 암호화
- Lambda 환경 변수 암호화 (KMS)

### Audit & Compliance
- CloudTrail로 API 호출 로깅
- remediation-history 테이블로 변경 추적
- Step Functions 실행 로그 보존

---

## Scalability & Reliability

### Auto Scaling
- Lambda 동시성 자동 확장
- DynamoDB On-Demand 용량 모드
- Step Functions 무제한 동시 실행

### Error Handling
- Lambda 재시도 (Step Functions Retry)
- DLQ (Dead Letter Queue) 설정
- 장애 시 Slack/Teams 알림

### Disaster Recovery
- Multi-AZ DynamoDB
- Lambda 코드 S3 버저닝
- CloudFormation/CDK IaC

---

## Monitoring

### CloudWatch Metrics
- Lambda: Invocations, Duration, Errors, Throttles
- Step Functions: ExecutionsFailed, ExecutionsSucceeded
- DynamoDB: ReadCapacityUnits, WriteCapacityUnits

### CloudWatch Alarms
- Lambda 에러율 > 5%
- Step Functions 실패율 > 10%
- LLM API 지연 > 10초 (vLLM/Gemini)

### Dashboards
- 이상 감지 현황
- 자동 복구 성공률
- 비용 추이
