# BDP Agent Implementation Guide

## Overview

이 가이드는 BDP Agent의 단계별 구현 방법과 코드 예시를 제공합니다.

---

## Phase 1: Core Infrastructure (1-2주)

### 1.1 프로젝트 구조 설정

```
bdp-agent/
├── src/
│   ├── handlers/           # Lambda 핸들러
│   │   ├── __init__.py
│   │   ├── base_handler.py
│   │   ├── detection_handler.py
│   │   ├── analysis_handler.py
│   │   └── remediation_handler.py
│   ├── prompts/            # 프롬프트 템플릿
│   │   ├── __init__.py
│   │   └── analysis_prompts.py
│   ├── services/           # 비즈니스 로직
│   │   ├── __init__.py
│   │   ├── llm_client.py         # vLLM/Gemini 통합 클라이언트
│   │   ├── reflection_engine.py
│   │   ├── log_collector.py
│   │   └── remediation_executor.py
│   ├── models/             # 데이터 모델
│   │   ├── __init__.py
│   │   ├── anomaly.py
│   │   └── analysis_result.py
│   └── knowledge/          # 도메인 지식
│       ├── libraries/
│       └── playbooks/
├── step_functions/         # Step Functions 정의
├── infra/                  # IaC
│   └── cdk/
├── tests/
└── docs/
```

### 1.2 의존성 설정

**requirements.txt**
```txt
boto3>=1.34.0
pydantic>=2.0.0
structlog>=24.0.0
tenacity>=8.0.0
python-json-logger>=2.0.0
openai>=1.0.0            # vLLM OpenAI Compatible API
google-generativeai>=0.8.0  # Gemini API
httpx>=0.27.0            # HTTP 클라이언트
```

---

## Phase 2: Lambda Handlers

### 2.1 Base Handler

모든 Lambda 핸들러의 기본 클래스:

```python
# src/handlers/base_handler.py
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
    """Decorator for consistent error handling and logging."""
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
    """Abstract base class for all Lambda handlers."""

    def __init__(self, input_model: type[T]):
        self.input_model = input_model
        self.logger = structlog.get_logger()

    def parse_input(self, event: Dict) -> T:
        """Parse and validate input event."""
        # Step Functions에서 직접 전달되는 경우
        if "body" in event:
            data = json.loads(event["body"])
        else:
            data = event
        return self.input_model.model_validate(data)

    @abstractmethod
    def process(self, input_data: T, context: Any) -> Dict:
        """Process the request. Must be implemented by subclasses."""
        pass

    def handle(self, event: Dict, context: Any) -> Dict:
        """Main entry point for Lambda handler."""
        input_data = self.parse_input(event)
        return self.process(input_data, context)
```

### 2.2 Detection Handler

로그 이상 감지 Lambda:

