# BDP Agent Architecture

## Overview

BDP (Big Data Platform) Agent는 AWS Lambda 기반 서버리스 아키텍처로 구현된 지능형 로그 분석 및 자동 복구 시스템입니다.

### Provider Abstraction Pattern

BDP Agent는 Provider Abstraction 패턴을 사용하여 LLM과 AWS 서비스를 추상화합니다. 이를 통해 프로덕션(On-Premise/AWS)과 테스트(Public/Mock) 환경에서 동일한 코드로 동작합니다.

#### LLM Provider

| 환경 | Provider | 설명 | 환경 변수 |
|------|----------|------|----------|
| **On-Premise** | VLLMProvider | 자체 호스팅 LLM 서버 (OpenAI Compatible API) | `LLM_PROVIDER=vllm` |
| **Public** | GeminiProvider | Google Gemini 2.5 Pro/Flash API | `LLM_PROVIDER=gemini` |
| **Mock** | MockLLMProvider | 테스트용 내장 Mock | `LLM_MOCK=true` |

#### AWS Provider

| 환경 | Provider | 설명 | 환경 변수 |
|------|----------|------|----------|
| **Production** | AWS*Provider | 실제 AWS 서비스 호출 | (기본값) |
| **Mock** | Mock*Provider | AWS 없이 로직 테스트 | `AWS_MOCK=true` |

**Mock 지원 AWS 서비스:**
- CloudWatch (Metrics, Logs, Anomaly Detection)
- DynamoDB (Deduplication, Workflow State)
- RDS Data API (Unified Logs)
- Lambda (Function Invocation)
- EventBridge (Event Publishing)
- Step Functions (Workflow Execution)

### 핵심 특징
- **LangGraph Agent**: 동적 ReAct 루프, Reflect & Replan 패턴
- **하이브리드 오케스트레이션**: Step Functions (외부 워크플로우) + LangGraph (내부 에이전트)
- **신뢰도 기반 자동화**: 0.85+ 자동 실행, 0.5-0.85 승인 요청
- **비용 최적화**: Field Indexing, Hierarchical Summarization, Deduplication
- **서버리스**: Lambda + Step Functions + MWAA

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            BDP Agent Architecture                            │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │      MWAA        │
                              │  (Airflow DAG)   │
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
| Runtime | Python 3.12 |
| Architecture | ARM64 (Graviton2) |
| Memory | 512MB |
| Timeout | 60s |
| Trigger | MWAA (Airflow DAG) |

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
| Runtime | Python 3.12 |
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
| Runtime | Python 3.12 |
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

## Provider Architecture

### Provider Pattern Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Provider Abstraction Layer                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         LLMClient                                    │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │ VLLMProvider│  │GeminiProvider│ │MockLLMProvider│                │    │
│  │  │ (On-Prem)   │  │ (Public)    │  │ (Test)      │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         AWSClient                                    │    │
│  │  ┌───────────────────────────────────────────────────────────────┐  │    │
│  │  │                    AWS Providers (Production)                  │  │    │
│  │  │  CloudWatch | DynamoDB | RDS Data | Lambda | EventBridge | SFN │  │    │
│  │  └───────────────────────────────────────────────────────────────┘  │    │
│  │  ┌───────────────────────────────────────────────────────────────┐  │    │
│  │  │                    Mock Providers (Testing)                    │  │    │
│  │  │  MockCW    | MockDDB  | MockRDS  | MockLam | MockEB    |MockSFN│  │    │
│  │  └───────────────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Environment Configuration

```bash
# 프로덕션 환경 (On-Premise vLLM + AWS)
export LLM_PROVIDER=vllm
export VLLM_BASE_URL=http://your-vllm-server:8000/v1
export VLLM_MODEL_NAME=your-model-name
# AWS_MOCK은 설정하지 않음 (기본값: AWS 사용)

# 개발 환경 (Public Gemini + Mock AWS)
export LLM_PROVIDER=gemini
export GEMINI_API_KEY=your-api-key
export GEMINI_MODEL_ID=gemini-2.5-flash
export AWS_MOCK=true

# 로컬 테스트 환경 (전체 Mock)
export LLM_MOCK=true
export AWS_MOCK=true
```

### Provider Selection Logic

```python
# LLMClient 초기화
if os.environ.get('LLM_MOCK', '').lower() == 'true':
    provider = MockLLMProvider()     # 외부 의존성 없음
elif os.environ.get('LLM_PROVIDER') == 'gemini':
    provider = GeminiProvider()      # Google Gemini API
else:
    provider = VLLMProvider()        # On-Prem vLLM 서버

# AWSClient 초기화
if os.environ.get('AWS_MOCK', '').lower() == 'true':
    cloudwatch = MockCloudWatchProvider()
    dynamodb = MockDynamoDBProvider()
    # ... 모든 AWS 서비스 Mock 사용
else:
    cloudwatch = AWSCloudWatchProvider()
    dynamodb = AWSDynamoDBProvider()
    # ... 실제 AWS 서비스 사용
```

