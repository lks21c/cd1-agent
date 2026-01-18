"""
LLM Client with Provider Abstraction.

Supports vLLM, Gemini, and Mock providers for flexible deployment.
"""

import json
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    VLLM = "vllm"
    GEMINI = "gemini"
    MOCK = "mock"


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate text completion."""
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> T:
        """Generate structured output matching Pydantic model."""
        pass


class VLLMProvider(BaseLLMProvider):
    """vLLM provider for self-hosted models."""

    def __init__(self, endpoint: str, model_name: str, api_key: Optional[str] = None):
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key or os.getenv("VLLM_API_KEY", "")

    def _make_request(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Make HTTP request to vLLM server."""
        import urllib.request

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            f"{self.endpoint}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate text completion via vLLM."""
        return self._make_request(prompt, system_prompt, temperature, max_tokens)

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> T:
        """Generate structured output via vLLM with JSON mode."""
        schema = response_model.model_json_schema()
        enhanced_prompt = f"{prompt}\n\nRespond with valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"

        response_format = {"type": "json_object"}
        result = self._make_request(
            enhanced_prompt, system_prompt, temperature, 4096, response_format
        )

        return response_model.model_validate_json(result)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-pro"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _make_request(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Make HTTP request to Gemini API."""
        import urllib.request

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
            contents.append(
                {"role": "model", "parts": [{"text": "Understood. I will follow these instructions."}]}
            )
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        url = f"{self.base_url}/models/{self.model_name}:generateContent?key={self.api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["candidates"][0]["content"]["parts"][0]["text"]

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate text completion via Gemini."""
        return self._make_request(prompt, system_prompt, temperature, max_tokens)

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> T:
        """Generate structured output via Gemini."""
        from src.common.prompts.utils import parse_json_response

        schema = response_model.model_json_schema()
        enhanced_prompt = f"{prompt}\n\nRespond ONLY with valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"

        result = self._make_request(enhanced_prompt, system_prompt, temperature, 4096)
        parsed = parse_json_response(result)
        return response_model.model_validate(parsed)


class MockLLMProvider(BaseLLMProvider):
    """Mock provider for testing."""

    def __init__(self, responses: Optional[Dict[str, Any]] = None):
        self.responses = responses or {}
        self.call_history: List[Dict[str, Any]] = []

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Return mock response."""
        self.call_history.append(
            {
                "method": "generate",
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )

        if "generate" in self.responses:
            return self.responses["generate"]

        return json.dumps(
            {
                "analysis": {
                    "root_cause": "Mock root cause analysis",
                    "impact_severity": "medium",
                    "affected_services": ["service-a"],
                    "evidence": ["Mock evidence"],
                },
                "confidence_score": 0.85,
                "reasoning": "Mock reasoning",
                "remediations": [],
                "requires_human_review": False,
            }
        )

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> T:
        """Return mock structured response."""
        self.call_history.append(
            {
                "method": "generate_structured",
                "prompt": prompt,
                "response_model": response_model.__name__,
                "system_prompt": system_prompt,
                "temperature": temperature,
            }
        )

        if "structured" in self.responses:
            return response_model.model_validate(self.responses["structured"])

        # Generate default mock based on model
        mock_data = self._generate_mock_for_model(response_model)
        return response_model.model_validate(mock_data)

    def _generate_mock_for_model(self, model: Type[BaseModel]) -> Dict[str, Any]:
        """Generate mock data for a Pydantic model."""
        from src.common.models.analysis_result import AnalysisResult

        if model == AnalysisResult or model.__name__ == "AnalysisResult":
            return {
                "analysis": {
                    "root_cause": "Mock root cause",
                    "impact_severity": "medium",
                    "affected_services": ["mock-service"],
                    "evidence": ["Mock evidence"],
                },
                "confidence_score": 0.85,
                "reasoning": "Mock reasoning",
                "remediations": [],
                "requires_human_review": False,
            }

        return {}


class LLMClient:
    """
    Unified LLM client with provider abstraction.

    Usage:
        # vLLM provider
        client = LLMClient(provider=LLMProvider.VLLM, endpoint="http://localhost:8000")

        # Gemini provider
        client = LLMClient(provider=LLMProvider.GEMINI)

        # Mock provider for testing
        client = LLMClient(provider=LLMProvider.MOCK)

        # Generate text
        response = client.generate("Analyze this log...")

        # Generate structured output
        result = client.generate_structured(prompt, AnalysisResult)
    """

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.MOCK,
        endpoint: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        mock_responses: Optional[Dict[str, Any]] = None,
    ):
        self.provider_type = provider
        self._provider = self._create_provider(
            provider, endpoint, model_name, api_key, mock_responses
        )

    def _create_provider(
        self,
        provider: LLMProvider,
        endpoint: Optional[str],
        model_name: Optional[str],
        api_key: Optional[str],
        mock_responses: Optional[Dict[str, Any]],
    ) -> BaseLLMProvider:
        """Create the appropriate provider instance."""
        if provider == LLMProvider.VLLM:
            return VLLMProvider(
                endpoint=endpoint or os.getenv("VLLM_ENDPOINT", "http://localhost:8000"),
                model_name=model_name or os.getenv("VLLM_MODEL", "default"),
                api_key=api_key,
            )
        elif provider == LLMProvider.GEMINI:
            return GeminiProvider(
                api_key=api_key,
                model_name=model_name or "gemini-pro",
            )
        else:
            return MockLLMProvider(responses=mock_responses)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate text completion."""
        return self._provider.generate(prompt, system_prompt, temperature, max_tokens)

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> T:
        """Generate structured output matching Pydantic model."""
        return self._provider.generate_structured(
            prompt, response_model, system_prompt, temperature
        )

    @property
    def call_history(self) -> List[Dict[str, Any]]:
        """Get call history (only available for mock provider)."""
        if isinstance(self._provider, MockLLMProvider):
            return self._provider.call_history
        return []