```python
# src/handlers/detection_handler.py
import os
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

import boto3
from boto3.dynamodb.conditions import Key

from .base_handler import BaseHandler, lambda_handler_wrapper, HandlerError


class DetectionInput(BaseModel):
    """Detection Lambda input model."""
    time_range_minutes: int = Field(default=10, ge=5, le=60)
    service_filter: Optional[List[str]] = None
    severity_threshold: str = Field(default="ERROR")


class AnomalyRecord(BaseModel):
    """Detected anomaly record."""
    signature: str
    anomaly_type: str
    service_name: str
    first_seen: str
    last_seen: str
    occurrence_count: int
    sample_logs: List[Dict]
    metrics_snapshot: Dict


class DetectionHandler(BaseHandler[DetectionInput]):
    """Handler for detecting anomalies in logs and metrics."""

    def __init__(self):
        super().__init__(DetectionInput)
        self.cloudwatch = boto3.client('cloudwatch')
        self.logs_client = boto3.client('logs')
        self.rds_data = boto3.client('rds-data')
        self.dynamodb = boto3.resource('dynamodb')
        self.dedup_table = self.dynamodb.Table(os.environ.get('DEDUP_TABLE', 'bdp-anomaly-tracking'))

        # RDS 연결 정보
        self.rds_cluster_arn = os.environ.get('RDS_CLUSTER_ARN')
        self.rds_secret_arn = os.environ.get('RDS_SECRET_ARN')
        self.rds_database = os.environ.get('RDS_DATABASE', 'unified_logs')

    def process(self, input_data: DetectionInput, context: Any) -> Dict:
        """Main detection process."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=input_data.time_range_minutes)

        # 1. CloudWatch Anomaly Detection 결과 조회
        anomalies = self._check_cloudwatch_anomalies(start_time, end_time)

        # 2. 이상 감지된 경우에만 RDS 로그 조회
        if anomalies:
            log_context = self._query_rds_logs(
                start_time,
                end_time,
                input_data.service_filter,
                input_data.severity_threshold
            )

            # 3. Anomaly와 로그 연관
            enriched_anomalies = self._enrich_anomalies(anomalies, log_context)

            # 4. Deduplication
            new_anomalies = self._deduplicate(enriched_anomalies)

            if new_anomalies:
                return {
                    "anomalies_detected": True,
                    "anomaly_count": len(new_anomalies),
                    "anomalies": [a.model_dump() for a in new_anomalies],
                    "time_range": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat()
                    }
                }

        return {
            "anomalies_detected": False,
            "anomaly_count": 0,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
        }

    def _check_cloudwatch_anomalies(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Check CloudWatch Anomaly Detection results."""
        # 사전 정의된 메트릭 목록
        metrics_to_check = [
            {"namespace": "AWS/Lambda", "metric": "Errors"},
            {"namespace": "AWS/Lambda", "metric": "Duration"},
            {"namespace": "AWS/RDS", "metric": "CPUUtilization"},
            {"namespace": "AWS/RDS", "metric": "DatabaseConnections"},
        ]

        anomalies = []

        for metric_config in metrics_to_check:
            try:
                response = self.cloudwatch.get_metric_data(
                    MetricDataQueries=[
                        {
                            'Id': 'm1',
                            'MetricStat': {
                                'Metric': {
                                    'Namespace': metric_config['namespace'],
                                    'MetricName': metric_config['metric']
                                },
                                'Period': 300,
                                'Stat': 'Average'
                            }
                        },
                        {
                            'Id': 'anomaly',
                            'Expression': 'ANOMALY_DETECTION_BAND(m1, 2)',
                            'Label': 'AnomalyBand'
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time
                )

                # Anomaly 판단: 값이 밴드를 벗어났는지 확인
                if self._is_anomalous(response):
                    anomalies.append({
                        "type": "metric_anomaly",
                        "namespace": metric_config['namespace'],
                        "metric": metric_config['metric'],
                        "data": response['MetricDataResults']
                    })
            except Exception as e:
                self.logger.warning("metric_check_failed",
                                   metric=metric_config['metric'],
                                   error=str(e))

        return anomalies

    def _is_anomalous(self, metric_response: Dict) -> bool:
        """Check if metric values are outside anomaly band."""
        results = metric_response.get('MetricDataResults', [])
        if len(results) < 2:
            return False

        metric_data = next((r for r in results if r['Id'] == 'm1'), None)
        band_data = next((r for r in results if r['Id'] == 'anomaly'), None)

        if not metric_data or not band_data:
            return False

        # 값이 밴드를 벗어났는지 확인
        for i, value in enumerate(metric_data.get('Values', [])):
            if i < len(band_data.get('Values', [])):
                # 밴드 데이터는 [lower, upper] 쌍으로 제공됨
                # 실제 구현에서는 상세 로직 필요
                pass

        return False  # 실제 구현에서 수정 필요

    def _query_rds_logs(
        self,
        start_time: datetime,
        end_time: datetime,
        service_filter: Optional[List[str]],
        severity_threshold: str
    ) -> List[Dict]:
        """Query RDS unified logs with Field Indexing optimization."""

        # Field Indexing을 활용한 효율적 쿼리
        # service_name, log_level, timestamp에 인덱스 설정 필요

        base_query = """
            SELECT id, timestamp, service_name, log_level, message, metadata
            FROM unified_logs
            WHERE timestamp BETWEEN :start_time AND :end_time
            AND log_level IN (:levels)
        """

        # Severity threshold에 따른 레벨 필터링
        severity_levels = self._get_severity_levels(severity_threshold)

        params = [
            {'name': 'start_time', 'value': {'stringValue': start_time.isoformat()}},
            {'name': 'end_time', 'value': {'stringValue': end_time.isoformat()}},
            {'name': 'levels', 'value': {'stringValue': ','.join(severity_levels)}}
        ]

        if service_filter:
            base_query += " AND service_name IN (:services)"
            params.append({
                'name': 'services',
                'value': {'stringValue': ','.join(service_filter)}
            })

        base_query += " ORDER BY timestamp DESC LIMIT 1000"

        try:
            response = self.rds_data.execute_statement(
                resourceArn=self.rds_cluster_arn,
                secretArn=self.rds_secret_arn,
                database=self.rds_database,
                sql=base_query,
                parameters=params
            )

            return self._parse_rds_response(response)
        except Exception as e:
            self.logger.error("rds_query_failed", error=str(e))
            raise HandlerError(
                message="Failed to query RDS logs",
                error_code="RDS_QUERY_ERROR",
                details={"error": str(e)}
            )

    def _get_severity_levels(self, threshold: str) -> List[str]:
        """Get severity levels at or above threshold."""
        levels_order = ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
        try:
            idx = levels_order.index(threshold.upper())
            return levels_order[idx:]
        except ValueError:
            return ["ERROR", "FATAL"]

    def _parse_rds_response(self, response: Dict) -> List[Dict]:
        """Parse RDS Data API response, including JSON string columns."""
        import json as json_module

        records = []
        columns = response.get('columnMetadata', [])

        for row in response.get('records', []):
            record = {}
            for i, col in enumerate(columns):
                col_name = col['name']
                cell = row[i]

                # 값 추출
                if 'stringValue' in cell:
                    value = cell['stringValue']
                    # metadata 컬럼은 JSON string
                    if col_name == 'metadata' and value:
                        try:
                            value = json_module.loads(value)
                        except json_module.JSONDecodeError:
                            pass
                elif 'longValue' in cell:
                    value = cell['longValue']
                elif 'isNull' in cell and cell['isNull']:
                    value = None
                else:
                    value = str(cell)

                record[col_name] = value

            records.append(record)

        return records

    def _enrich_anomalies(
        self,
        anomalies: List[Dict],
        logs: List[Dict]
    ) -> List[AnomalyRecord]:
        """Enrich anomalies with log context."""
        enriched = []

        for anomaly in anomalies:
            # 관련 로그 샘플링 (최대 5개)
            related_logs = self._find_related_logs(anomaly, logs)[:5]

            # Signature 생성 (deduplication용)
            signature = self._generate_signature(anomaly, related_logs)

            enriched.append(AnomalyRecord(
                signature=signature,
                anomaly_type=anomaly['type'],
                service_name=anomaly.get('namespace', 'unknown'),
                first_seen=datetime.utcnow().isoformat(),
                last_seen=datetime.utcnow().isoformat(),
                occurrence_count=1,
                sample_logs=related_logs,
                metrics_snapshot=anomaly.get('data', {})
            ))

        return enriched

    def _find_related_logs(self, anomaly: Dict, logs: List[Dict]) -> List[Dict]:
        """Find logs related to the anomaly."""
        # 단순 구현: namespace/service 기반 필터링
        namespace = anomaly.get('namespace', '')
        service_hint = namespace.split('/')[-1].lower() if namespace else ''

        related = [
            log for log in logs
            if service_hint in log.get('service_name', '').lower()
        ]

        return related if related else logs[:5]

    def _generate_signature(self, anomaly: Dict, logs: List[Dict]) -> str:
        """Generate unique signature for deduplication."""
        # 핵심 특성을 조합하여 해시 생성
        key_parts = [
            anomaly.get('type', ''),
            anomaly.get('namespace', ''),
            anomaly.get('metric', ''),
        ]

        # 로그의 주요 에러 패턴 추가
        for log in logs[:3]:
            msg = log.get('message', '')[:100]
            key_parts.append(msg)

        combined = '|'.join(key_parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _deduplicate(self, anomalies: List[AnomalyRecord]) -> List[AnomalyRecord]:
        """Filter out recently seen anomalies using DynamoDB."""
        new_anomalies = []
        dedup_window_hours = 1

        for anomaly in anomalies:
            try:
                response = self.dedup_table.get_item(
                    Key={'signature': anomaly.signature}
                )

                if 'Item' in response:
                    # 이미 존재하는 경우: 카운트 업데이트
                    last_seen = datetime.fromisoformat(response['Item']['last_seen'])
                    if datetime.utcnow() - last_seen < timedelta(hours=dedup_window_hours):
                        # 최근에 본 anomaly - 카운트만 업데이트
                        self.dedup_table.update_item(
                            Key={'signature': anomaly.signature},
                            UpdateExpression='SET occurrence_count = occurrence_count + :inc, last_seen = :now',
                            ExpressionAttributeValues={
                                ':inc': 1,
                                ':now': datetime.utcnow().isoformat()
                            }
                        )
                        continue

                # 새 anomaly 또는 오래된 것 - 새로 추가
                self.dedup_table.put_item(
                    Item={
                        'signature': anomaly.signature,
                        'anomaly_type': anomaly.anomaly_type,
                        'service_name': anomaly.service_name,
                        'first_seen': anomaly.first_seen,
                        'last_seen': anomaly.last_seen,
                        'occurrence_count': 1,
                        'ttl': int((datetime.utcnow() + timedelta(days=7)).timestamp())
                    }
                )
                new_anomalies.append(anomaly)

            except Exception as e:
                self.logger.warning("dedup_check_failed",
                                   signature=anomaly.signature,
                                   error=str(e))
                new_anomalies.append(anomaly)

        return new_anomalies


# Lambda entry point
handler_instance = DetectionHandler()

@lambda_handler_wrapper
def lambda_handler(event: Dict, context: Any, log) -> Dict:
    return handler_instance.handle(event, context)
```

