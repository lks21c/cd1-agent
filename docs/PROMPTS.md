# BDP Agent Prompt Design Guide

## Overview

BDP Agent의 프롬프트는 **hdsp_agent 패턴**을 따라 비즈니스 로직에서 분리되어 `src/prompts/` 디렉토리에서 관리됩니다.

### LLM Provider 호환성

| Provider | 지원 버전 | 특이사항 |
|----------|----------|----------|
| **vLLM** | OpenAI Compatible | 모든 프롬프트 호환 |
| **Gemini 2.5 Pro** | 최신 버전 | JSON 출력 최적화 |
| **Gemini 2.5 Flash** | 최신 버전 | 빠른 응답, 비용 효율 |

### 설계 원칙
1. **분리된 관심사**: 프롬프트 템플릿과 실행 로직 분리
2. **JSON 출력 강제**: 파싱 가능한 구조화된 응답
3. **컨텍스트 주입**: 동적 데이터를 위한 포맷 함수 제공
4. **도메인 지식 통합**: Knowledge Base 내용 삽입 지원
5. **Provider 중립성**: vLLM/Gemini 모두에서 동작하는 프롬프트 설계

---

## Prompt File Structure

```
src/prompts/
├── __init__.py
├── detection_prompts.py    # 이상 감지 분류
├── analysis_prompts.py     # 근본 원인 분석
├── remediation_prompts.py  # 해결책 생성
└── reflection_prompts.py   # 자기 평가
```

---

## 1. Analysis Prompts

### ANALYSIS_PROMPT

근본 원인 분석을 위한 메인 프롬프트입니다.

```python
ANALYSIS_PROMPT = '''당신은 AWS 인프라 전문가입니다. 다음 로그 이상 현상을 분석하고 근본 원인과 해결책을 제시하세요.

## 감지된 이상 현상

{anomalies}

## 관련 로그 요약

{log_summary}

## 시스템 컨텍스트

- RDS 인스턴스: {rds_instance}
- Lambda 함수: {lambda_functions}
- 최근 변경사항: {recent_changes}

## 분석 지침

1. **근본 원인 분석**: 로그 패턴과 메트릭을 기반으로 근본 원인 파악
2. **영향도 평가**: 서비스에 미치는 영향 심각도 평가
3. **해결책 제시**: 구체적이고 실행 가능한 해결책 제시
4. **신뢰도 점수**: 분석의 확실성을 0.0-1.0 사이로 평가

## 해결책 유형

1. **lambda_restart**: Lambda 함수 재시작
   - parameters: {{"function_name": "함수명", "reason": "재시작 이유"}}

2. **rds_parameter**: RDS 파라미터 조정
   - parameters: {{"parameter_name": "파라미터명", "old_value": "이전값", "new_value": "새값"}}

3. **auto_scaling**: Auto Scaling 조정
   - parameters: {{"resource_type": "리소스유형", "action": "scale_up|scale_down", "amount": 수량}}

4. **eventbridge_event**: 이벤트 발행 (외부 알림용)
   - parameters: {{"event_type": "이벤트유형", "severity": "심각도", "detail": {{...}}}}

{knowledge_section}

## 출력 형식 (JSON)

```json
{{
  "analysis": {{
    "root_cause": "근본 원인 설명",
    "impact_severity": "low | medium | high | critical",
    "affected_services": ["영향받는 서비스"],
    "evidence": ["근거가 되는 로그/메트릭"]
  }},
  "confidence_score": 0.0-1.0,
  "reasoning": "분석 근거 설명",
  "remediations": [
    {{
      "action_type": "lambda_restart | rds_parameter | auto_scaling | eventbridge_event",
      "priority": 1,
      "parameters": {{}},
      "expected_outcome": "예상 결과",
      "rollback_plan": "롤백 계획"
    }}
  ],
  "requires_human_review": true | false,
  "review_reason": "사람 검토가 필요한 이유 (해당 시)"
}}
```

JSON만 출력하세요.'''
```

### Format Function

```python
def format_analysis_prompt(
    anomalies: list,
    log_summary: str,
    rds_instance: str,
    lambda_functions: list,
    recent_changes: list,
    knowledge: str = ""
) -> str:
    """분석 프롬프트 포맷팅"""

    # 이상 현상 텍스트 변환
    anomalies_text = "\n".join([
        f"- [{a.get('severity', 'UNKNOWN')}] {a.get('type', 'Unknown')}: {a.get('description', '')}"
        for a in anomalies
    ])

    # 지식 베이스 섹션
    knowledge_section = ""
    if knowledge:
        knowledge_section = f"\n## 참조 지식\n\n{knowledge}"

    return ANALYSIS_PROMPT.format(
        anomalies=anomalies_text,
        log_summary=log_summary,
        rds_instance=rds_instance,
        lambda_functions=", ".join(lambda_functions),
        recent_changes=", ".join(recent_changes) if recent_changes else "없음",
        knowledge_section=knowledge_section
    )
```

