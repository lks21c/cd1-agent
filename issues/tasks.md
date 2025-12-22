# CD1 Agent Tasks

## 진행 상태
- [ ] 대기 (Pending)
- [x] 완료 (Completed)
- [-] 취소 (Cancelled)

---

## Tasks

### ~~1. Review confidence-based decision flow~~
- **상태**: 완료
- **완료일**: 2024-12-09
- **설명**: Auto-execute 기능 비활성화, 모든 조치는 승인 후 실행으로 단순화
- **변경 사항**:
  - Auto-execute (0.85+) 제거 → 모든 조치는 approval 필요
  - Confidence >= 0.5: 승인 요청
  - Confidence < 0.5: 에스컬레이션
  - README.md: Decision Flow 섹션 업데이트
  - docs/ARCHITECTURE.md: 신뢰도 기반 자동화 → 승인 기반 실행
  - step_functions/bdp_workflow.asl.json: AutoExecuteRemediation 상태 제거
  - src/models/analysis_result.py: auto_execute 속성 항상 False 반환
  - src/handlers/analysis_handler.py: _trigger_remediation 메서드 제거
  - src/agent/nodes.py: 자동 실행 로직 제거
  - tests/test_models.py, tests/test_handlers.py: 테스트 업데이트

### ~~2. Reorganize features (Multi-Agent Architecture)~~
- **상태**: 완료
- **완료일**: 2024-12-10
- **설명**: 단일 에이전트 → 4개 서브 에이전트 멀티 아키텍처로 분리
- **우선순위**: Medium
- **관련 파일**: `README.md`, `docs/ARCHITECTURE.md`, `docs/HDSP_DETECTION.md`, `src/`
- **서브 에이전트 구성**:
  - BDP Agent: AWS CloudWatch 로그/메트릭 이상 감지
  - HDSP Agent: On-Prem K8s Prometheus 메트릭 장애 감지
  - Cost Agent: AWS Cost Explorer 비용 이상 탐지
  - Drift Agent: AWS 설정 Git Baseline 드리프트 감지

#### Sub-Tasks

##### ~~2.1 문서 업데이트~~
- **상태**: 완료
- **완료일**: 2024-12-10
- **변경 사항**:
  - README.md: Overview, Architecture, Lambda Functions, MWAA DAG 섹션 업데이트
  - docs/ARCHITECTURE.md: 멀티 에이전트 오케스트레이션 다이어그램, Detection Layer 4개 분리
  - docs/HDSP_DETECTION.md: HDSP Agent 문서 신규 생성 (On-Prem K8s 장애 감지)
  - docs/CONFIG_DRIFT_DETECTION.md: Drift Agent 명칭 추가
  - docs/COST_ANOMALY_DETECTION.md: Cost Agent 명칭 추가

##### ~~2.2 HDSP Agent 구현~~
- **상태**: 완료
- **완료일**: 2024-12-10
- **우선순위**: High
- **설명**: On-Prem K8s Prometheus 메트릭 수집 및 장애 감지 구현
- **구현 항목**:
  - [x] `src/services/prometheus_client.py`: Prometheus/VictoriaMetrics 클라이언트 (Provider 추상화)
  - [x] `src/services/hdsp_anomaly_detector.py`: K8s 이상 탐지 로직 (Pod/Node/Resource)
  - [x] `src/handlers/hdsp_detection_handler.py`: Lambda 핸들러
  - [x] `step_functions/bdp_hdsp_workflow.asl.json`: HDSP Agent Step Functions 정의
  - [x] `tests/test_hdsp_detection.py`: 단위 테스트 (30 passed, 8 skipped)
- **탐지 대상**:
  - Pod 장애: CrashLoopBackOff, OOMKilled, 재시작 횟수
  - Node 압력: MemoryPressure, DiskPressure, NotReady
  - 리소스 이상: CPU/Memory 임계값 초과

##### ~~2.3 Cost Agent 구현 보완~~
- **상태**: 완료
- **완료일**: 2024-12-10
- **우선순위**: Medium
- **설명**: 기존 Cost Detection을 독립 에이전트로 분리 및 Step Functions 연동
- **구현 항목**:
  - [x] `src/handlers/cost_detection_handler.py`: Lambda 핸들러 (BaseHandler 패턴)
  - [x] `step_functions/bdp_cost_workflow.asl.json`: Cost Agent Step Functions 정의
  - [x] `dags/bdp_cost_detection_dag.py`: MWAA DAG 연동

##### ~~2.4 Drift Agent 구현 보완~~
- **상태**: 완료
- **완료일**: 2024-12-10
- **우선순위**: Medium
- **설명**: 기존 Drift Detection을 독립 에이전트로 분리 및 Step Functions 연동
- **구현 항목**:
  - [x] `step_functions/bdp_drift_workflow.asl.json`: Drift Agent Step Functions 정의
  - [x] `dags/bdp_drift_detection_dag.py`: MWAA DAG 연동