### 2.3 Analysis Handler

vLLM 또는 Gemini를 사용한 근본 원인 분석 Lambda:

```python
# src/handlers/analysis_handler.py
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from .base_handler import BaseHandler, lambda_handler_wrapper
from ..services.llm_client import LLMClient
from ..services.reflection_engine import ReflectionEngine
from ..prompts.analysis_prompts import AnalysisPrompts


class AnalysisInput(BaseModel):
    """Analysis Lambda input model."""
    anomalies: List[Dict]
    workflow_id: str
    previous_attempts: List[Dict] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Analysis result model."""
    root_cause: str
    evidence: List[str]
    recommended_actions: List[Dict]
    confidence: float
    reasoning: str
    requires_approval: bool


class AnalysisHandler(BaseHandler[AnalysisInput]):
    """Handler for root cause analysis using vLLM or Gemini."""

    def __init__(self):
        super().__init__(AnalysisInput)
        self.llm = LLMClient()  # vLLM 또는 Gemini 자동 선택
        self.reflection = ReflectionEngine()
        self.prompts = AnalysisPrompts()

    def process(self, input_data: AnalysisInput, context: Any) -> Dict:
        """Main analysis process."""
        # 1. 로그 계층적 요약 (토큰 최적화)
        summarized_logs = self._hierarchical_summarize(input_data.anomalies)

        # 2. Knowledge Base 로딩
        knowledge_context = self._load_knowledge_base(input_data.anomalies)

        # 3. 분석 프롬프트 포맷팅
        prompt = self.prompts.format_analysis_prompt(
            anomalies=input_data.anomalies,
            log_summary=summarized_logs,
            knowledge=knowledge_context,
            previous_attempts=input_data.previous_attempts
        )

        # 4. LLM 호출 (vLLM 또는 Gemini)
        raw_analysis = self.llm.invoke(prompt)

        # 5. Reflection을 통한 신뢰도 평가
        reflection_result = self.reflection.evaluate(
            analysis=raw_analysis,
            evidence=summarized_logs,
            context=input_data.anomalies
        )

        # 6. 결과 구조화
        result = AnalysisResult(
            root_cause=raw_analysis.get('root_cause', ''),
            evidence=raw_analysis.get('evidence', []),
            recommended_actions=raw_analysis.get('actions', []),
            confidence=reflection_result.confidence,
            reasoning=reflection_result.reasoning,
            requires_approval=reflection_result.confidence < 0.85
        )

        return {
            "analysis": result.model_dump(),
            "workflow_id": input_data.workflow_id,
            "auto_execute": not result.requires_approval,
            "reflection_details": {
                "confidence_breakdown": reflection_result.breakdown,
                "improvement_suggestions": reflection_result.suggestions
            }
        }

    def _hierarchical_summarize(self, anomalies: List[Dict]) -> Dict:
        """Hierarchical log summarization for token optimization."""
        summary = {
            "total_anomalies": len(anomalies),
            "by_type": {},
            "by_service": {},
            "representative_samples": []
        }

        # 타입별 그룹화
        for anomaly in anomalies:
            atype = anomaly.get('anomaly_type', 'unknown')
            if atype not in summary['by_type']:
                summary['by_type'][atype] = {
                    'count': 0,
                    'samples': []
                }
            summary['by_type'][atype]['count'] += 1

            # 샘플 로그 제한 (타입당 최대 3개)
            if len(summary['by_type'][atype]['samples']) < 3:
                # 로그에서 핵심 필드만 추출
                sample_logs = anomaly.get('sample_logs', [])[:2]
                compressed_logs = [
                    {
                        'level': log.get('log_level'),
                        'service': log.get('service_name'),
                        'message': log.get('message', '')[:200],  # 메시지 길이 제한
                        'key_metadata': self._extract_key_metadata(log.get('metadata', {}))
                    }
                    for log in sample_logs
                ]
                summary['by_type'][atype]['samples'].extend(compressed_logs)

        # 서비스별 집계
        for anomaly in anomalies:
            service = anomaly.get('service_name', 'unknown')
            if service not in summary['by_service']:
                summary['by_service'][service] = 0
            summary['by_service'][service] += 1

        # 대표 샘플 선택 (전체에서 최대 5개)
        for atype, data in summary['by_type'].items():
            if data['samples']:
                summary['representative_samples'].append({
                    'type': atype,
                    'sample': data['samples'][0]
                })
                if len(summary['representative_samples']) >= 5:
                    break

        return summary

    def _extract_key_metadata(self, metadata: Dict) -> Dict:
        """Extract only key metadata fields."""
        key_fields = ['request_id', 'user_id', 'error_code', 'trace_id', 'status_code']
        return {k: v for k, v in metadata.items() if k in key_fields}

    def _load_knowledge_base(self, anomalies: List[Dict]) -> str:
        """Load relevant knowledge from local knowledge base."""
        # 에러 패턴에서 라이브러리/서비스 감지
        detected_patterns = set()

        for anomaly in anomalies:
            for log in anomaly.get('sample_logs', []):
                message = log.get('message', '').lower()
                # 패턴 매칭
                if 'timeout' in message:
                    detected_patterns.add('timeout')
                if 'connection' in message:
                    detected_patterns.add('connection')
                if 'memory' in message:
                    detected_patterns.add('memory')
                if 'lambda' in message:
                    detected_patterns.add('lambda')

        # 관련 playbook 로딩
        knowledge_parts = []
        knowledge_base_path = os.path.join(
            os.path.dirname(__file__),
            '..', 'knowledge', 'playbooks'
        )

        for pattern in detected_patterns:
            playbook_path = os.path.join(knowledge_base_path, f'{pattern}.md')
            if os.path.exists(playbook_path):
                with open(playbook_path, 'r') as f:
                    knowledge_parts.append(f.read())

        return '\n---\n'.join(knowledge_parts) if knowledge_parts else ''


# Lambda entry point
handler_instance = AnalysisHandler()

@lambda_handler_wrapper
def lambda_handler(event: Dict, context: Any, log) -> Dict:
    return handler_instance.handle(event, context)
```

---

## Phase 3: Core Services

### 3.1 LLM Client (vLLM / Gemini 통합)