---

## Agent Framework (LangGraph)

### Why LangGraph?

현재 Step Functions 기반 아키텍처는 **정적 워크플로우**로, 분기와 루프가 미리 정의되어 있습니다. 그러나 ReAct 패턴과 Reflect/Replan 루프는 **LLM이 다음 행동을 동적으로 결정**하는 에이전트 패턴이 더 적합합니다.

| 구분 | Step Functions | LangGraph |
|------|----------------|-----------|
| 워크플로우 유형 | 정적 (사전 정의) | 동적 (LLM 결정) |
| 분기 조건 | 명시적 Choice 상태 | LLM 추론 기반 |
| 도구 호출 | Lambda 단위 | 세분화된 Tool 단위 |
| 재시도/Replan | 고정 로직 | 적응형 |
| 적합 영역 | 오케스트레이션, 승인, 실행 | 분석, 추론, 계획 |

### Hybrid Architecture

Step Functions와 LangGraph를 결합하여 각 컴포넌트의 강점을 활용합니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Hybrid Orchestration Architecture                     │
└─────────────────────────────────────────────────────────────────────────────┘

                           ┌──────────────────┐
                           │      MWAA        │
                           │  (Airflow DAG)   │
                           └────────┬─────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                         Step Functions (Outer Orchestration)                   │