##### ~~2.5 MWAA DAG 구현~~
- **상태**: 완료
- **완료일**: 2024-12-10
- **우선순위**: High
- **설명**: 4개 에이전트별 Airflow DAG 구현 (5분 주기 스케줄)
- **구현 항목**:
  - [x] `dags/bdp_detection_dag.py`: BDP Agent DAG
  - [x] `dags/bdp_hdsp_detection_dag.py`: HDSP Agent DAG
  - [x] `dags/bdp_cost_detection_dag.py`: Cost Agent DAG
  - [x] `dags/bdp_drift_detection_dag.py`: Drift Agent DAG
- **DAG 기능**:
  - Lambda 함수 호출 → 탐지 결과 확인 → 심각도 분기 → Step Functions 시작

### ~~3. Evaluate DynamoDB necessity~~
- **상태**: 완료
- **완료일**: 2024-12-10
- **설명**: DynamoDB 필수 여부 검토 및 대안 고려
- **우선순위**: High
- **관련 파일**: `docs/ARCHITECTURE.md`, `src/`
- **검토 결과** (2024-12-09):
  - 대안 검토: S3 Select, Athena External Table
  - 결론: 현행 DynamoDB 유지 (중복 제거 실시간 조회 필요)
  - 향후: 비용 이슈 발생 시 하이브리드 구조 고려 (DynamoDB 1테이블 + S3/Athena)

### ~~4. Remove infra/cdk directory~~
- **상태**: 완료
- **완료일**: 2024-12-09
- **설명**: infra/cdk 디렉토리 삭제 및 문서에서 CDK 참조 제거
- **변경 사항**:
  - `infra/` 디렉토리 삭제
  - README.md: 디렉토리 구조, Prerequisites, Installation에서 CDK 제거
  - docs/COST_OPTIMIZATION.md: CDK 예시를 CloudFormation으로 변경
  - docs/IMPLEMENTATION_GUIDE.md: CDK Stack을 MWAA DAG + CloudFormation으로 변경

### ~~5. Replace remediation terms~~
- **상태**: 완료
- **완료일**: 2024-12-09
- **설명**: remediation 영문 표현을 한글로 전환 (문서에서 "복구 조치"로 변경)
- **변경 사항**:
  - README.md: `bdp-remediation` → `bdp-action`, `bdp-remediation-history` → `bdp-action-history`
  - README.md: "Supported Remediation Actions" → "지원 복구 조치 (Supported Actions)"
  - docs/ARCHITECTURE.md: Remediation Layer → 복구 조치 레이어
  - docs/ARCHITECTURE.md: Remediation Decision Flow → 복구 조치 결정 흐름
  - docs/ARCHITECTURE.md: Lambda/테이블/역할명 변경
  - docs/COST_OPTIMIZATION.md: bdp-remediation → bdp-action
  - 코드 내 변수명/함수명은 영문 유지 (호환성)

### ~~6. Remove Bedrock references~~
- **상태**: 완료
- **완료일**: 2024-12-09
- **설명**: 잔존 Bedrock 표현/기능 완전 제거
- **변경 사항**:
  - src/services/aws_client.py: "Bedrock Knowledge Base" → "Knowledge Base"
  - README.md: "Bedrock 근본 원인 분석" → "LLM 기반 근본 원인 분석"
  - docs/ARCHITECTURE.md: "Invoke Bedrock Claude" → "Invoke LLM (vLLM/Gemini)"
  - docs/COST_OPTIMIZATION.md: Bedrock API → LLM API
  - CLAUDE.md: Bedrock 언급 제거

### ~~7. RDS 스키마 동적 로딩 구조 구현~~
- **상태**: 완료
- **완료일**: 2024-12-10
- **우선순위**: High
- **설명**: 금융권 보안 환경에서 코드 반입 후 스키마 정보만 별도 관리하여 동적 조회 지원
- **배경**:
  - 금융권 내부망 반입 시 민감 스키마 정보는 소스코드와 분리 필요
  - Public (외부): mock 스키마로 고속 개발 및 테스트
  - Private (내부): 실제 production 스키마로 운영
  - 소스코드 자체는 보안 이슈 없이 반입 가능
- **파일 구조**:
  ```
  schema/                    # .gitignore에 추가 (Git 추적 제외)
  ├── README.md              # 스키마 작성 가이드
  ├── tables/
  │   └── *.json
  └── views/
  schema.example/            # Git 추적 (템플릿)
  ├── README.md
  └── tables/
      ├── anomaly_logs.json
      ├── service_metrics.json
      └── remediation_history.json
  ```