```python
# src/services/llm_client.py
import json
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import structlog

logger = structlog.get_logger()


class BaseLLMProvider(ABC):
    """LLM Provider 추상 클래스"""

    @abstractmethod
    def invoke(self, prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
        pass

    @abstractmethod
    def invoke_with_system(self, system_prompt: str, user_prompt: str,
                          max_tokens: int, temperature: float) -> Dict[str, Any]:
        pass


class VLLMProvider(BaseLLMProvider):
    """vLLM OpenAI Compatible API Provider (On-Premise)"""

    def __init__(self):
        from openai import OpenAI

        self.base_url = os.environ.get('VLLM_BASE_URL', 'http://localhost:8000/v1')
        self.model_name = os.environ.get('VLLM_MODEL_NAME')
        self.api_key = os.environ.get('VLLM_API_KEY', 'EMPTY')  # vLLM은 API key 불필요

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
        """vLLM 호출"""
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
        """시스템 프롬프트와 함께 호출"""
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

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """JSON 응답 파싱"""
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


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider (Public Mock)"""

    def __init__(self):
        import google.generativeai as genai

        self.api_key = os.environ.get('GEMINI_API_KEY')
        self.model_id = os.environ.get('GEMINI_MODEL_ID', 'gemini-2.5-pro')

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
        """Gemini 호출"""
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
        """시스템 프롬프트와 함께 호출"""
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"
        return self.invoke(combined_prompt, max_tokens, temperature)

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """JSON 응답 파싱"""
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


class LLMClient:
    """통합 LLM 클라이언트 - Provider 자동 선택"""

    def __init__(self, provider: Optional[str] = None):
        provider = provider or os.environ.get('LLM_PROVIDER', 'vllm')

        if provider == 'vllm':
            self._provider = VLLMProvider()
        elif provider == 'gemini':
            self._provider = GeminiProvider()
        else:
            raise ValueError(f"지원하지 않는 LLM provider: {provider}")

        self.logger = logger.bind(service="llm_client", provider=provider)

    def invoke(self, prompt: str, max_tokens: int = 4096,
               temperature: float = 0.3) -> Dict[str, Any]:
        """LLM 호출"""
        return self._provider.invoke(prompt, max_tokens, temperature)

    def invoke_with_system(self, system_prompt: str, user_prompt: str,
                          max_tokens: int = 4096, temperature: float = 0.3) -> Dict[str, Any]:
        """시스템 프롬프트와 함께 호출"""
        return self._provider.invoke_with_system(
            system_prompt, user_prompt, max_tokens, temperature
        )
```

### 3.2 Reflection Engine

신뢰도 평가 및 리플렉션 엔진:

```python
# src/services/reflection_engine.py
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import structlog

logger = structlog.get_logger()


@dataclass
class ReflectionResult:
    """Result of reflection evaluation."""
    confidence: float
    reasoning: str
    breakdown: Dict[str, float]
    suggestions: List[str]
    requires_replan: bool


class ReflectionEngine:
    """Engine for evaluating analysis quality and confidence."""

    # 신뢰도 임계값
    AUTO_EXECUTE_THRESHOLD = 0.85
    APPROVAL_THRESHOLD = 0.5

    def __init__(self):
        self.logger = logger.bind(service="reflection_engine")

    def evaluate(
        self,
        analysis: Dict[str, Any],
        evidence: Dict[str, Any],
        context: List[Dict]
    ) -> ReflectionResult:
        """Evaluate analysis quality and calculate confidence score."""

        # 1. 증거 충분성 평가 (0.0-1.0)
        evidence_score = self._evaluate_evidence_sufficiency(analysis, evidence)

        # 2. 논리적 일관성 평가 (0.0-1.0)
        logic_score = self._evaluate_logical_consistency(analysis)

        # 3. 실행 가능성 평가 (0.0-1.0)
        actionability_score = self._evaluate_actionability(analysis)

        # 4. 이전 시도와의 일관성 (0.0-1.0)
        consistency_score = self._evaluate_consistency(analysis, context)

        # 가중 평균 계산
        weights = {
            'evidence': 0.35,
            'logic': 0.25,
            'actionability': 0.25,
            'consistency': 0.15
        }

        overall_confidence = (
            evidence_score * weights['evidence'] +
            logic_score * weights['logic'] +
            actionability_score * weights['actionability'] +
            consistency_score * weights['consistency']
        )

        breakdown = {
            'evidence_sufficiency': evidence_score,
            'logical_consistency': logic_score,
            'actionability': actionability_score,
            'consistency': consistency_score
        }

        # 개선 제안 생성
        suggestions = self._generate_suggestions(breakdown)

        # 리플랜 필요 여부 결정
        requires_replan = overall_confidence < self.APPROVAL_THRESHOLD

        reasoning = self._generate_reasoning(breakdown, overall_confidence)

        self.logger.info(
            "reflection_complete",
            confidence=overall_confidence,
            breakdown=breakdown,
            requires_replan=requires_replan
        )

        return ReflectionResult(
            confidence=round(overall_confidence, 3),
            reasoning=reasoning,
            breakdown=breakdown,
            suggestions=suggestions,
            requires_replan=requires_replan
        )

    def _evaluate_evidence_sufficiency(
        self,
        analysis: Dict,
        evidence: Dict
    ) -> float:
        """Evaluate if there's sufficient evidence for conclusions."""
        score = 0.0
        factors = []

        # 증거 목록 존재 여부
        evidence_list = analysis.get('evidence', [])
        if evidence_list:
            score += 0.3
            factors.append("evidence_provided")

        # 증거 개수
        if len(evidence_list) >= 3:
            score += 0.2
            factors.append("multiple_evidence")
        elif len(evidence_list) >= 1:
            score += 0.1

        # 로그 샘플과의 연관성
        sample_count = evidence.get('total_anomalies', 0)
        if sample_count > 0 and evidence_list:
            score += 0.3
            factors.append("evidence_from_logs")

        # 구체적인 타임스탬프/ID 언급
        root_cause = analysis.get('root_cause', '')
        if any(indicator in root_cause.lower() for indicator in ['timestamp', 'id', 'request', 'trace']):
            score += 0.2
            factors.append("specific_references")

        return min(1.0, score)

    def _evaluate_logical_consistency(self, analysis: Dict) -> float:
        """Evaluate logical consistency of the analysis."""
        score = 0.5  # 기본 점수

        root_cause = analysis.get('root_cause', '')
        actions = analysis.get('actions', [])
        evidence = analysis.get('evidence', [])

        # 근본 원인과 액션의 연관성
        if root_cause and actions:
            # 간단한 휴리스틱: 키워드 매칭
            root_cause_words = set(root_cause.lower().split())
            for action in actions:
                action_desc = action.get('description', '').lower()
                if any(word in action_desc for word in root_cause_words if len(word) > 4):
                    score += 0.1

        # 증거가 결론을 지지하는지
        if evidence and root_cause:
            evidence_text = ' '.join(str(e) for e in evidence).lower()
            if any(word in evidence_text for word in root_cause.lower().split() if len(word) > 4):
                score += 0.2

        # 액션에 구체적인 파라미터가 있는지
        for action in actions:
            if action.get('parameters') and len(action.get('parameters', {})) > 0:
                score += 0.1
                break

        return min(1.0, score)

    def _evaluate_actionability(self, analysis: Dict) -> float:
        """Evaluate if recommended actions are executable."""
        score = 0.0
        actions = analysis.get('actions', [])

        if not actions:
            return 0.0

        valid_action_types = {
            'lambda_restart', 'rds_parameter', 'auto_scaling',
            'eventbridge_event', 'notify', 'investigate'
        }

        for action in actions:
            action_type = action.get('type', '')

            # 알려진 액션 타입인지
            if action_type in valid_action_types:
                score += 0.3

            # 필수 파라미터가 있는지
            params = action.get('parameters', {})
            if params:
                score += 0.2

                # 파라미터 값이 구체적인지 (placeholder가 아닌지)
                param_values = [str(v) for v in params.values()]
                if not any('placeholder' in v.lower() or 'xxx' in v.lower() for v in param_values):
                    score += 0.2

        # 액션 수로 정규화
        return min(1.0, score / max(1, len(actions)))

    def _evaluate_consistency(
        self,
        analysis: Dict,
        context: List[Dict]
    ) -> float:
        """Evaluate consistency with previous attempts."""
        # 이전 시도가 없으면 높은 점수
        if not context:
            return 0.9

        # 이전 실패한 액션을 다시 제안하지 않는지 확인
        current_actions = set(
            action.get('type', '')
            for action in analysis.get('actions', [])
        )

        for prev in context:
            if prev.get('status') == 'failed':
                failed_actions = set(
                    action.get('type', '')
                    for action in prev.get('actions', [])
                )
                # 실패한 액션을 다시 제안하면 점수 감소
                overlap = current_actions & failed_actions
                if overlap:
                    return 0.3

        return 0.9

    def _generate_suggestions(self, breakdown: Dict[str, float]) -> List[str]:
        """Generate improvement suggestions based on scores."""
        suggestions = []

        if breakdown['evidence_sufficiency'] < 0.6:
            suggestions.append("Collect more specific log entries related to the anomaly")
            suggestions.append("Include timestamps and request IDs in evidence")

        if breakdown['logical_consistency'] < 0.6:
            suggestions.append("Ensure recommended actions directly address root cause")
            suggestions.append("Verify evidence supports the stated conclusions")

        if breakdown['actionability'] < 0.6:
            suggestions.append("Provide specific parameters for each recommended action")
            suggestions.append("Use supported action types (lambda_restart, rds_parameter, etc.)")

        if breakdown['consistency'] < 0.6:
            suggestions.append("Avoid recommending previously failed actions")
            suggestions.append("Consider alternative approaches if previous attempts failed")

        return suggestions

    def _generate_reasoning(
        self,
        breakdown: Dict[str, float],
        overall: float
    ) -> str:
        """Generate human-readable reasoning for the confidence score."""
        parts = []

        parts.append(f"Overall confidence: {overall:.1%}")
        parts.append("")

        for factor, score in breakdown.items():
            status = "Strong" if score >= 0.8 else "Moderate" if score >= 0.5 else "Weak"
            parts.append(f"- {factor.replace('_', ' ').title()}: {status} ({score:.1%})")

        parts.append("")

        if overall >= self.AUTO_EXECUTE_THRESHOLD:
            parts.append("Recommendation: Safe for automatic execution")
        elif overall >= self.APPROVAL_THRESHOLD:
            parts.append("Recommendation: Requires human approval before execution")
        else:
            parts.append("Recommendation: Replan with additional context needed")

        return '\n'.join(parts)
```

