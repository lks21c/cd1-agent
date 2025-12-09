# BDP Agent Tasks

## 진행 상태
- [ ] 대기 (Pending)
- [x] 완료 (Completed)
- [-] 취소 (Cancelled)

---

## Tasks

### 1. Review confidence-based decision flow
- **상태**: 대기
- **설명**: confidence-based decision flow 시기상조 여부 검토 및 단순화/제거 결정
- **우선순위**: Medium
- **관련 파일**: `src/`, `docs/ARCHITECTURE.md`

### 2. Reorganize features
- **상태**: 대기
- **설명**: 주요 기능 하이라이트 정리 (README, ARCHITECTURE)
- **우선순위**: Medium
- **관련 파일**: `README.md`, `docs/ARCHITECTURE.md`

### 3. Evaluate DynamoDB necessity
- **상태**: 대기
- **설명**: DynamoDB 필수 여부 검토 및 대안 고려
- **우선순위**: High
- **관련 파일**: `docs/ARCHITECTURE.md`, `src/`

### ~~4. Remove infra/cdk directory~~
- **상태**: 완료
- **완료일**: 2024-12-09
- **설명**: infra/cdk 디렉토리 삭제 및 문서에서 CDK 참조 제거
- **변경 사항**:
  - `infra/` 디렉토리 삭제
  - README.md: 디렉토리 구조, Prerequisites, Installation에서 CDK 제거
  - docs/COST_OPTIMIZATION.md: CDK 예시를 CloudFormation으로 변경
  - docs/IMPLEMENTATION_GUIDE.md: CDK Stack을 MWAA DAG + CloudFormation으로 변경

### 5. Replace remediation terms
- **상태**: 대기
- **설명**: remediation 영문 표현을 한글로 전환
- **우선순위**: Low
- **관련 파일**: `docs/`, `src/`

### 6. Remove Bedrock references
- **상태**: 대기
- **설명**: 잔존 Bedrock 표현/기능 완전 제거
- **우선순위**: High
- **관련 파일**: `docs/`, `src/`, `README.md`

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