---

## 2. Replan Prompts

### REPLAN_PROMPT

초기 해결책 실패 시 대안을 찾기 위한 프롬프트입니다.

```python
REPLAN_PROMPT = '''이전 해결책 실행 후 문제가 해결되지 않았습니다. 새로운 접근법을 제시하세요.

## 원래 문제

{original_anomaly}

## 시도한 해결책

{attempted_remediation}

## 실행 결과

{execution_result}

## 새로운 분석 지침

1. 왜 이전 해결책이 효과가 없었는지 분석
2. 다른 근본 원인 가능성 검토
3. 대안적 해결책 제시
4. 에스컬레이션 필요 여부 판단

## 출력 형식 (JSON)

```json
{{
  "reanalysis": {{
    "why_previous_failed": "이전 실패 원인",
    "new_hypothesis": "새로운 가설",
    "alternative_root_causes": ["대안적 근본 원인"]
  }},
  "new_remediations": [
    {{
      "action_type": "액션 유형",
      "priority": 1,
      "parameters": {{}},
      "expected_outcome": "예상 결과",
      "rollback_plan": "롤백 계획"
    }}
  ],
  "confidence_score": 0.0-1.0,
  "escalation_required": true | false,
  "escalation_reason": "에스컬레이션 이유 (해당 시)"
}}
```

JSON만 출력하세요.'''
```

### Format Function

```python
def format_replan_prompt(
    original_anomaly: dict,
    attempted_remediation: dict,
    execution_result: dict
) -> str:
    """Replan 프롬프트 포맷팅"""
    import json

    return REPLAN_PROMPT.format(
        original_anomaly=json.dumps(original_anomaly, indent=2, ensure_ascii=False),
        attempted_remediation=json.dumps(attempted_remediation, indent=2, ensure_ascii=False),
        execution_result=json.dumps(execution_result, indent=2, ensure_ascii=False)
    )
```

---

## 3. Reflection Prompts

### REFLECTION_PROMPT

분석 결과의 품질을 자체 평가하는 프롬프트입니다.

```python
REFLECTION_PROMPT = '''분석 결과를 자체 평가하고 신뢰도를 산정하세요.

## 분석 결과

{analysis_result}

## 평가 기준

1. **근거 충분성**: 결론을 뒷받침하는 증거가 충분한가?
2. **논리적 일관성**: 분석 논리에 모순이 없는가?
3. **해결책 실행 가능성**: 제안된 해결책이 실제로 실행 가능한가?
4. **위험도**: 해결책 실행 시 부작용 가능성은?

## 자동 실행 기준

- 신뢰도 >= 0.85: 자동 실행 가능
- 신뢰도 0.50 - 0.84: 승인 필요
- 신뢰도 < 0.50: 에스컬레이션 필요

## 출력 형식 (JSON)

```json
{{
  "evaluation": {{
    "evidence_sufficiency": 0.0-1.0,
    "logical_consistency": 0.0-1.0,
    "actionability": 0.0-1.0,
    "risk_assessment": 0.0-1.0
  }},
  "overall_confidence": 0.0-1.0,
  "concerns": ["우려 사항"],
  "recommendations": {{
    "auto_execute": true | false,
    "reason": "자동 실행 여부 판단 근거"
  }}
}}
```

JSON만 출력하세요.'''
```

### Format Function

```python
def format_reflection_prompt(analysis_result: dict) -> str:
    """Reflection 프롬프트 포맷팅"""
    import json

    return REFLECTION_PROMPT.format(
        analysis_result=json.dumps(analysis_result, indent=2, ensure_ascii=False)
    )
```

---

## 4. Detection Prompts

### ANOMALY_CLASSIFICATION_PROMPT

감지된 이상 현상을 분류하고 우선순위를 매기는 프롬프트입니다.