---

## Phase 4: Prompt Templates

### 4.1 Analysis Prompts

```python
# src/prompts/analysis_prompts.py
from typing import Dict, List, Any, Optional
import json


class AnalysisPrompts:
    """Prompt templates for analysis operations."""

    ANALYSIS_SYSTEM_PROMPT = """You are an expert DevOps engineer specialized in:
- AWS infrastructure troubleshooting
- Log analysis and anomaly detection
- Root cause analysis
- Automated remediation strategies

You analyze system anomalies and provide actionable remediation recommendations.
Always respond in valid JSON format."""

    ANALYSIS_TEMPLATE = """## Task
Analyze the following system anomalies and provide root cause analysis with remediation recommendations.

## Anomaly Summary
{anomaly_summary}

## Log Samples
{log_samples}

## Relevant Knowledge
{knowledge_context}

{previous_attempts_section}

## Response Format
Respond with a JSON object containing:
```json
{{
    "root_cause": "Clear description of the identified root cause",
    "evidence": [
        "Evidence point 1 with specific log reference",
        "Evidence point 2 with metric correlation"
    ],
    "actions": [
        {{
            "type": "action_type",
            "description": "What this action does",
            "parameters": {{}},
            "priority": "high|medium|low",
            "estimated_impact": "Description of expected outcome"
        }}
    ],
    "confidence_factors": {{
        "evidence_strength": "strong|moderate|weak",
        "pattern_match": "exact|partial|inferred",
        "risk_level": "low|medium|high"
    }},
    "alternative_hypotheses": [
        "Alternative explanation 1",
        "Alternative explanation 2"
    ]
}}
```

## Supported Action Types
- lambda_restart: Restart a Lambda function
- rds_parameter: Modify RDS parameter
- auto_scaling: Adjust Auto Scaling settings
- eventbridge_event: Publish event for notification
- investigate: Request more information

## Important Guidelines
1. Base conclusions on provided evidence only
2. Prefer less invasive actions when confidence is moderate
3. Always include rollback considerations for destructive actions
4. If evidence is insufficient, use "investigate" action type"""

    REPLAN_TEMPLATE = """## Task
The previous remediation attempt did not fully resolve the issue. Reanalyze with new information.

## Original Analysis
{original_analysis}

## Previous Actions Taken
{previous_actions}

## Current Status
{current_status}

## New Observations
{new_observations}

## Instructions
1. Identify why the previous approach may have failed
2. Consider alternative root causes
3. Propose modified or new remediation actions
4. Avoid repeating failed approaches

Respond in the same JSON format as the original analysis."""

    REFLECTION_TEMPLATE = """## Task
Evaluate the quality of the following analysis.

## Analysis to Evaluate
{analysis}

## Available Evidence
{evidence}

## Evaluation Criteria
1. Evidence Sufficiency: Are conclusions supported by concrete evidence?
2. Logical Consistency: Do actions address the identified root cause?
3. Actionability: Are recommended actions specific and executable?
4. Risk Assessment: Are potential risks properly considered?

## Response Format
```json
{{
    "evaluation": {{
        "evidence_sufficiency": {{
            "score": 0.0-1.0,
            "reasoning": "explanation"
        }},
        "logical_consistency": {{
            "score": 0.0-1.0,
            "reasoning": "explanation"
        }},
        "actionability": {{
            "score": 0.0-1.0,
            "reasoning": "explanation"
        }},
        "risk_assessment": {{
            "score": 0.0-1.0,
            "reasoning": "explanation"
        }}
    }},
    "overall_confidence": 0.0-1.0,
    "improvement_suggestions": [
        "Suggestion 1",
        "Suggestion 2"
    ],
    "proceed_recommendation": "auto_execute|request_approval|replan"
}}
```"""

    def format_analysis_prompt(
        self,
        anomalies: List[Dict],
        log_summary: Dict,
        knowledge: str = "",
        previous_attempts: Optional[List[Dict]] = None
    ) -> str:
        """Format the analysis prompt with provided data."""

        # Anomaly 요약
        anomaly_summary = self._format_anomaly_summary(anomalies)

        # 로그 샘플
        log_samples = self._format_log_samples(log_summary)

        # 이전 시도 섹션
        previous_section = ""
        if previous_attempts:
            previous_section = self._format_previous_attempts(previous_attempts)

        return self.ANALYSIS_TEMPLATE.format(
            anomaly_summary=anomaly_summary,
            log_samples=log_samples,
            knowledge_context=knowledge or "No specific knowledge base entries found.",
            previous_attempts_section=previous_section
        )

    def _format_anomaly_summary(self, anomalies: List[Dict]) -> str:
        """Format anomaly data for prompt."""
        lines = [f"Total anomalies detected: {len(anomalies)}"]

        # 타입별 그룹화
        by_type = {}
        for a in anomalies:
            atype = a.get('anomaly_type', 'unknown')
            if atype not in by_type:
                by_type[atype] = []
            by_type[atype].append(a)

        for atype, items in by_type.items():
            lines.append(f"\n### {atype}")
            lines.append(f"- Count: {len(items)}")
            if items:
                lines.append(f"- Services affected: {', '.join(set(i.get('service_name', 'unknown') for i in items))}")

        return '\n'.join(lines)

    def _format_log_samples(self, log_summary: Dict) -> str:
        """Format log summary for prompt."""
        if not log_summary:
            return "No log samples available."

        lines = []

        # 대표 샘플
        samples = log_summary.get('representative_samples', [])
        if samples:
            lines.append("### Representative Log Samples")
            for sample in samples[:5]:
                lines.append(f"\n**Type: {sample.get('type')}**")
                s = sample.get('sample', {})
                lines.append(f"- Service: {s.get('service')}")
                lines.append(f"- Level: {s.get('level')}")
                lines.append(f"- Message: {s.get('message', '')[:300]}")
                if s.get('key_metadata'):
                    lines.append(f"- Metadata: {json.dumps(s.get('key_metadata'))}")

        return '\n'.join(lines)

    def _format_previous_attempts(self, attempts: List[Dict]) -> str:
        """Format previous attempt history."""
        if not attempts:
            return ""

        lines = ["\n## Previous Attempts"]
        for i, attempt in enumerate(attempts, 1):
            lines.append(f"\n### Attempt {i}")
            lines.append(f"- Status: {attempt.get('status', 'unknown')}")
            lines.append(f"- Root Cause Identified: {attempt.get('root_cause', 'N/A')[:200]}")

            actions = attempt.get('actions', [])
            if actions:
                lines.append("- Actions Taken:")
                for action in actions:
                    lines.append(f"  - {action.get('type')}: {action.get('description', '')[:100]}")

            if attempt.get('failure_reason'):
                lines.append(f"- Failure Reason: {attempt.get('failure_reason')}")

        return '\n'.join(lines)

    def format_replan_prompt(
        self,
        original_analysis: Dict,
        previous_actions: List[Dict],
        current_status: str,
        new_observations: str
    ) -> str:
        """Format the replan prompt."""
        return self.REPLAN_TEMPLATE.format(
            original_analysis=json.dumps(original_analysis, indent=2),
            previous_actions=json.dumps(previous_actions, indent=2),
            current_status=current_status,
            new_observations=new_observations
        )

    def format_reflection_prompt(
        self,
        analysis: Dict,
        evidence: Dict
    ) -> str:
        """Format the reflection prompt."""
        return self.REFLECTION_TEMPLATE.format(
            analysis=json.dumps(analysis, indent=2),
            evidence=json.dumps(evidence, indent=2)
        )
```

