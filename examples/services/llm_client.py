"""
LLM Client for CD1 Agent.

vLLM (On-Premise) 또는 Gemini (Public Mock)를 지원하는 통합 LLM 클라이언트.
환경 변수 LLM_PROVIDER로 provider를 선택합니다.
"""
import json
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import structlog

logger = structlog.get_logger()


class BaseLLMProvider(ABC):
    """LLM Provider 추상 클래스."""

    @abstractmethod
    def invoke(self, prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
        """프롬프트를 LLM에 전송하고 응답을 반환."""
        pass

    @abstractmethod
    def invoke_with_system(self, system_prompt: str, user_prompt: str,
                          max_tokens: int, temperature: float) -> Dict[str, Any]:
        """시스템 프롬프트와 함께 LLM 호출."""
        pass

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """LLM 응답에서 JSON 파싱."""
        if '```json' in content:
            start = content.find('```json') + 7
            end = content.find('```', start)
            json_str = content[start:end].strip()
        elif '```' in content:
            start = content.find('```') + 3
            end = content.find('```', start)
            json_str = content[start:end].strip()
        else:
            json_str = content.strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {"raw_response": content}


class VLLMProvider(BaseLLMProvider):
    """vLLM OpenAI Compatible API Provider (On-Premise)."""

    def __init__(self):
        from openai import OpenAI

        self.base_url = os.environ.get('VLLM_BASE_URL', 'http://localhost:8000/v1')
        self.model_name = os.environ.get('VLLM_MODEL_NAME')
        self.api_key = os.environ.get('VLLM_API_KEY', 'EMPTY')

        if not self.model_name:
            raise ValueError("VLLM_MODEL_NAME 환경 변수가 필요합니다")

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        self.logger = logger.bind(service="vllm_provider")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30)
    )
    def invoke(self, prompt: str, max_tokens: int = 4096,
               temperature: float = 0.3) -> Dict[str, Any]:
        """vLLM 호출."""
        self.logger.info(
            "vllm_invoke_start",
            model=self.model_name,
            prompt_length=len(prompt)
        )

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )

        content = response.choices[0].message.content

        self.logger.info(
            "vllm_invoke_success",
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens
        )

        return self._parse_json_response(content)

    def invoke_with_system(self, system_prompt: str, user_prompt: str,
                          max_tokens: int = 4096, temperature: float = 0.3) -> Dict[str, Any]:
        """시스템 프롬프트와 함께 호출."""
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )

        content = response.choices[0].message.content
        return self._parse_json_response(content)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider (Public Mock)."""

    def __init__(self):
        import google.generativeai as genai

        self.api_key = os.environ.get('GEMINI_API_KEY')
        self.model_id = os.environ.get('GEMINI_MODEL_ID', 'gemini-2.5-flash')

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY 환경 변수가 필요합니다")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_id)
        self.logger = logger.bind(service="gemini_provider")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30)
    )
    def invoke(self, prompt: str, max_tokens: int = 4096,
               temperature: float = 0.3) -> Dict[str, Any]:
        """Gemini 호출."""
        self.logger.info(
            "gemini_invoke_start",
            model=self.model_id,
            prompt_length=len(prompt)
        )

        generation_config = {
            "max_output_tokens": max_tokens,
            "temperature": temperature
        }

        response = self.model.generate_content(
            prompt,
            generation_config=generation_config
        )

        content = response.text

        self.logger.info(
            "gemini_invoke_success",
            model=self.model_id
        )

        return self._parse_json_response(content)

    def invoke_with_system(self, system_prompt: str, user_prompt: str,
                          max_tokens: int = 4096, temperature: float = 0.3) -> Dict[str, Any]:
        """시스템 프롬프트와 함께 호출."""
        combined_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
        return self.invoke(combined_prompt, max_tokens, temperature)


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM Provider for testing without any external API."""

    def __init__(self):
        self.logger = logger.bind(service="mock_llm_provider")
        self.call_count = 0

    def invoke(self, prompt: str, max_tokens: int = 4096,
               temperature: float = 0.3) -> Dict[str, Any]:
        """Mock LLM 응답 생성."""
        self.call_count += 1
        self.logger.info(
            "mock_llm_invoke",
            call_count=self.call_count,
            prompt_length=len(prompt)
        )

        # 프롬프트 분석하여 적절한 mock 응답 생성
        if "analyze" in prompt.lower() or "분석" in prompt:
            return self._generate_analysis_response()
        elif "reflect" in prompt.lower() or "평가" in prompt:
            return self._generate_reflection_response()
        elif "replan" in prompt.lower() or "재계획" in prompt:
            return self._generate_replan_response()
        else:
            return self._generate_default_response()

    def invoke_with_system(self, system_prompt: str, user_prompt: str,
                          max_tokens: int = 4096, temperature: float = 0.3) -> Dict[str, Any]:
        """시스템 프롬프트와 함께 호출."""
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"
        return self.invoke(combined_prompt, max_tokens, temperature)

    def _generate_analysis_response(self) -> Dict[str, Any]:
        """분석 응답 mock."""
        return {
            "analysis": {
                "root_cause": "[Mock] Database connection pool exhausted",
                "impact_severity": "high",
                "affected_services": ["api-gateway", "user-service"],
                "evidence": [
                    "Connection timeout errors increased by 500%",
                    "Active connections reached max limit of 100"
                ]
            },
            "confidence_score": 0.87,
            "reasoning": "[Mock] Evidence strongly suggests connection pool exhaustion",
            "remediations": [
                {
                    "action_type": "rds_parameter",
                    "priority": 1,
                    "parameters": {
                        "parameter_name": "max_connections",
                        "new_value": "200"
                    },
                    "expected_outcome": "Increase connection capacity",
                    "rollback_plan": "Revert to previous value of 100"
                }
            ],
            "requires_human_review": False,
            "review_reason": None
        }

    def _generate_reflection_response(self) -> Dict[str, Any]:
        """리플렉션 응답 mock."""
        return {
            "evaluation": {
                "evidence_sufficiency": 0.85,
                "logical_consistency": 0.90,
                "actionability": 0.88,
                "risk_assessment": 0.80
            },
            "overall_confidence": 0.86,
            "concerns": ["[Mock] Some edge cases not fully covered"],
            "recommendations": {
                "auto_execute": True,
                "reason": "[Mock] High confidence with manageable risk"
            }
        }

    def _generate_replan_response(self) -> Dict[str, Any]:
        """재계획 응답 mock."""
        return {
            "reanalysis": {
                "why_previous_failed": "[Mock] Root cause was misidentified",
                "new_hypothesis": "[Mock] Issue is in application layer, not database",
                "alternative_root_causes": [
                    "Memory leak in connection handling",
                    "Missing connection release in error paths"
                ]
            },
            "new_remediations": [
                {
                    "action_type": "lambda_restart",
                    "priority": 1,
                    "parameters": {"function_name": "api-handler"},
                    "expected_outcome": "Clear stale connections",
                    "rollback_plan": "No rollback needed"
                }
            ],
            "confidence_score": 0.75,
            "escalation_required": False,
            "escalation_reason": None
        }

    def _generate_default_response(self) -> Dict[str, Any]:
        """기본 응답 mock."""
        return {
            "status": "success",
            "message": "[Mock] Request processed successfully",
            "data": {}
        }


