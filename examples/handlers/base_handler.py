"""
Base Handler Pattern for CD1 Agent Lambda Functions.

이 모듈은 모든 Lambda 핸들러의 기본 클래스를 제공합니다.
- 일관된 에러 처리
- 입력 검증 (Pydantic)
- 구조화된 로깅 (structlog)
"""
import json
import structlog
from abc import ABC, abstractmethod
from typing import Any, Dict, TypeVar, Generic
from pydantic import BaseModel, ValidationError
from functools import wraps

logger = structlog.get_logger()

T = TypeVar('T', bound=BaseModel)


class HandlerError(Exception):
    """Base exception for handler errors."""

    def __init__(self, message: str, error_code: str, details: Dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


def lambda_handler_wrapper(func):
    """
    Lambda 핸들러를 위한 데코레이터.

    기능:
    - 일관된 에러 처리 및 응답 포맷
    - 요청 ID 바인딩
    - 구조화된 로깅
    """
    @wraps(func)
    def wrapper(event: Dict, context: Any) -> Dict:
        request_id = context.aws_request_id if context else "local"
        log = logger.bind(request_id=request_id)

        try:
            log.info("handler_start", event_keys=list(event.keys()))
            result = func(event, context, log)
            log.info("handler_success")
            return {
                "statusCode": 200,
                "body": json.dumps(result, ensure_ascii=False, default=str)
            }
        except ValidationError as e:
            log.error("validation_error", errors=e.errors())
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "VALIDATION_ERROR",
                    "message": str(e),
                    "details": e.errors()
                })
            }
        except HandlerError as e:
            log.error("handler_error", error_code=e.error_code, details=e.details)
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "error": e.error_code,
                    "message": e.message,
                    "details": e.details
                })
            }
        except Exception as e:
            log.exception("unexpected_error")
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "error": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred"
                })
            }
    return wrapper


class BaseHandler(ABC, Generic[T]):
    """
    모든 Lambda 핸들러의 추상 기본 클래스.

    사용법:
        class MyHandler(BaseHandler[MyInputModel]):
            def __init__(self):
                super().__init__(MyInputModel)

            def process(self, input_data: MyInputModel, context: Any) -> Dict:
                # 비즈니스 로직 구현
                return {"result": "success"}
    """

    def __init__(self, input_model: type[T]):
        self.input_model = input_model
        self.logger = structlog.get_logger()

    def parse_input(self, event: Dict) -> T:
        """입력 이벤트를 파싱하고 검증합니다."""
        # Step Functions에서 직접 전달되는 경우
        if "body" in event:
            data = json.loads(event["body"])
        else:
            data = event
        return self.input_model.model_validate(data)

    @abstractmethod
    def process(self, input_data: T, context: Any) -> Dict:
        """
        요청을 처리합니다. 서브클래스에서 구현해야 합니다.

        Args:
            input_data: 검증된 입력 데이터
            context: Lambda 컨텍스트

        Returns:
            처리 결과 딕셔너리
        """
        pass

    def handle(self, event: Dict, context: Any) -> Dict:
        """Lambda 핸들러의 메인 진입점."""
        input_data = self.parse_input(event)
        return self.process(input_data, context)