---

## Phase 5: Step Functions Workflow

### 5.1 Main Workflow Definition

```json
{
  "Comment": "BDP Agent Main Workflow - Detection, Analysis, Remediation",
  "StartAt": "DetectAnomalies",
  "States": {
    "DetectAnomalies": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:bdp-detection",
      "Parameters": {
        "time_range_minutes": 10,
        "severity_threshold": "ERROR"
      },
      "ResultPath": "$.detection",
      "Next": "CheckAnomaliesDetected",
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
          "IntervalSeconds": 2,
          "MaxAttempts": 3,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.error",
          "Next": "HandleError"
        }
      ]
    },

    "CheckAnomaliesDetected": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.detection.anomalies_detected",
          "BooleanEquals": true,
          "Next": "AnalyzeRootCause"
        }
      ],
      "Default": "NoAnomaliesFound"
    },

    "NoAnomaliesFound": {
      "Type": "Succeed",
      "Comment": "No anomalies detected, workflow complete"
    },

    "AnalyzeRootCause": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:bdp-analysis",
      "Parameters": {
        "anomalies.$": "$.detection.anomalies",
        "workflow_id.$": "$$.Execution.Id",
        "previous_attempts.$": "$.previous_attempts"
      },
      "ResultPath": "$.analysis",
      "Next": "EvaluateConfidence",
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException"],
          "IntervalSeconds": 5,
          "MaxAttempts": 2,
          "BackoffRate": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.error",
          "Next": "HandleError"
        }
      ]
    },

    "EvaluateConfidence": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.analysis.analysis.confidence",
          "NumericGreaterThanEquals": 0.85,
          "Next": "AutoExecuteRemediation"
        },
        {
          "Variable": "$.analysis.analysis.confidence",
          "NumericGreaterThanEquals": 0.5,
          "Next": "RequestApproval"
        }
      ],
      "Default": "EscalateToHuman"
    },

    "AutoExecuteRemediation": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:bdp-remediation",
      "Parameters": {
        "actions.$": "$.analysis.analysis.recommended_actions",
        "workflow_id.$": "$$.Execution.Id",
        "auto_approved": true
      },
      "ResultPath": "$.remediation",
      "Next": "ReflectOnResult",
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException"],
          "IntervalSeconds": 2,
          "MaxAttempts": 2
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.error",
          "Next": "HandleRemediationError"
        }
      ]
    },

    "RequestApproval": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
      "Parameters": {
        "FunctionName": "bdp-approval",
        "Payload": {
          "analysis.$": "$.analysis",
          "taskToken.$": "$$.Task.Token"
        }
      },
      "ResultPath": "$.approval",
      "TimeoutSeconds": 3600,
      "Next": "CheckApprovalResult",
      "Catch": [
        {
          "ErrorEquals": ["States.Timeout"],
          "ResultPath": "$.error",
          "Next": "ApprovalTimeout"
        }
      ]
    },

    "CheckApprovalResult": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.approval.approved",
          "BooleanEquals": true,
          "Next": "ExecuteApprovedRemediation"
        }
      ],
      "Default": "ApprovalRejected"
    },

    "ExecuteApprovedRemediation": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:bdp-remediation",
      "Parameters": {
        "actions.$": "$.analysis.analysis.recommended_actions",
        "workflow_id.$": "$$.Execution.Id",
        "approved_by.$": "$.approval.approved_by"
      },
      "ResultPath": "$.remediation",
      "Next": "ReflectOnResult"
    },

    "ReflectOnResult": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:bdp-analysis",
      "Parameters": {
        "mode": "reflection",
        "remediation_result.$": "$.remediation",
        "original_analysis.$": "$.analysis"
      },
      "ResultPath": "$.reflection",
      "Next": "CheckReflectionResult"
    },

    "CheckReflectionResult": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.reflection.success",
          "BooleanEquals": true,
          "Next": "WorkflowSuccess"
        },
        {
          "Variable": "$.reflection.requires_replan",
          "BooleanEquals": true,
          "Next": "CheckReplanAttempts"
        }
      ],
      "Default": "WorkflowSuccess"
    },

    "CheckReplanAttempts": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.replan_count",
          "NumericLessThan": 3,
          "Next": "IncrementReplanCount"
        }
      ],
      "Default": "MaxReplansReached"
    },

    "IncrementReplanCount": {
      "Type": "Pass",
      "Parameters": {
        "replan_count.$": "States.MathAdd($.replan_count, 1)",
        "previous_attempts.$": "States.Array($.analysis)"
      },
      "ResultPath": "$",
      "Next": "AnalyzeRootCause"
    },

    "MaxReplansReached": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:bdp-notification",
      "Parameters": {
        "type": "ESCALATION",
        "reason": "Maximum replan attempts reached",
        "workflow_id.$": "$$.Execution.Id",
        "context.$": "$"
      },
      "Next": "EscalateToHuman"
    },

    "EscalateToHuman": {
      "Type": "Task",
      "Resource": "arn:aws:events:::event-bus/default",
      "Parameters": {
        "Entries": [
          {
            "Source": "bdp-agent",
            "DetailType": "ESCALATION_REQUIRED",
            "Detail": {
              "workflow_id.$": "$$.Execution.Id",
              "reason": "Low confidence analysis requires human review",
              "analysis.$": "$.analysis"
            }
          }
        ]
      },
      "Next": "WorkflowEscalated"
    },

    "WorkflowSuccess": {
      "Type": "Task",
      "Resource": "arn:aws:events:::event-bus/default",
      "Parameters": {
        "Entries": [
          {
            "Source": "bdp-agent",
            "DetailType": "REMEDIATION_SUCCESS",
            "Detail": {
              "workflow_id.$": "$$.Execution.Id",
              "summary.$": "$.reflection"
            }
          }
        ]
      },
      "Next": "Success"
    },

    "Success": {
      "Type": "Succeed"
    },

    "WorkflowEscalated": {
      "Type": "Succeed",
      "Comment": "Workflow escalated to human review"
    },

    "ApprovalRejected": {
      "Type": "Succeed",
      "Comment": "Remediation rejected by approver"
    },

    "ApprovalTimeout": {
      "Type": "Task",
      "Resource": "arn:aws:events:::event-bus/default",
      "Parameters": {
        "Entries": [
          {
            "Source": "bdp-agent",
            "DetailType": "APPROVAL_TIMEOUT",
            "Detail": {
              "workflow_id.$": "$$.Execution.Id"
            }
          }
        ]
      },
      "Next": "WorkflowEscalated"
    },

    "HandleError": {
      "Type": "Task",
      "Resource": "arn:aws:events:::event-bus/default",
      "Parameters": {
        "Entries": [
          {
            "Source": "bdp-agent",
            "DetailType": "WORKFLOW_ERROR",
            "Detail": {
              "workflow_id.$": "$$.Execution.Id",
              "error.$": "$.error"
            }
          }
        ]
      },
      "Next": "WorkflowFailed"
    },

    "HandleRemediationError": {
      "Type": "Task",
      "Resource": "arn:aws:events:::event-bus/default",
      "Parameters": {
        "Entries": [
          {
            "Source": "bdp-agent",
            "DetailType": "REMEDIATION_ERROR",
            "Detail": {
              "workflow_id.$": "$$.Execution.Id",
              "error.$": "$.error"
            }
          }
        ]
      },
      "Next": "CheckReplanAttempts"
    },

    "WorkflowFailed": {
      "Type": "Fail",
      "Error": "WorkflowError",
      "Cause": "Workflow failed due to unrecoverable error"
    }
  }
}
```

