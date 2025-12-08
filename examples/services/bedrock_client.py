"""
Bedrock Client for BDP Agent.

이 모듈은 AWS Bedrock Claude API와의 통신을 담당합니다.
- 재시도 로직 (tenacity)
- JSON 응답 파싱
- 구조화된 로깅
"""
import json
import os
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import boto3
import structlog

logger = structlog.get_logger()


class BedrockClient:
    """AWS Bedrock Claude API 클라이언트."""

    DEFAULT_MODEL = "anthropic.claude-3-sonnet-20240229-v1:0"

    def __init__(self, model_id: Optional[str] = None):
        """
        BedrockClient 초기화.

        Args:
            model_id: 사용할 Bedrock 모델 ID. 기본값은 Claude 3 Sonnet.
        """
        self.client = boto3.client('bedrock-runtime')
        self.model_id = model_id or os.environ.get(
            'BEDROCK_MODEL_ID',
            self.DEFAULT_MODEL
        )
        self.logger = logger.bind(service="bedrock_client")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30)
    )
    def invoke(
        self,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Bedrock Claude 호출 (재시도 로직 포함).

        Args:
            prompt: 사용자 프롬프트
            max_tokens: 최대 출력 토큰 수
            temperature: 샘플링 온도 (0.0-1.0)

        Returns:
            파싱된 JSON 응답 또는 raw 텍스트

        Raises:
            Exception: Bedrock API 호출 실패 시
        """
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        self.logger.info(
            "bedrock_invoke_start",
            model=self.model_id,
            prompt_length=len(prompt),
            max_tokens=max_tokens
        )

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json"
            )

            response_body = json.loads(response['body'].read())
            content = response_body.get('content', [{}])[0].get('text', '')

            # JSON 응답 파싱 시도
            parsed_content = self._parse_json_response(content)

            self.logger.info(
                "bedrock_invoke_success",
                input_tokens=response_body.get('usage', {}).get('input_tokens'),
                output_tokens=response_body.get('usage', {}).get('output_tokens')
            )

            return parsed_content

        except Exception as e:
            self.logger.error("bedrock_invoke_error", error=str(e))
            raise

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """
        Claude 응답에서 JSON 파싱.

        마크다운 코드 블록 처리 포함.
        """
        # JSON 블록 추출 시도
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
            # JSON 파싱 실패 시 원본 텍스트 반환
            return {"raw_response": content}

    def invoke_with_system(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        시스템 프롬프트와 사용자 프롬프트를 분리하여 호출.

        Args:
            system_prompt: 시스템 프롬프트 (역할 정의)
            user_prompt: 사용자 프롬프트 (실제 요청)
            max_tokens: 최대 출력 토큰 수
            temperature: 샘플링 온도

        Returns:
            파싱된 JSON 응답
        """
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ]
        }

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json"
            )

            response_body = json.loads(response['body'].read())
            content = response_body.get('content', [{}])[0].get('text', '')

            return self._parse_json_response(content)

        except Exception as e:
            self.logger.error("bedrock_invoke_error", error=str(e))
            raise

    def estimate_tokens(self, text: str) -> int:
        """
        텍스트의 대략적인 토큰 수 추정.

        Claude의 토큰화는 대략 4글자당 1토큰.
        """
        return len(text) // 4


# 사용 예시
if __name__ == "__main__":
    client = BedrockClient()

    test_prompt = """
    Analyze the following error and provide a solution:
    Error: Connection timeout to database after 30 seconds.

    Respond in JSON format with:
    - root_cause: string
    - solution: string
    """

    try:
        result = client.invoke(test_prompt)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}")
