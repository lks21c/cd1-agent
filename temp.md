# BDP Agent 프로젝트 작업 컨텍스트

## 작업 일시
- 시작: 2025-12-08
- 중단 시점: examples 파일 생성 완료, Step Functions + README 작성 중

---

## 프로젝트 개요

### 목적
AWS Lambda 기반 서버리스 로그 분석 및 자동 복구 에이전트

### 핵심 기능
1. **주기적 로그 감지** (5-10분 간격)
2. **데이터 소스**: RDS 통합로그 (JSON string 컬럼 포함), CloudWatch
3. **Bedrock Claude를 사용한 근본 원인 분석**
4. **신뢰도 기반 자동화**:
   - 0.85+: 자동 실행
   - 0.5-0.85: 승인 요청
   - <0.5: 재분석 필요
5. **AWS 리소스 조정** (Lambda 재시작, RDS 파라미터, Auto Scaling)
6. **EventBridge 알림** (외부 시스템이 Slack/Teams 등으로 분배)

### 설계 패턴
- **ReAct 패턴**: Plan → Execute → Reflect → Replan
- **프롬프트 분리**: hdsp_agent 패턴 따름
- **비용 최적화**: Field Indexing, 계층적 요약, ARM64

---

## 완료된 작업 ✅

### 1. 디렉토리 구조
```
~/repo/bdp-agent/
├── docs/
│   ├── ARCHITECTURE.md ✅
│   ├── PROMPTS.md ✅
│   ├── COST_OPTIMIZATION.md ✅
│   └── IMPLEMENTATION_GUIDE.md ✅
├── examples/
│   ├── handlers/
│   │   ├── __init__.py ✅
│   │   ├── base_handler.py ✅
│   │   ├── detection_handler.py ✅
│   │   └── analysis_handler.py ✅
│   ├── prompts/
│   │   ├── __init__.py ✅
│   │   └── analysis_prompts.py ✅
│   └── services/
│       ├── __init__.py ✅
│       ├── bedrock_client.py ✅
│       └── reflection_engine.py ✅
├── src/ (빈 디렉토리, .gitkeep 있음)
├── step_functions/ (빈 디렉토리)
├── infra/cdk/ (빈 디렉토리)
└── tests/ (빈 디렉토리)
```

### 2. GitHub 연결
- 저장소: https://github.com/lks21c/bdp-agent
- 첫 번째 커밋 push 완료 (문서 4개 + 디렉토리 구조)

---

## 남은 작업 ⏳

### 1. Step Functions 워크플로우
파일: `step_functions/bdp_workflow.asl.json`

내용 (IMPLEMENTATION_GUIDE.md에 전체 정의 있음):
- DetectAnomalies → CheckAnomaliesDetected → AnalyzeRootCause
- EvaluateConfidence (0.85+: AutoExecute, 0.5-0.85: RequestApproval)
- ReflectOnResult → CheckReplanAttempts (최대 3회)
- EventBridge 알림 통합

### 2. README.md
내용:
- 프로젝트 소개
- 아키텍처 다이어그램
- 빠른 시작 가이드
- 설정 방법
- 비용 추정

### 3. Git Commit & Push
examples/ 디렉토리 추가된 내용 commit 필요

---

## 참고 문서 위치

### 기존 hdsp_agent 패턴 참고
- `/Users/a453180/repo/hdsp_agent/backend/prompts/` - 프롬프트 분리 패턴
- `/Users/a453180/repo/hdsp_agent/backend/` - 전체 구조

### 생성된 문서
- `docs/ARCHITECTURE.md` - 전체 시스템 아키텍처, AWS 리소스, 데이터 플로우
- `docs/PROMPTS.md` - 프롬프트 템플릿 설계, JSON 출력 강제
- `docs/COST_OPTIMIZATION.md` - Field Indexing, 토큰 최적화, ARM64
- `docs/IMPLEMENTATION_GUIDE.md` - 단계별 구현 + 전체 코드 예시

---

## 핵심 설계 결정

### Lambda 함수 구성
| 함수 | 메모리 | 타임아웃 | 역할 |
|------|--------|----------|------|
| bdp-detection | 512MB | 60s | 로그 이상 감지 |
| bdp-analysis | 1024MB | 120s | Bedrock 분석 |
| bdp-remediation | 512MB | 60s | 복구 조치 실행 |

### DynamoDB 테이블
- `bdp-anomaly-tracking`: 중복 제거 (TTL 7일)
- `bdp-workflow-state`: 워크플로우 상태
- `bdp-remediation-history`: 감사 로그

### 비용 최적화 전략
1. CloudWatch Field Indexing → 67% 스캔 감소
2. 계층적 요약 → 80-90% 토큰 절감
3. ARM64/Graviton2 → 20-34% Lambda 비용 절감
4. EventBridge Warmup → Cold start 제거
5. 월간 예상 비용: ~$16/월 (1M 이벤트 기준)

---

## 이어서 할 명령어

```bash
# 1. Step Functions 워크플로우 생성
# step_functions/bdp_workflow.asl.json 파일 작성

# 2. README.md 작성

# 3. Git commit & push
cd ~/repo/bdp-agent
git add .
git commit -m "feat: Add code examples and Step Functions workflow"
git push
```

---

## 플랜 파일 위치
`/Users/a453180/.claude/plans/velvety-juggling-castle.md`

이 파일에 전체 구현 플랜이 있음.