---

## Phase 6: Deployment

### 6.1 CDK Stack (Python)

```python
# infra/cdk/bdp_agent_stack.py
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_lambda as lambda_,
    aws_lambda_python_alpha as lambda_python,
    aws_dynamodb as dynamodb,
    aws_stepfunctions as sfn,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
)
from constructs import Construct


class BdpAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB Tables
        dedup_table = dynamodb.Table(
            self, "AnomalyTracking",
            table_name="bdp-anomaly-tracking",
            partition_key=dynamodb.Attribute(
                name="signature",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl"
        )

        workflow_table = dynamodb.Table(
            self, "WorkflowState",
            table_name="bdp-workflow-state",
            partition_key=dynamodb.Attribute(
                name="workflow_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Common Lambda configuration
        common_lambda_props = {
            "runtime": lambda_.Runtime.PYTHON_3_11,
            "architecture": lambda_.Architecture.ARM_64,
            "timeout": Duration.seconds(60),
            "memory_size": 512,
        }

        # Detection Lambda
        detection_fn = lambda_python.PythonFunction(
            self, "DetectionFunction",
            entry="src/handlers",
            index="detection_handler.py",
            handler="lambda_handler",
            function_name="bdp-detection",
            environment={
                "DEDUP_TABLE": dedup_table.table_name,
                "RDS_CLUSTER_ARN": "your-rds-cluster-arn",
                "RDS_SECRET_ARN": "your-rds-secret-arn",
            },
            **common_lambda_props
        )

        # Analysis Lambda
        analysis_fn = lambda_python.PythonFunction(
            self, "AnalysisFunction",
            entry="src/handlers",
            index="analysis_handler.py",
            handler="lambda_handler",
            function_name="bdp-analysis",
            memory_size=1024,
            timeout=Duration.seconds(120),
            environment={
                # vLLM (On-Premise) 설정
                "LLM_PROVIDER": "vllm",  # 또는 "gemini"
                "VLLM_BASE_URL": "http://your-vllm-server:8000/v1",
                "VLLM_MODEL_NAME": "your-model-name",
                # Gemini (Public Mock) 설정 - 필요시 활성화
                # "LLM_PROVIDER": "gemini",
                # "GEMINI_MODEL_ID": "gemini-2.5-pro",
            },
            runtime=lambda_.Runtime.PYTHON_3_11,
            architecture=lambda_.Architecture.ARM_64,
        )

        # Grant permissions
        dedup_table.grant_read_write_data(detection_fn)

        # VPC 설정 (vLLM On-Prem 접근 시 필요)
        # analysis_fn.add_to_role_policy(iam.PolicyStatement(
        #     actions=["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces"],
        #     resources=["*"]
        # ))

        # Secrets Manager 접근 (API 키 저장 시)
        analysis_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=["arn:aws:secretsmanager:*:*:secret:bdp-llm-*"]
        ))

        # Step Functions
        with open("step_functions/bdp_workflow.asl.json") as f:
            workflow_definition = f.read()

        state_machine = sfn.StateMachine(
            self, "BdpWorkflow",
            state_machine_name="bdp-main-workflow",
            definition_body=sfn.DefinitionBody.from_string(workflow_definition),
            timeout=Duration.minutes(30)
        )

        # EventBridge Schedule
        detection_rule = events.Rule(
            self, "DetectionSchedule",
            schedule=events.Schedule.rate(Duration.minutes(5)),
            targets=[targets.SfnStateMachine(state_machine)]
        )

        # Warmup Rule (Cold Start 제거)
        warmup_rule = events.Rule(
            self, "WarmupSchedule",
            schedule=events.Schedule.rate(Duration.minutes(5)),
            targets=[
                targets.LambdaFunction(detection_fn),
                targets.LambdaFunction(analysis_fn)
            ]
        )
```