```python
ANOMALY_CLASSIFICATION_PROMPT = '''다음 로그 이상 현상들을 분류하고 우선순위를 매겨주세요.

## 감지된 이상 현상

{raw_anomalies}

## 분류 기준

### 심각도 (Severity)
- **critical**: 서비스 다운, 데이터 손실 위험
- **high**: 성능 저하, 부분적 서비스 영향
- **medium**: 경고 수준, 모니터링 필요
- **low**: 정보 수준, 추후 검토

### 카테고리 (Category)
- **connectivity**: 연결 문제 (타임아웃, 네트워크)
- **performance**: 성능 문제 (지연, 처리량)
- **resource**: 리소스 문제 (메모리, CPU, 디스크)
- **security**: 보안 관련 (인증 실패, 권한)
- **application**: 애플리케이션 오류
- **configuration**: 설정 오류

## 출력 형식 (JSON)

```json
{{
  "classified_anomalies": [
    {{
      "id": "이상현상ID",
      "severity": "critical | high | medium | low",
      "category": "카테고리",
      "summary": "요약 설명",
      "priority_score": 0-100,
      "requires_immediate_action": true | false
    }}
  ],
  "overall_assessment": "전체 상황 요약",
  "recommended_investigation_order": ["id1", "id2", ...]
}}
```

JSON만 출력하세요.'''
```

---

## 5. Knowledge Base Integration

### Knowledge Loader Pattern

```python
# src/knowledge/loader.py

class KnowledgeLoader:
    """도메인 지식 로더 (Mini RAG 패턴)"""

    TRIGGER_KEYWORDS = {
        'rds': ['rds', 'database', 'connection', 'query', 'timeout'],
        'lambda': ['lambda', 'invocation', 'cold start', 'memory', 'timeout'],
        'ecs': ['ecs', 'container', 'task', 'service', 'scaling'],
        'network': ['vpc', 'security group', 'network', 'connectivity']
    }

    def __init__(self, knowledge_dir: str = "knowledge/libraries"):
        self.knowledge_dir = knowledge_dir
        self._cache = {}

    def detect_relevant_knowledge(self, anomalies: list) -> list:
        """이상 현상에서 관련 지식 키워드 감지"""
        relevant = set()

        for anomaly in anomalies:
            text = f"{anomaly.get('type', '')} {anomaly.get('description', '')}".lower()
            for category, keywords in self.TRIGGER_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    relevant.add(category)

        return list(relevant)

    def load_knowledge(self, categories: list) -> str:
        """카테고리별 지식 로드"""
        knowledge_parts = []

        for category in categories:
            if category not in self._cache:
                path = f"{self.knowledge_dir}/{category}_errors.md"
                try:
                    with open(path, 'r') as f:
                        self._cache[category] = f.read()
                except FileNotFoundError:
                    continue

            if category in self._cache:
                knowledge_parts.append(f"### {category.upper()} 관련 지식\n\n{self._cache[category]}")

        return "\n\n".join(knowledge_parts)
```

### Knowledge File Example

```markdown
# knowledge/libraries/rds_errors.md

## 일반적인 RDS 오류 패턴

### Connection Timeout
- **원인**: max_connections 초과, 네트워크 지연
- **해결책**:
  1. RDS 파라미터 `max_connections` 증가
  2. Connection Pooling 확인
  3. VPC 보안 그룹 규칙 검토

### Too Many Connections
- **원인**: 커넥션 풀 고갈, 좀비 커넥션
- **해결책**:
  1. 애플리케이션 커넥션 풀 설정 검토
  2. `wait_timeout` 파라미터 조정
  3. 필요시 RDS 인스턴스 스케일업

### Slow Query
- **원인**: 인덱스 누락, 풀 테이블 스캔
- **해결책**:
  1. 실행 계획 분석 (EXPLAIN)
  2. 적절한 인덱스 추가
  3. 쿼리 최적화
```

---

## 6. Prompt Best Practices

### JSON 출력 강제
- 프롬프트 끝에 "JSON만 출력하세요" 명시
- JSON 스키마를 예시로 제공
- 추가 설명 없이 JSON만 반환하도록 유도

### 컨텍스트 최적화
- 필요한 정보만 포함 (토큰 절약)
- 구조화된 섹션으로 가독성 향상
- 명확한 지시사항 제공

### 에러 복구
- JSON 파싱 실패 시 복구 로직 (brace counting)
- 불완전한 JSON 처리
- 재시도 로직

```python
def parse_json_response(response: str) -> Optional[dict]:
    """LLM 응답에서 JSON 파싱 (복구 로직 포함)"""
    import json
    import re

    # 1. JSON 코드 블록 추출
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2. 직접 JSON 파싱 시도
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # 3. Brace counting으로 불완전한 JSON 복구
    return recover_incomplete_json(response)


def recover_incomplete_json(json_str: str) -> Optional[dict]:
    """불완전한 JSON 복구 (hdsp_agent 패턴)"""
    import json

    # 열린 괄호/중괄호 카운팅
    stack = []
    for char in json_str:
        if char in '{[':
            stack.append(char)
        elif char == '}' and stack and stack[-1] == '{':
            stack.pop()
        elif char == ']' and stack and stack[-1] == '[':
            stack.pop()

    # 누락된 닫는 괄호 추가
    closing = ''
    for bracket in reversed(stack):
        closing += ']' if bracket == '[' else '}'

    try:
        return json.loads(json_str + closing)
    except json.JSONDecodeError:
        return None
```

