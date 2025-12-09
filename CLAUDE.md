# BDP Agent - Claude Code Instructions

## Project Overview
BDP Agent는 AWS 환경에서 이상 탐지 및 자동 대응을 수행하는 LangGraph 기반 ReAct 에이전트입니다.

## Task Management

### TaskMaster AI MCP 연동 시
- **태스크 파일 위치**: `@issues/tasks.md`
- 태스크 목록 조회 및 수정 시 반드시 해당 파일에서 읽고 써야 함
- 태스크 상태 변경 시 파일 업데이트 후 Git 커밋 권장

## Key Directories
- `src/` - 메인 소스 코드
- `docs/` - 아키텍처 및 기능 문서
- `tests/` - 테스트 코드
- `issues/` - 태스크 및 이슈 관리

## Architecture
- **Trigger**: MWAA (Airflow DAG)
- **Event Publishing**: EventBridge (알림용)
- **LLM Provider**: vLLM / Gemini (Bedrock 사용 안 함)
- **Orchestration**: Step Functions