- **구현 항목**:
  - [x] `.gitignore` 설정 (`schema/` 디렉토리 제외)
  - [x] `schema/README.md`: 스키마 작성 가이드
  - [x] `schema.example/`: 템플릿 3종 (anomaly_logs, service_metrics, remediation_history)
  - [x] `src/services/schema_loader.py`: 스키마 로더 모듈
    - `SchemaLoader`, `TableSchema`, `ColumnSchema` 클래스
    - JSON 파싱, 캐싱, LLM 컨텍스트 생성
  - [x] `src/services/rds_client.py`: RDS Data API 클라이언트
    - `RDSClient`, `RDSProvider` (REAL/MOCK)
    - `QueryResult` 클래스 (마크다운 테이블 출력)
    - 스키마 로더 연동
  - [x] `src/agent/rds_tools.py`: 배치 에이전트용 RDS Tool (5개 도구)
    - `query_rds_anomalies`: 이상 징후 로그 조회
    - `query_rds_metrics`: 서비스 메트릭 조회
    - `query_rds_remediation_history`: 복구 조치 이력 조회
    - `execute_rds_query`: 커스텀 SQL 쿼리 (SELECT만 허용)
    - `get_rds_schema_info`: 스키마 정보 조회
  - [x] `src/chat/tools/rds.py`: Chat용 RDS Tool (5개 도구)
    - `query_anomalies`, `query_metrics`, `query_remediation_history`
    - `get_schema_info`, `execute_custom_query`
  - [x] `tests/test_schema_loader.py`: 단위 테스트 (35 passed, 5 skipped)
- **사용 방법**:
  ```python
  # Schema Loader
  from src.services.schema_loader import SchemaLoader
  loader = SchemaLoader(schema_dir="schema")
  schema = loader.load_table("anomaly_logs")
  context = loader.get_llm_context()  # LLM 프롬프트용

  # RDS Client (Mock)
  from src.services.rds_client import RDSClient, RDSProvider
  client = RDSClient(provider=RDSProvider.MOCK)
  result = client.get_recent_anomalies(severity="HIGH", limit=10)
  print(result.to_markdown_table())
  ```
- **관련 파일**: `.gitignore`, `schema/`, `schema.example/`, `src/services/schema_loader.py`, `src/services/rds_client.py`, `src/agent/rds_tools.py`, `src/chat/tools/rds.py`, `tests/test_schema_loader.py`
- **참고**: Public/Private 환경 간 코드 동기화는 Git으로, 스키마는 각자 수동 관리 (`cp -r schema.example/* schema/`)

### ~~8. Interactive Chat Backend (ChatAgent Library)~~
- **상태**: 완료
- **완료일**: 2024-12-10
- **우선순위**: Medium
- **설명**: 대화형 에이전트 백엔드 라이브러리 (UI는 별도 클라이언트에서 구현)
- **문서**: [`docs/INTERACTIVE_CHAT.md`](../docs/INTERACTIVE_CHAT.md)
- **핵심 기능**:
  - 자원 현황 조회: 대화로 AWS/K8s 자원 상태 실시간 조회
  - 원인분석 의뢰: LLM 기반 근본 원인 분석 (멀티턴 지원)
  - ReAct 자체 검증: Reflect & Replan 패턴으로 분석 품질 검증
  - Human-in-the-loop: 조치 실행 전 운영자 승인/피드백 수집
- **구현 항목**:
  - [x] `src/chat/__init__.py`: 모듈 초기화 및 API export
  - [x] `src/chat/state.py`: ChatState, ChatMessage, ApprovalRequest 등 상태 모델
  - [x] `src/chat/config.py`: ChatConfig, PromptTemplates 설정
  - [x] `src/chat/agent.py`: ChatAgent (LangGraph 기반 ReAct 에이전트)
  - [x] `src/chat/nodes/`: plan, act, observe, reflect, human_review, respond 노드
  - [x] `src/chat/tools/`: CloudWatch, Prometheus, Service Health Tool 래퍼
  - [x] `tests/test_chat.py`: 단위 테스트
- **사용 방법**:
  ```python
  from src.chat import ChatAgent
  from src.services.llm_client import LLMProvider
  from src.services.aws_client import AWSProvider

  agent = ChatAgent(
      llm_provider=LLMProvider.GEMINI,
      aws_provider=AWSProvider.REAL,
  )
  response = agent.chat("현재 서비스 상태 알려줘")
  ```
- **UI 연동**: Streamlit/FastAPI 등 별도 클라이언트에서 ChatAgent import하여 사용
- **의존성**: Task #7 (RDS 스키마 동적 로딩) - rds_tool.py 추가 시 연동
- **관련 파일**: `src/chat/`, `docs/INTERACTIVE_CHAT.md`, `tests/test_chat.py`

---

## 완료된 Tasks

### ~~EventBridge → MWAA 마이그레이션~~
- **상태**: 완료
- **완료일**: 2024-12-09
- **커밋**: `e204b1d`
- **설명**: EventBridge scheduler를 MWAA (Airflow DAG)로 변경

### ~~Configuration Drift Detection 문서화~~
- **상태**: 완료
- **완료일**: 2024-12-09
- **커밋**: `8c36b45`
- **설명**: AWS 리소스 구성 드리프트 탐지 기능 문서 작성

---

*최종 업데이트: 2024-12-10*
