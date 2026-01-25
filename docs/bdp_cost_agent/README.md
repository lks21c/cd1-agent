# BDP Compact Agent

> **서브 에이전트**: BDP Compact (비용 드리프트 탐지 경량 Agent)
>
> PyOD ECOD 기반 Cost Explorer 비용 드리프트 탐지 시스템.
> 한글 Rich Summary 및 KakaoTalk 알람 지원.

## 개요

BDP Compact Agent는 AWS Cost Explorer를 통해 비용 변화를 모니터링하고, PyOD ECOD 알고리즘 기반으로 비용 드리프트를 탐지하는 경량 에이전트입니다.

## 주요 기능

- **계정별 Lambda 배포**: 각 AWS 계정에 개별 Lambda 배포 (Lambda 실행 역할 권한 사용)
- **PyOD ECOD 탐지**: Parameter-free 이상 탐지 알고리즘 (Python 3.11+ 지원)
- **앙상블 탐지**: ECOD + Ratio 기반 복합 판정
- **Pattern-Aware Detection**: 요일/추세 패턴 인식으로 False Positive 감소
- **한글 Rich Summary**: 사람이 읽기 쉬운 한글 알람 메시지 생성
- **KakaoTalk 알람**: EventBridge → KakaoTalk 연동 알람 발송
- **HITL 통합**: Critical 이상 탐지시 Human-in-the-Loop 요청 자동 생성
- **Lambda + FastAPI**: 동일 코드로 서버리스/컨테이너 배포 지원

## 빠른 시작

### 1. 환경 변수 설정

```bash
export BDP_PROVIDER=mock          # Provider 타입 (mock/real/localstack)
export BDP_ACCOUNT_NAME=my-account  # 계정 식별 이름
export BDP_SENSITIVITY=0.7        # 탐지 민감도 (0.0-1.0)
export BDP_PATTERN_RECOGNITION=true  # 패턴 인식 활성화
```

### 2. 탐지 실행 (Lambda Handler)

```python
from src.agents.bdp_cost.handler import handler

result = handler({'days': 14}, None)
print(result)
```

### 3. FastAPI 서버 실행

```bash
# 개발 모드
python -m src.agents.bdp_cost.server

# 또는
uvicorn src.agents.bdp_cost.server:app --port 8005 --reload
```

## 주요 컴포넌트

| 컴포넌트 | 파일 | 설명 |
|---------|------|------|
| **Handler** | `handler.py` | Lambda/FastAPI 진입점 |
| **Anomaly Detector** | `services/anomaly_detector.py` | ECOD 기반 비용 탐지기 |
| **Pattern Recognizers** | `services/pattern_recognizers.py` | 패턴 인식기 (요일, 추세) |
| **Cost Explorer Provider** | `services/cost_explorer_provider.py` | Cost Explorer 접근 |
| **Summary Generator** | `services/summary_generator.py` | 한글 Summary 생성 |
| **Event Publisher** | `services/event_publisher.py` | EventBridge 발행 |

## 문서 구조

```
docs/bdp_cost_agent/
├── README.md                    # 이 파일
├── architecture.md              # 시스템 아키텍처
├── detection/
│   ├── algorithm.md             # ECOD + Ratio 앙상블 알고리즘
│   ├── pattern_aware.md         # 패턴 인식 전략 설계
│   └── severity.md              # 심각도 분류 기준
├── integration/
│   ├── eventbridge.md           # EventBridge 연동
│   ├── kakao.md                 # KakaoTalk 알람
│   └── hitl.md                  # HITL 연동
├── deployment/
│   ├── lambda.md                # Lambda 배포
│   └── fastapi.md               # FastAPI 서버
└── testing.md                   # 테스트 가이드
```

## Cost Agent와의 차이점

| 항목 | Cost Agent | BDP Compact Agent |
|------|------------|-------------------|
| **탐지 알고리즘** | Luminol (deprecated) | PyOD ECOD (active) |
| **Python 버전** | 3.9+ | 3.11+ |
| **패턴 인식** | 미지원 | 요일/추세 패턴 인식 |
| **Summary 언어** | 영문 | 한글 Rich Summary |
| **알람 채널** | Slack/Email | KakaoTalk |
| **HITL 지원** | 미지원 | PROMPT_INPUT 지원 |

## 관련 문서

- [아키텍처](architecture.md)
- [탐지 알고리즘](detection/algorithm.md)
- [패턴 인식 전략](detection/pattern_aware.md)
- [배포 가이드](deployment/lambda.md)
- [테스트 가이드](testing.md)
