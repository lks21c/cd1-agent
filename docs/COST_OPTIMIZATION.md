# BDP Agent Cost Optimization Guide

## Overview

BDP Agent는 비용 효율성을 핵심 설계 원칙으로 삼아, 다양한 최적화 기법을 통해 AWS 비용을 최소화합니다.

### LLM Provider별 비용 구조

| Provider | 환경 | 비용 모델 |
|----------|------|----------|
| **vLLM (On-Prem)** | 프로덕션 | 고정 인프라 비용 (GPU 서버) |
| **Gemini 2.5 Pro** | Mock/개발 | ~$0.00125/1K input, ~$0.005/1K output |
| **Gemini 2.5 Flash** | Mock/개발 | ~$0.00015/1K input, ~$0.0006/1K output |

### 예상 비용 절감 효과

| 최적화 기법 | 절감률 | 적용 난이도 |
|------------|--------|-------------|
| CloudWatch Field Indexing | 67% (데이터 스캔) | 쉬움 |
| ARM64/Graviton2 | 20-34% (Lambda) | 쉬움 |
| Hierarchical Summarization | 80-90% (토큰) | 중간 |
| Deduplication | 50%+ (LLM 호출) | 중간 |
| Pre-aggregated Metrics | 90%+ (쿼리) | 중간 |
| EventBridge Warmup | Cold start 제거 | 쉬움 |

---

## 1. Log Querying Optimization

### 1.1 CloudWatch Field Indexing (무료, 67% 감소)

CloudWatch Field Indexing을 사용하면 로그 쿼리 시 데이터 스캔량을 67%까지 줄일 수 있습니다.

#### 설정 방법

```bash
# CLI로 필드 인덱스 생성
aws logs create-field-index \
  --log-group-name /aws/lambda/api-handler \
  --field-index-name requestId

aws logs create-field-index \
  --log-group-name /aws/lambda/api-handler \
  --field-index-name level
```

#### 인덱싱 권장 필드

| 필드명 | 용도 | 카디널리티 |
|--------|------|-----------|
| `requestId` | 요청 추적 | 높음 |
| `level` | 로그 레벨 필터링 | 낮음 |
| `errorCode` | 에러 유형 필터링 | 중간 |
| `resource_id` | 리소스별 필터링 | 중간 |

#### 쿼리 최적화

```python
# BAD: 전체 스캔
response = logs_client.filter_log_events(
    logGroupName='/aws/lambda/api-handler',
    filterPattern='ERROR'  # 전체 데이터 스캔
)

# GOOD: 인덱스 사용
response = logs_client.start_query(
    logGroupName='/aws/lambda/api-handler',
    queryString='''
        fields @timestamp, @message
        | filter level = "ERROR"  # 인덱스된 필드 사용
        | sort @timestamp desc
        | limit 100
    '''
)
```

#### 비용 비교

```
Before (Full Scan):
- 1000 TB 스캔 × $0.0051/GB = $5,120

After (Field Indexing):
- 333 TB 스캔 × $0.0051/GB = $1,704
- 절감: $3,416 (67%)
```

### 1.2 RDS 통합로그 최적화

#### JSON 파싱 최소화

```python
class LogQueryService:
    """비용 효율적인 로그 쿼리 서비스"""

    async def query_rds_logs(
        self,
        time_range: tuple,
        filters: dict,
        limit: int = 100
    ) -> list:
        """RDS 통합로그 쿼리 (비용 최적화)"""

        # 1. 필요한 컬럼만 선택 (SELECT *)
        query = """
            SELECT id, timestamp, service_name, log_level, message
            FROM integrated_logs
            WHERE timestamp BETWEEN %s AND %s
            AND log_level IN ('ERROR', 'CRITICAL')
            ORDER BY timestamp DESC
            LIMIT %s
        """

        # 2. JSON 파싱은 Python에서 (DB 부하 감소)
        rows = await self.execute_query(query, (*time_range, limit))

        # 3. 필요한 경우에만 metadata JSON 파싱
        return [self._parse_if_needed(row) for row in rows]

    def _parse_if_needed(self, row: dict) -> dict:
        """필요 시에만 JSON 파싱 (지연 파싱)"""
        # metadata 컬럼은 필요할 때만 파싱
        return row  # metadata는 분석 단계에서 파싱
```

#### 쿼리 결과 캐싱