class LLMClient:
    """통합 LLM 클라이언트 - Provider 자동 선택."""

    def __init__(self, provider: Optional[str] = None):
        """
        LLMClient 초기화.

        Args:
            provider: 'vllm', 'gemini', 또는 'mock'. None이면 환경 변수에서 결정.

        환경 변수:
            LLM_PROVIDER: 'vllm' | 'gemini' | 'mock'
            LLM_MOCK: 'true'로 설정 시 mock provider 강제 사용
        """
        # Mock 모드 체크
        if os.environ.get('LLM_MOCK', '').lower() == 'true':
            provider = 'mock'
        else:
            provider = provider or os.environ.get('LLM_PROVIDER', 'vllm')

        if provider == 'vllm':
            self._provider = VLLMProvider()
        elif provider == 'gemini':
            self._provider = GeminiProvider()
        elif provider == 'mock':
            self._provider = MockLLMProvider()
        else:
            raise ValueError(f"지원하지 않는 LLM provider: {provider}")

        self.provider_name = provider
        self.logger = logger.bind(service="llm_client", provider=provider)

    def invoke(self, prompt: str, max_tokens: int = 4096,
               temperature: float = 0.3) -> Dict[str, Any]:
        """LLM 호출."""
        return self._provider.invoke(prompt, max_tokens, temperature)

    def invoke_with_system(self, system_prompt: str, user_prompt: str,
                          max_tokens: int = 4096, temperature: float = 0.3) -> Dict[str, Any]:
        """시스템 프롬프트와 함께 호출."""
        return self._provider.invoke_with_system(
            system_prompt, user_prompt, max_tokens, temperature
        )

    def estimate_tokens(self, text: str) -> int:
        """텍스트의 대략적인 토큰 수 추정."""
        return len(text) // 4


# 사용 예시
if __name__ == "__main__":
    # Mock 모드로 테스트
    os.environ['LLM_MOCK'] = 'true'

    client = LLMClient()
    print(f"Using provider: {client.provider_name}")

    test_prompt = """
    Analyze the following error and provide a solution:
    Error: Connection timeout to database after 30 seconds.
    """

    result = client.invoke(test_prompt)
    print(json.dumps(result, indent=2, ensure_ascii=False))
