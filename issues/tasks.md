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

### 4. Remove infra/cdk directory
- **상태**: 대기
- **설명**: 불필요한 infra/cdk 디렉토리 제거 검토
- **우선순위**: Low
- **관련 파일**: `infra/cdk/`

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