```python
import hashlib
from datetime import timedelta

class QueryCache:
    """쿼리 결과 캐싱 (DynamoDB)"""

    def __init__(self, table_name: str = "bdp-query-cache"):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        self.cache_ttl = timedelta(minutes=5)

    def _generate_cache_key(self, query: str, params: tuple) -> str:
        content = f"{query}:{params}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    async def get_or_fetch(self, query: str, params: tuple, fetch_fn) -> list:
        cache_key = self._generate_cache_key(query, params)

        # 캐시 확인
        cached = self.table.get_item(Key={'cache_key': cache_key})
        if 'Item' in cached:
            return cached['Item']['result']

        # 캐시 미스: 쿼리 실행
        result = await fetch_fn(query, params)

        # 캐시 저장
        self.table.put_item(Item={
            'cache_key': cache_key,
            'result': result,
            'ttl': int((datetime.utcnow() + self.cache_ttl).timestamp())
        })

        return result
```

---

## 2. Token Optimization (80-90% 절감)

### 2.1 Hierarchical Summarization

로그를 계층적으로 요약하여 LLM에 전달되는 토큰 수를 80-90% 줄입니다.

```python
class TokenOptimizer:
    """토큰 최적화 서비스"""

    MAX_TOKENS_PER_ANALYSIS = 4000  # 분석당 최대 토큰

    async def summarize_logs(self, logs: list[dict]) -> str:
        """계층적 로그 요약"""

        # Level 1: 에러 유형별 그룹화
        grouped = self._group_by_error_type(logs)

        # Level 2: 대표 로그 샘플링 (그룹당 최대 5개)
        sampled = {
            k: self._sample_representative_logs(v, max_samples=5)
            for k, v in grouped.items()
        }

        # Level 3: 핵심 필드만 추출
        extracted = self._extract_key_fields(sampled)

        # Level 4: 최종 포맷팅
        return self._format_summary(extracted)

    def _group_by_error_type(self, logs: list[dict]) -> dict:
        """에러 유형별 그룹화"""
        groups = {}
        for log in logs:
            error_type = self._classify_error(log.get('message', ''))
            if error_type not in groups:
                groups[error_type] = []
            groups[error_type].append(log)
        return groups

    def _classify_error(self, message: str) -> str:
        """에러 메시지 분류"""
        patterns = {
            'connection': ['timeout', 'connection', 'refused', 'unreachable'],
            'memory': ['out of memory', 'oom', 'heap'],
            'authentication': ['auth', 'permission', 'forbidden', '403', '401'],
            'database': ['sql', 'query', 'database', 'rds'],
            'other': []
        }

        message_lower = message.lower()
        for category, keywords in patterns.items():
            if any(kw in message_lower for kw in keywords):
                return category
        return 'other'

    def _sample_representative_logs(self, logs: list, max_samples: int = 5) -> list:
        """대표 로그 샘플링"""
        if len(logs) <= max_samples:
            return logs

        # 시간순 분산 샘플링
        step = len(logs) // max_samples
        return [logs[i * step] for i in range(max_samples)]

    def _extract_key_fields(self, grouped: dict) -> dict:
        """핵심 필드만 추출"""
        KEY_FIELDS = ['timestamp', 'level', 'message', 'error_code', 'resource_id']

        result = {}
        for category, logs in grouped.items():
            result[category] = {
                'count': len(logs),
                'samples': [
                    {k: log.get(k) for k in KEY_FIELDS if log.get(k)}
                    for log in logs
                ]
            }
        return result

    def _format_summary(self, extracted: dict) -> str:
        """최종 요약 포맷팅"""
        lines = []
        for category, data in extracted.items():
            lines.append(f"### {category.upper()} ({data['count']}건)")
            for sample in data['samples']:
                lines.append(f"  - [{sample.get('timestamp', 'N/A')}] {sample.get('message', 'N/A')[:100]}")
        return "\n".join(lines)
```

#### 토큰 절감 효과

```
Before (Raw Logs):
- 1000 로그 × 평균 200 토큰 = 200,000 토큰

After (Hierarchical Summarization):
- 그룹화: 5개 카테고리
- 샘플링: 25개 대표 로그
- 추출: 핵심 필드만
- 결과: ~4,000 토큰
- 절감: 98%

Gemini 2.5 Pro 기준 비용:
- Before: 200K × $0.00125/1K = $0.25
- After: 4K × $0.00125/1K = $0.005

Gemini 2.5 Flash 기준 비용:
- Before: 200K × $0.00015/1K = $0.03
- After: 4K × $0.00015/1K = $0.0006
```