│                                                                                │
│   ┌──────────┐         ┌──────────────────────────────────┐        ┌────────┐│
│   │ Detect   │────────▶│                                  │───────▶│Execute ││
│   │ Anomaly  │         │      LangGraph Agent             │        │Actions ││
│   │ (Lambda) │         │      (Analysis Lambda)           │        │(Lambda)││
│   └──────────┘         │                                  │        └────────┘│
│                        │  ┌─────────────────────────────┐ │             │     │
│                        │  │        ReAct Loop           │ │             │     │
│                        │  │  ┌───────┐    ┌──────────┐  │ │             │     │
│                        │  │  │ Think │───▶│   Act    │  │ │             ▼     │
│                        │  │  └───────┘    └────┬─────┘  │ │       ┌────────┐ │
│                        │  │       ▲            │        │ │       │Reflect │ │
│                        │  │       │            ▼        │ │       │(Agent) │ │
│                        │  │  ┌────┴────┐  ┌────────┐   │ │       └───┬────┘ │
│                        │  │  │ Reflect │◀─│Observe │   │ │           │      │
│                        │  │  └─────────┘  └────────┘   │ │           │      │
│                        │  └─────────────────────────────┘ │           │      │
│                        │                                  │           │      │
│                        │  Tools:                          │           ▼      │
│                        │  - query_cloudwatch              │    ┌───────────┐ │
│                        │  - query_rds_logs                │    │  Replan?  │ │
│                        │  - search_knowledge_base         │    └─────┬─────┘ │
│                        │  - analyze_metrics               │          │       │
│                        │  - evaluate_confidence           │          │       │
│                        └──────────────────────────────────┘          │       │
│                                                                       │       │
│                              ◀────────────────────────────────────────┘       │
└───────────────────────────────────────────────────────────────────────────────┘
```

### LangGraph Agent 구성

#### State Definition

```python
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    """LangGraph Agent 상태 정의."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    anomaly_data: dict           # 감지된 이상 현상 정보
    log_summary: str             # 계층적 요약된 로그
    analysis_result: dict        # 분석 결과
    confidence_score: float      # 신뢰도 점수
    remediation_plan: dict       # 복구 계획
    iteration_count: int         # 현재 반복 횟수
    max_iterations: int          # 최대 반복 횟수
```

#### Tool Definitions

```python
from langchain_core.tools import tool

@tool
def query_cloudwatch_metrics(namespace: str, metric_name: str, period: int) -> dict:
    """CloudWatch 메트릭을 조회합니다."""
    pass

@tool
def query_rds_logs(service_filter: list, severity: str, time_range_minutes: int) -> list:
    """RDS 통합 로그를 조회합니다 (Field Indexing 사용)."""
    pass

@tool
def search_knowledge_base(query: str, top_k: int = 5) -> list:
    """지식 베이스에서 관련 문서를 검색합니다."""
    pass

@tool
def analyze_patterns(logs: list, metrics: dict) -> dict:
    """로그와 메트릭 패턴을 분석합니다."""
    pass

@tool
def evaluate_confidence(analysis: dict, evidence: list) -> float:
    """분석 결과의 신뢰도를 평가합니다."""
    pass

@tool
def propose_remediation(root_cause: str, context: dict) -> dict:
    """복구 조치를 제안합니다."""
    pass
```

#### Graph Definition

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

def create_analysis_agent():
    """LangGraph 분석 에이전트 생성."""

    # 노드 정의
    def think_node(state: AgentState) -> AgentState:
        """현재 상태를 분석하고 다음 행동 결정."""
        pass

    def act_node(state: AgentState) -> AgentState:
        """도구를 사용하여 정보 수집."""
        pass

    def observe_node(state: AgentState) -> AgentState:
        """도구 실행 결과 관찰."""
        pass

    def reflect_node(state: AgentState) -> AgentState:
        """분석 결과 검토 및 신뢰도 평가."""
        pass

    def should_continue(state: AgentState) -> str:
        """계속 분석할지 결정."""
        if state["confidence_score"] >= 0.7:
            return "complete"
        if state["iteration_count"] >= state["max_iterations"]:
            return "complete"
        return "continue"

    # 그래프 구성
    workflow = StateGraph(AgentState)

    workflow.add_node("think", think_node)
    workflow.add_node("act", ToolNode(tools))
    workflow.add_node("observe", observe_node)
    workflow.add_node("reflect", reflect_node)

    workflow.set_entry_point("think")
    workflow.add_edge("think", "act")
    workflow.add_edge("act", "observe")
    workflow.add_edge("observe", "reflect")

    workflow.add_conditional_edges(
        "reflect",
        should_continue,
        {
            "continue": "think",
            "complete": END
        }
    )

    return workflow.compile()
```

### Step Functions Integration

LangGraph Agent는 Lambda 내부에서 실행되며, Step Functions는 외부 오케스트레이션을 담당합니다.

```json
{
  "Comment": "BDP Agent Hybrid Workflow",
  "StartAt": "DetectAnomalies",
  "States": {
    "DetectAnomalies": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:bdp-detection",
      "Next": "CheckAnomalies"
    },
    "CheckAnomalies": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.anomalies_detected",
          "BooleanEquals": true,
          "Next": "AnalyzeWithAgent"
        }
      ],
      "Default": "NoAnomalies"
    },
    "AnalyzeWithAgent": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:bdp-analysis",
      "Comment": "LangGraph Agent runs inside this Lambda",
      "Next": "EvaluateConfidence"
    },
    "EvaluateConfidence": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.confidence_score",
          "NumericGreaterThanEquals": 0.85,
          "Next": "AutoExecute"
        },
        {
          "Variable": "$.confidence_score",
          "NumericGreaterThanEquals": 0.5,
          "Next": "RequestApproval"
        }
      ],
      "Default": "Escalate"
    }
  }
}
```

### LangGraph vs 다른 Agent Framework 비교

| Framework | 장점 | 단점 | BDP Agent 적합도 |
|-----------|------|------|------------------|
| **LangGraph** | 상태 기반 그래프, 루프 지원, LangChain 호환 | 학습 곡선 | ⭐⭐⭐ 최적 |
| Claude Agent SDK | Anthropic 최적화, 간단한 API | Claude 전용 | ⭐⭐ vLLM 미지원 |
| CrewAI | 멀티 에이전트 협업 | 단일 에이전트에 과도 | ⭐ 과도한 복잡도 |
| AutoGen | 대화형 협업 | 설정 복잡 | ⭐ 부적합 |

### 구현 로드맵

| Phase | 내용 | 우선순위 |
|-------|------|----------|
| Phase 1 | LangGraph 기본 통합, Tool 정의 | 높음 |
| Phase 2 | ReAct 루프 구현, 신뢰도 평가 | 높음 |
| Phase 3 | Reflect & Replan 루프 | 중간 |
| Phase 4 | Knowledge Base 연동 (RAG) | 중간 |
| Phase 5 | 멀티 에이전트 확장 (필요시) | 낮음 |

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
| bdp-detection | 512MB | 60s | ARM64 | MWAA (Airflow DAG) |
| bdp-analysis | 1024MB | 120s | ARM64 | Step Functions |
| bdp-remediation | 512MB | 60s | ARM64 | Step Functions |
| bdp-approval | 256MB | 30s | ARM64 | API Gateway |

### DynamoDB Tables

| Table | Billing | TTL | Purpose |
|-------|---------|-----|---------|
| bdp-anomaly-tracking | On-Demand | 7 days | Deduplication |
| bdp-workflow-state | On-Demand | 30 days | Workflow state |
| bdp-remediation-history | On-Demand | 90 days | Audit trail |

### MWAA (Amazon Managed Workflows for Apache Airflow)

| DAG | Schedule | Target |
|-----|----------|--------|
| bdp_detection_dag | Configurable (Airflow cron) | bdp-detection Lambda / Step Functions |

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