---

## Testing

### Unit Test Example

```python
# tests/unit/test_reflection_engine.py
import pytest
from src.services.reflection_engine import ReflectionEngine


class TestReflectionEngine:
    def setup_method(self):
        self.engine = ReflectionEngine()

    def test_high_confidence_analysis(self):
        """Test that well-structured analysis gets high confidence."""
        analysis = {
            "root_cause": "Database connection pool exhausted due to connection leak in user-service",
            "evidence": [
                "RDS connection count exceeded 80% threshold at 14:32:00",
                "user-service logs show 'connection timeout' errors starting 14:30:00",
                "No connection release in /api/users endpoint handler"
            ],
            "actions": [
                {
                    "type": "rds_parameter",
                    "description": "Increase max_connections",
                    "parameters": {"parameter_name": "max_connections", "new_value": "200"},
                    "priority": "high"
                },
                {
                    "type": "lambda_restart",
                    "description": "Restart user-service to clear stale connections",
                    "parameters": {"function_name": "user-service"},
                    "priority": "high"
                }
            ]
        }

        evidence = {
            "total_anomalies": 3,
            "representative_samples": [
                {"type": "connection_error", "sample": {"level": "ERROR"}}
            ]
        }

        result = self.engine.evaluate(analysis, evidence, [])

        assert result.confidence >= 0.7
        assert not result.requires_replan

    def test_low_evidence_gets_low_confidence(self):
        """Test that analysis without evidence gets low confidence."""
        analysis = {
            "root_cause": "Something is wrong",
            "evidence": [],
            "actions": []
        }

        result = self.engine.evaluate(analysis, {}, [])

        assert result.confidence < 0.5
        assert result.requires_replan
```

---

## Monitoring & Observability

### CloudWatch Dashboard Template

```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "title": "Detection Lambda Performance",
        "metrics": [
          ["AWS/Lambda", "Invocations", "FunctionName", "bdp-detection"],
          [".", "Errors", ".", "."],
          [".", "Duration", ".", ".", {"stat": "p95"}]
        ],
        "period": 300
      }
    },
    {
      "type": "metric",
      "properties": {
        "title": "Analysis Lambda Performance",
        "metrics": [
          ["AWS/Lambda", "Invocations", "FunctionName", "bdp-analysis"],
          [".", "Duration", ".", ".", {"stat": "p95"}]
        ],
        "period": 300
      }
    },
    {
      "type": "metric",
      "properties": {
        "title": "Step Functions Executions",
        "metrics": [
          ["AWS/States", "ExecutionsStarted", "StateMachineArn", "${StateMachineArn}"],
          [".", "ExecutionsSucceeded", ".", "."],
          [".", "ExecutionsFailed", ".", "."]
        ],
        "period": 300
      }
    },
    {
      "type": "metric",
      "properties": {
        "title": "LLM Usage (Custom Metrics)",
        "metrics": [
          ["BDP/LLM", "InvocationCount"],
          [".", "InputTokenCount"],
          [".", "OutputTokenCount"],
          [".", "Latency", {"stat": "p99"}]
        ],
        "period": 3600
      }
    }
  ]
}
```

---

## Best Practices Checklist

### Security
- [ ] IAM 최소 권한 원칙 적용
- [ ] 환경 변수 암호화 (KMS)
- [ ] RDS 접근에 Secrets Manager 사용
- [ ] VPC 엔드포인트로 private 통신
- [ ] Gemini API 키는 Secrets Manager에 저장
- [ ] vLLM 서버 접근은 VPC 내부 통신

### Cost Optimization
- [ ] ARM64/Graviton2 아키텍처 사용
- [ ] Provisioned Concurrency 대신 EventBridge Warmup
- [ ] CloudWatch Field Indexing 활성화
- [ ] Hierarchical Summarization으로 토큰 절감
- [ ] 개발 환경에서는 Gemini Flash 사용 (비용 절감)

### Reliability
- [ ] Step Functions Retry 설정
- [ ] DLQ 구성
- [ ] Circuit breaker 패턴 적용
- [ ] Multi-AZ 배포

### Observability
- [ ] Structured logging (structlog)
- [ ] CloudWatch Dashboards
- [ ] X-Ray tracing 활성화
- [ ] 알람 설정 (에러율, 지연시간)