### 2.2 Incremental Context

이전 분석 결과를 활용하여 반복 분석을 최소화합니다.

```python
class IncrementalContext:
    """점진적 컨텍스트 관리"""

    def __init__(self):
        self.previous_analyses = []
        self.known_patterns = {}

    def should_analyze(self, anomaly: dict) -> bool:
        """분석 필요 여부 판단"""
        signature = self._get_signature(anomaly)

        # 이미 알려진 패턴이면 이전 분석 재사용
        if signature in self.known_patterns:
            return False

        return True

    def get_context_summary(self) -> str:
        """이전 분석 요약 (토큰 최소화)"""
        if not self.previous_analyses:
            return ""

        # 최근 3개 분석만 요약
        recent = self.previous_analyses[-3:]
        summary = "\n".join([
            f"- {a['timestamp']}: {a['root_cause'][:50]}"
            for a in recent
        ])
        return f"## 최근 분석 히스토리\n{summary}"
```

---

## 3. Lambda Cost Optimization

### 3.1 ARM64/Graviton2 (20-34% 절감)

ARM64 아키텍처는 x86_64 대비 20% 저렴하고 최대 34% 더 빠릅니다.

#### 마이그레이션 체크리스트

```bash
# 1. 종속성 호환성 확인
pip check

# 2. ARM64용 레이어 빌드
docker run --platform linux/arm64 \
  public.ecr.aws/lambda/python:3.12 \
  pip install -t /var/task/python/ boto3 requests

# 3. 함수 설정 업데이트
aws lambda update-function-configuration \
  --function-name bdp-detection \
  --architectures arm64
```

#### CDK 설정

```python
# infra/cdk/bdp_stack.py

from aws_cdk import aws_lambda as lambda_

detection_function = lambda_.Function(
    self, "BdpDetection",
    function_name="bdp-detection",
    runtime=lambda_.Runtime.PYTHON_3_11,
    architecture=lambda_.Architecture.ARM_64,  # ARM64 사용
    memory_size=512,
    timeout=Duration.seconds(60),
    handler="detection_handler.lambda_handler",
    code=lambda_.Code.from_asset("src/handlers")
)
```

#### 비용 비교

```
x86_64 (기준):
- 1024MB × 1M 호출 × 500ms = $8.33/월

ARM64:
- 20% 저렴 + 20% 빠름
- 1024MB × 1M 호출 × 400ms = $5.33/월
- 절감: $3.00/월 (36%)
```

### 3.2 Memory 최적화

Lambda 메모리는 CPU에 비례합니다. Bedrock API 호출은 I/O 바운드이므로 높은 메모리가 필요 없습니다.

```python
# 함수별 권장 메모리

MEMORY_RECOMMENDATIONS = {
    'bdp-detection': 512,    # 로그 쿼리 (I/O 바운드)
    'bdp-analysis': 1024,    # Bedrock 호출 + 로그 처리
    'bdp-remediation': 512,  # AWS API 호출 (I/O 바운드)
    'bdp-approval': 256,     # 간단한 API 핸들러
    'bdp-warmup': 128,       # Ping 전용
}
```

### 3.3 Cold Start 제거 (EventBridge Warmup)

5분마다 Lambda를 워밍하여 Cold Start를 제거합니다.

```python
# src/handlers/warmup_handler.py

import boto3

lambda_client = boto3.client('lambda')

FUNCTIONS_TO_WARM = [
    'bdp-detection',
    'bdp-analysis',
    'bdp-remediation'
]

def lambda_handler(event, context):
    """Lambda 워밍 핸들러"""

    results = []
    for fn_name in FUNCTIONS_TO_WARM:
        try:
            lambda_client.invoke(
                FunctionName=fn_name,
                InvocationType='Event',  # 비동기
                Payload='{"warmup": true}'
            )
            results.append({'function': fn_name, 'status': 'warmed'})
        except Exception as e:
            results.append({'function': fn_name, 'status': 'error', 'error': str(e)})

    return {'results': results}
```

#### EventBridge 규칙