---

## 7. Prompt Testing

### Unit Test Example

```python
# tests/unit/test_prompts.py

import pytest
from src.prompts.analysis_prompts import format_analysis_prompt, ANALYSIS_PROMPT

def test_format_analysis_prompt():
    """분석 프롬프트 포맷팅 테스트"""
    anomalies = [
        {"severity": "high", "type": "ConnectionTimeout", "description": "RDS connection timeout"}
    ]

    result = format_analysis_prompt(
        anomalies=anomalies,
        log_summary="Connection timeout occurred 5 times in last 10 minutes",
        rds_instance="prod-db-1",
        lambda_functions=["api-handler", "data-processor"],
        recent_changes=["Deployed v2.1.0"]
    )

    assert "ConnectionTimeout" in result
    assert "prod-db-1" in result
    assert "api-handler" in result

def test_analysis_prompt_has_json_instruction():
    """JSON 출력 지시 포함 확인"""
    assert "JSON만 출력" in ANALYSIS_PROMPT
    assert "```json" in ANALYSIS_PROMPT
```

---

## 8. Prompt Versioning

### Version Control Strategy

```python
# src/prompts/__init__.py

PROMPT_VERSION = "1.0.0"

# 버전별 프롬프트 관리
PROMPT_VERSIONS = {
    "1.0.0": {
        "analysis": ANALYSIS_PROMPT_V1,
        "replan": REPLAN_PROMPT_V1,
        "reflection": REFLECTION_PROMPT_V1
    }
}

def get_prompt(prompt_type: str, version: str = None) -> str:
    """버전별 프롬프트 로드"""
    version = version or PROMPT_VERSION
    return PROMPT_VERSIONS[version][prompt_type]
```

### A/B Testing Support

```python
def get_analysis_prompt(variant: str = "default") -> str:
    """A/B 테스트용 프롬프트 선택"""
    variants = {
        "default": ANALYSIS_PROMPT,
        "concise": ANALYSIS_PROMPT_CONCISE,
        "detailed": ANALYSIS_PROMPT_DETAILED
    }
    return variants.get(variant, ANALYSIS_PROMPT)
```

---

## 9. LLM Provider 고려사항

### Provider별 프롬프트 최적화

#### vLLM (On-Premise)
```python
# vLLM은 OpenAI Compatible API를 사용
# 시스템 프롬프트와 사용자 프롬프트를 별도로 전달 가능

def format_for_vllm(system_prompt: str, user_prompt: str) -> list:
    """vLLM용 메시지 포맷"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
```

#### Gemini (Public Mock)
```python
# Gemini는 시스템 프롬프트를 사용자 프롬프트에 결합
# JSON 출력을 위해 명시적인 지시가 더 필요할 수 있음

def format_for_gemini(system_prompt: str, user_prompt: str) -> str:
    """Gemini용 프롬프트 포맷"""
    return f"""{system_prompt}

---

{user_prompt}

중요: 반드시 유효한 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요."""
```

### Provider 중립적 프롬프트 설계 지침

1. **명확한 JSON 스키마 제공**: 모든 LLM이 정확한 형식을 따르도록
2. **예시 포함**: 기대하는 출력 형식의 구체적 예시 제공
3. **간결한 지시**: 복잡한 프롬프트보다 명확하고 간결한 지시 선호
4. **에러 처리 고려**: JSON 파싱 실패 시 복구 로직 포함

### Provider별 토큰 제한

| Provider | 입력 토큰 | 출력 토큰 | 권장 설정 |
|----------|----------|----------|----------|
| vLLM (모델 의존) | 모델 별 상이 | 모델 별 상이 | max_tokens: 4096 |
| Gemini 2.5 Pro | 1M | 8K | max_output_tokens: 4096 |
| Gemini 2.5 Flash | 1M | 8K | max_output_tokens: 4096 |

### 응답 파싱 전략

```python
def parse_llm_response(response: str) -> dict:
    """Provider 중립적 응답 파싱"""
    import json
    import re

    # 1. JSON 코드 블록 추출
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2. 일반 코드 블록 추출
    code_match = re.search(r'```\s*([\s\S]*?)\s*```', response)
    if code_match:
        try:
            return json.loads(code_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 직접 JSON 파싱
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # 4. 불완전한 JSON 복구
    return recover_incomplete_json(response)
```
