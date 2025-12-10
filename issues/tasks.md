# BDP Agent Tasks

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

### 2. Reorganize features
- **상태**: 대기
- **설명**: 주요 기능 하이라이트 정리 (README, ARCHITECTURE)
- **우선순위**: Medium
- **관련 파일**: `README.md`, `docs/ARCHITECTURE.md`

### 3. Evaluate DynamoDB necessity
- **상태**: 보류 (On Hold)
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

*최종 업데이트: 2024-12-09*