```yaml
# CloudFormation
WarmupRule:
  Type: AWS::Events::Rule
  Properties:
    Name: bdp-warmup-schedule
    ScheduleExpression: rate(5 minutes)
    State: ENABLED
    Targets:
      - Id: warmup-target
        Arn: !GetAtt WarmupFunction.Arn
```

---

## 4. Deduplication (50%+ LLM 호출 절감)

동일한 이상 현상의 중복 분석을 방지합니다.

### 구현

```python
# src/services/deduplication_service.py

import hashlib
from datetime import datetime, timedelta
import boto3

class DeduplicationService:
    """이상 현상 중복 제거 서비스"""

    def __init__(self, table_name: str = "bdp-anomaly-tracking"):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        self.dedup_window = timedelta(hours=1)

    def _generate_signature(self, anomaly: dict) -> str:
        """이상 현상 시그니처 생성"""
        key_fields = [
            anomaly.get('type', ''),
            anomaly.get('source', ''),
            anomaly.get('error_code', ''),
            anomaly.get('resource_id', '')
        ]
        content = "|".join(str(f) for f in key_fields)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def filter_duplicates(self, anomalies: list[dict]) -> list[dict]:
        """중복 이상 현상 필터링"""
        unique = []

        for anomaly in anomalies:
            signature = self._generate_signature(anomaly)

            # DynamoDB에서 최근 기록 확인
            response = self.table.get_item(Key={'signature': signature})

            if 'Item' in response:
                last_seen = datetime.fromisoformat(response['Item']['last_seen'])
                if datetime.utcnow() - last_seen < self.dedup_window:
                    # 중복: 카운트만 증가
                    self._increment_count(signature)
                    continue

            # 신규 또는 만료된 이상 현상
            unique.append(anomaly)
            self._record_anomaly(anomaly, signature)

        return unique

    def _record_anomaly(self, anomaly: dict, signature: str):
        """이상 현상 기록"""
        self.table.put_item(Item={
            'signature': signature,
            'last_seen': datetime.utcnow().isoformat(),
            'anomaly_type': anomaly.get('type', ''),
            'count': 1,
            'ttl': int((datetime.utcnow() + timedelta(days=7)).timestamp())
        })

    def _increment_count(self, signature: str):
        """발생 횟수 증가"""
        self.table.update_item(
            Key={'signature': signature},
            UpdateExpression='SET #count = #count + :inc, last_seen = :now',
            ExpressionAttributeNames={'#count': 'count'},
            ExpressionAttributeValues={
                ':inc': 1,
                ':now': datetime.utcnow().isoformat()
            }
        )
```

### 효과

```
Before (중복 분석):
- 1시간 동안 동일 에러 100회 발생
- 100회 × LLM 분석 = 높은 비용

After (Deduplication):
- 첫 발생만 LLM 분석
- 나머지 99회는 DynamoDB 조회만
- 절감: 99%
```

---

## 5. Pre-aggregated Metrics

반복적인 CloudWatch 쿼리를 사전 집계로 대체합니다.

### 구현

```python
# src/services/metric_aggregator.py

import boto3
from datetime import datetime, timedelta

class MetricAggregator:
    """메트릭 사전 집계 서비스"""

    def __init__(self):
        self.cloudwatch = boto3.client('cloudwatch')
        self.dynamodb = boto3.resource('dynamodb')
        self.cache_table = self.dynamodb.Table('bdp-metric-cache')

    async def get_aggregated_metrics(self, time_range: tuple) -> dict:
        """사전 집계된 메트릭 조회"""

        cache_key = self._generate_cache_key(time_range)

        # 캐시 확인
        cached = self.cache_table.get_item(Key={'cache_key': cache_key})
        if 'Item' in cached:
            return cached['Item']['metrics']

        # 캐시 미스: CloudWatch에서 조회
        metrics = await self._fetch_metrics(time_range)

        # 캐시 저장 (5분 TTL)
        self.cache_table.put_item(Item={
            'cache_key': cache_key,
            'metrics': metrics,
            'ttl': int((datetime.utcnow() + timedelta(minutes=5)).timestamp())
        })

        return metrics

    async def _fetch_metrics(self, time_range: tuple) -> dict:
        """CloudWatch에서 메트릭 조회"""
        start_time, end_time = time_range

        response = self.cloudwatch.get_metric_data(
            MetricDataQueries=[
                {
                    'Id': 'error_rate',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': 'AWS/Lambda',
                            'MetricName': 'Errors',
                            'Dimensions': [
                                {'Name': 'FunctionName', 'Value': 'api-handler'}
                            ]
                        },
                        'Period': 300,  # 5분
                        'Stat': 'Sum'
                    }
                },
                {
                    'Id': 'latency_p99',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': 'AWS/Lambda',
                            'MetricName': 'Duration',
                            'Dimensions': [
                                {'Name': 'FunctionName', 'Value': 'api-handler'}
                            ]
                        },
                        'Period': 300,
                        'Stat': 'p99'
                    }
                }
            ],
            StartTime=start_time,
            EndTime=end_time
        )

        return self._parse_metric_response(response)
```

---

## 6. Cost Monitoring

### CloudWatch 비용 알람

```python
# infra/cdk/cost_alarms.py

from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_sns as sns

class CostAlarms:
    """비용 알람 설정"""

    def __init__(self, scope, id):
        # SNS 토픽
        self.alarm_topic = sns.Topic(scope, "CostAlarmTopic")

        # LLM 호출 횟수 알람 (Custom Metric)
        cloudwatch.Alarm(
            scope, "LLMCallAlarm",
            metric=cloudwatch.Metric(
                namespace="BDP/LLM",
                metric_name="InvocationCount",
                statistic="Sum",
                period=Duration.hours(1)
            ),
            threshold=1000,  # 시간당 1000회
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
        ).add_alarm_action(cloudwatch_actions.SnsAction(self.alarm_topic))

        # Lambda 비용 알람
        cloudwatch.Alarm(
            scope, "LambdaCostAlarm",
            metric=cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="Invocations",
                statistic="Sum",
                period=Duration.hours(1)
            ),
            threshold=10000,  # 시간당 1만 호출
            evaluation_periods=1
        ).add_alarm_action(cloudwatch_actions.SnsAction(self.alarm_topic))
```

### 비용 대시보드

```python
# CloudWatch Dashboard 위젯

widgets = [
    {
        "type": "metric",
        "properties": {
            "title": "LLM Usage (Custom Metrics)",
            "metrics": [
                ["BDP/LLM", "InvocationCount", {"stat": "Sum"}],
                ["BDP/LLM", "InputTokenCount", {"stat": "Sum"}],
                ["BDP/LLM", "OutputTokenCount", {"stat": "Sum"}],
                ["BDP/LLM", "Latency", {"stat": "p99"}]
            ]
        }
    },
    {
        "type": "metric",
        "properties": {
            "title": "Lambda Costs",
            "metrics": [
                ["AWS/Lambda", "Duration", "FunctionName", "bdp-detection"],
                ["AWS/Lambda", "Duration", "FunctionName", "bdp-analysis"]
            ]
        }
    }
]
```

---

## 7. Cost Estimation

### 월간 비용 예측 (1M 로그 이벤트 기준, LLM 비용 제외)

| 서비스 | 사용량 | 단가 | 월 비용 |
|--------|--------|------|---------|
| Lambda (Detection) | 8,640 호출 × 500ms | $0.20/1M ms | $0.86 |
| Lambda (Analysis) | 1,000 호출 × 2s | $0.20/1M ms | $0.40 |
| DynamoDB | 1GB 저장, 100K R/W | On-demand | $1.50 |
| CloudWatch Logs | 10GB 수집 | $0.50/GB | $5.00 |
| Step Functions | 10K 전환 | $0.025/1K | $0.25 |
| **합계 (AWS)** | | | **~$8/월** |

### LLM 비용 (별도)

| Provider | 사용량 | 월 비용 |
|----------|--------|---------|
| **vLLM (On-Prem)** | 고정 인프라 | GPU 서버 운영 비용 |
| **Gemini 2.5 Pro** | 500K input + 100K output | ~$1.13 |
| **Gemini 2.5 Flash** | 500K input + 100K output | ~$0.14 |

### 최적화 전/후 비교

| 항목 | 최적화 전 | 최적화 후 | 절감액 |
|------|----------|----------|--------|
| CloudWatch 쿼리 | $50 | $17 | $33 (67%) |
| LLM 토큰 (Gemini Pro 기준) | $15 | $1.5 | $13.5 (90%) |
| Lambda 실행 | $10 | $6.5 | $3.5 (35%) |
| **합계** | **$75** | **$25** | **$50 (67%)** |
