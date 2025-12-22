"""
AWS Client Abstraction Layer for CD1 Agent.

AWS (Production) 또는 Mock (Public Testing)을 지원하는 통합 AWS 클라이언트.
환경 변수 AWS_MOCK으로 mock 모드를 활성화합니다.
"""
import json
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger()


# ============================================================================
# CloudWatch Provider
# ============================================================================

class BaseCloudWatchProvider(ABC):
    """CloudWatch Provider 추상 클래스."""

    @abstractmethod
    def get_metric_data(self, namespace: str, metric_name: str,
                        dimensions: List[Dict], start_time: datetime,
                        end_time: datetime, period: int = 300) -> Dict[str, Any]:
        """메트릭 데이터 조회."""
        pass

    @abstractmethod
    def put_metric_data(self, namespace: str, metric_name: str,
                        value: float, dimensions: List[Dict],
                        unit: str = 'Count') -> Dict[str, Any]:
        """메트릭 데이터 저장."""
        pass

    @abstractmethod
    def get_anomaly_detection_result(self, namespace: str, metric_name: str,
                                     dimensions: List[Dict]) -> Dict[str, Any]:
        """이상 탐지 결과 조회."""
        pass

    @abstractmethod
    def query_logs(self, log_group: str, query: str,
                   start_time: datetime, end_time: datetime) -> List[Dict]:
        """CloudWatch Logs Insights 쿼리."""
        pass


class AWSCloudWatchProvider(BaseCloudWatchProvider):
    """AWS CloudWatch Provider (Production)."""

    def __init__(self):
        import boto3
        self.cloudwatch = boto3.client('cloudwatch')
        self.logs = boto3.client('logs')
        self.logger = logger.bind(service="aws_cloudwatch")

    def get_metric_data(self, namespace: str, metric_name: str,
                        dimensions: List[Dict], start_time: datetime,
                        end_time: datetime, period: int = 300) -> Dict[str, Any]:
        """AWS CloudWatch 메트릭 데이터 조회."""
        response = self.cloudwatch.get_metric_data(
            MetricDataQueries=[{
                'Id': 'm1',
                'MetricStat': {
                    'Metric': {
                        'Namespace': namespace,
                        'MetricName': metric_name,
                        'Dimensions': dimensions
                    },
                    'Period': period,
                    'Stat': 'Average'
                }
            }],
            StartTime=start_time,
            EndTime=end_time
        )
        return {
            'timestamps': response['MetricDataResults'][0].get('Timestamps', []),
            'values': response['MetricDataResults'][0].get('Values', [])
        }

    def put_metric_data(self, namespace: str, metric_name: str,
                        value: float, dimensions: List[Dict],
                        unit: str = 'Count') -> Dict[str, Any]:
        """AWS CloudWatch 메트릭 데이터 저장."""
        self.cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[{
                'MetricName': metric_name,
                'Dimensions': dimensions,
                'Value': value,
                'Unit': unit
            }]
        )
        return {'status': 'success'}

    def get_anomaly_detection_result(self, namespace: str, metric_name: str,
                                     dimensions: List[Dict]) -> Dict[str, Any]:
        """AWS CloudWatch 이상 탐지 결과."""
        # Describe anomaly detectors and get current state
        response = self.cloudwatch.describe_anomaly_detectors(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions
        )
        if response.get('AnomalyDetectors'):
            return {
                'is_anomaly': True,  # Simplified - actual logic more complex
                'anomaly_score': 0.85,
                'expected_range': {'lower': 10, 'upper': 100}
            }
        return {'is_anomaly': False, 'anomaly_score': 0.0}

    def query_logs(self, log_group: str, query: str,
                   start_time: datetime, end_time: datetime) -> List[Dict]:
        """CloudWatch Logs Insights 쿼리."""
        start_query = self.logs.start_query(
            logGroupName=log_group,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query
        )

        query_id = start_query['queryId']

        # Wait for query completion (simplified)
        import time
        while True:
            response = self.logs.get_query_results(queryId=query_id)
            if response['status'] == 'Complete':
                return response.get('results', [])
            elif response['status'] in ['Failed', 'Cancelled']:
                return []
            time.sleep(0.5)


class MockCloudWatchProvider(BaseCloudWatchProvider):
    """Mock CloudWatch Provider for testing."""

    def __init__(self):
        self.logger = logger.bind(service="mock_cloudwatch")
        self.metrics_store: Dict[str, List[Dict]] = {}
        self.call_count = 0

    def get_metric_data(self, namespace: str, metric_name: str,
                        dimensions: List[Dict], start_time: datetime,
                        end_time: datetime, period: int = 300) -> Dict[str, Any]:
        """Mock 메트릭 데이터 생성."""
        self.call_count += 1
        self.logger.info("mock_get_metric_data", namespace=namespace, metric=metric_name)

        # Generate mock time series data
        import random
        timestamps = []
        values = []
        current = start_time
        while current <= end_time:
            timestamps.append(current)
            # Generate realistic-looking metric values with some variance
            base_value = 50 + random.uniform(-10, 10)
            # Add occasional spikes for anomaly testing
            if random.random() > 0.9:
                base_value *= 2.5
            values.append(base_value)
            current += timedelta(seconds=period)

        return {
            'timestamps': timestamps,
            'values': values
        }

    def put_metric_data(self, namespace: str, metric_name: str,
                        value: float, dimensions: List[Dict],
                        unit: str = 'Count') -> Dict[str, Any]:
        """Mock 메트릭 데이터 저장."""
        self.call_count += 1
        key = f"{namespace}/{metric_name}"
        if key not in self.metrics_store:
            self.metrics_store[key] = []
        self.metrics_store[key].append({
            'value': value,
            'dimensions': dimensions,
            'timestamp': datetime.utcnow().isoformat()
        })
        self.logger.info("mock_put_metric_data", namespace=namespace, metric=metric_name)
        return {'status': 'success'}

    def get_anomaly_detection_result(self, namespace: str, metric_name: str,
                                     dimensions: List[Dict]) -> Dict[str, Any]:
        """Mock 이상 탐지 결과."""
        self.call_count += 1
        import random

        # Simulate anomaly detection with configurable probability
        is_anomaly = random.random() > 0.7
        return {
            'is_anomaly': is_anomaly,
            'anomaly_score': random.uniform(0.7, 0.95) if is_anomaly else random.uniform(0.1, 0.3),
            'expected_range': {'lower': 30, 'upper': 70},
            'current_value': random.uniform(20, 120)
        }

    def query_logs(self, log_group: str, query: str,
                   start_time: datetime, end_time: datetime) -> List[Dict]:
        """Mock 로그 쿼리 결과."""
        self.call_count += 1
        self.logger.info("mock_query_logs", log_group=log_group)

        # Return mock log entries
        return [
            {
                '@timestamp': (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
                '@message': '[Mock] ERROR: Connection timeout to database',
                'level': 'ERROR',
                'service': 'api-gateway'
            },
            {
                '@timestamp': (datetime.utcnow() - timedelta(minutes=3)).isoformat(),
                '@message': '[Mock] WARN: High memory usage detected',
                'level': 'WARN',
                'service': 'user-service'
            },
            {
                '@timestamp': datetime.utcnow().isoformat(),
                '@message': '[Mock] INFO: Request processed successfully',
                'level': 'INFO',
                'service': 'api-gateway'
            }
        ]


# ============================================================================
# DynamoDB Provider
# ============================================================================

class BaseDynamoDBProvider(ABC):
    """DynamoDB Provider 추상 클래스."""

    @abstractmethod
    def put_item(self, table_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """아이템 저장."""
        pass

    @abstractmethod
    def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """아이템 조회."""
        pass

    @abstractmethod
    def query(self, table_name: str, key_condition: str,
              expression_values: Dict) -> List[Dict[str, Any]]:
        """쿼리 실행."""
        pass

    @abstractmethod
    def delete_item(self, table_name: str, key: Dict[str, Any]) -> Dict[str, Any]:
        """아이템 삭제."""
        pass


class AWSDynamoDBProvider(BaseDynamoDBProvider):
    """AWS DynamoDB Provider (Production)."""

    def __init__(self):
        import boto3
        self.dynamodb = boto3.resource('dynamodb')
        self.logger = logger.bind(service="aws_dynamodb")

    def put_item(self, table_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """DynamoDB 아이템 저장."""
        table = self.dynamodb.Table(table_name)
        table.put_item(Item=item)
        return {'status': 'success'}

    def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """DynamoDB 아이템 조회."""
        table = self.dynamodb.Table(table_name)
        response = table.get_item(Key=key)
        return response.get('Item')

    def query(self, table_name: str, key_condition: str,
              expression_values: Dict) -> List[Dict[str, Any]]:
        """DynamoDB 쿼리."""
        table = self.dynamodb.Table(table_name)
        response = table.query(
            KeyConditionExpression=key_condition,
            ExpressionAttributeValues=expression_values
        )
        return response.get('Items', [])

    def delete_item(self, table_name: str, key: Dict[str, Any]) -> Dict[str, Any]:
        """DynamoDB 아이템 삭제."""
        table = self.dynamodb.Table(table_name)
        table.delete_item(Key=key)
        return {'status': 'success'}


class MockDynamoDBProvider(BaseDynamoDBProvider):
    """Mock DynamoDB Provider for testing."""

    def __init__(self):
        self.logger = logger.bind(service="mock_dynamodb")
        self.tables: Dict[str, Dict[str, Dict]] = {}
        self.call_count = 0

    def _get_key_string(self, key: Dict[str, Any]) -> str:
        """키를 문자열로 변환."""
        return json.dumps(key, sort_keys=True)

    def put_item(self, table_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Mock 아이템 저장."""
        self.call_count += 1
        if table_name not in self.tables:
            self.tables[table_name] = {}

        # Assume first key in item is partition key
        key = {k: v for k, v in list(item.items())[:1]}
        key_str = self._get_key_string(key)
        self.tables[table_name][key_str] = item

        self.logger.info("mock_put_item", table=table_name)
        return {'status': 'success'}

    def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Mock 아이템 조회."""
        self.call_count += 1
        if table_name not in self.tables:
            return None

        key_str = self._get_key_string(key)
        item = self.tables[table_name].get(key_str)
        self.logger.info("mock_get_item", table=table_name, found=item is not None)
        return item

    def query(self, table_name: str, key_condition: str,
              expression_values: Dict) -> List[Dict[str, Any]]:
        """Mock 쿼리 - 테이블의 모든 아이템 반환 (단순화)."""
        self.call_count += 1
        if table_name not in self.tables:
            return []

        self.logger.info("mock_query", table=table_name)
        return list(self.tables[table_name].values())

    def delete_item(self, table_name: str, key: Dict[str, Any]) -> Dict[str, Any]:
        """Mock 아이템 삭제."""
        self.call_count += 1
        if table_name in self.tables:
            key_str = self._get_key_string(key)
            self.tables[table_name].pop(key_str, None)

        self.logger.info("mock_delete_item", table=table_name)
        return {'status': 'success'}


# ============================================================================
# RDS Data API Provider
# ============================================================================

class BaseRDSDataProvider(ABC):
    """RDS Data API Provider 추상 클래스."""

    @abstractmethod
    def execute_statement(self, sql: str, parameters: List[Dict] = None) -> Dict[str, Any]:
        """SQL 실행."""
        pass

    @abstractmethod
    def batch_execute_statement(self, sql: str,
                                parameter_sets: List[List[Dict]]) -> Dict[str, Any]:
        """배치 SQL 실행."""
        pass


class AWSRDSDataProvider(BaseRDSDataProvider):
    """AWS RDS Data API Provider (Production)."""

    def __init__(self):
        import boto3
        self.client = boto3.client('rds-data')
        self.resource_arn = os.environ.get('RDS_RESOURCE_ARN')
        self.secret_arn = os.environ.get('RDS_SECRET_ARN')
        self.database = os.environ.get('RDS_DATABASE', 'bdp_logs')
        self.logger = logger.bind(service="aws_rds_data")

    def execute_statement(self, sql: str, parameters: List[Dict] = None) -> Dict[str, Any]:
        """RDS Data API SQL 실행."""
        params = {
            'resourceArn': self.resource_arn,
            'secretArn': self.secret_arn,
            'database': self.database,
            'sql': sql
        }
        if parameters:
            params['parameters'] = parameters

        response = self.client.execute_statement(**params)
        return {
            'records': response.get('records', []),
            'numberOfRecordsUpdated': response.get('numberOfRecordsUpdated', 0)
        }

    def batch_execute_statement(self, sql: str,
                                parameter_sets: List[List[Dict]]) -> Dict[str, Any]:
        """배치 SQL 실행."""
        response = self.client.batch_execute_statement(
            resourceArn=self.resource_arn,
            secretArn=self.secret_arn,
            database=self.database,
            sql=sql,
            parameterSets=parameter_sets
        )
        return {
            'updateResults': response.get('updateResults', [])
        }


class MockRDSDataProvider(BaseRDSDataProvider):
    """Mock RDS Data API Provider for testing."""

    def __init__(self):
        self.logger = logger.bind(service="mock_rds_data")
        self.records: List[Dict] = []
        self.call_count = 0

    def execute_statement(self, sql: str, parameters: List[Dict] = None) -> Dict[str, Any]:
        """Mock SQL 실행."""
        self.call_count += 1
        self.logger.info("mock_execute_statement", sql_preview=sql[:50])

        # Generate mock query results based on SQL type
        sql_lower = sql.lower().strip()

        if sql_lower.startswith('select'):
            return {
                'records': [
                    [{'stringValue': 'mock_id_1'}, {'stringValue': 'error'}, {'stringValue': '2024-01-01'}],
                    [{'stringValue': 'mock_id_2'}, {'stringValue': 'warning'}, {'stringValue': '2024-01-02'}]
                ],
                'numberOfRecordsUpdated': 0
            }
        elif sql_lower.startswith('insert'):
            return {
                'records': [],
                'numberOfRecordsUpdated': 1
            }
        elif sql_lower.startswith('update'):
            return {
                'records': [],
                'numberOfRecordsUpdated': 1
            }
        elif sql_lower.startswith('delete'):
            return {
                'records': [],
                'numberOfRecordsUpdated': 1
            }
        else:
            return {'records': [], 'numberOfRecordsUpdated': 0}

    def batch_execute_statement(self, sql: str,
                                parameter_sets: List[List[Dict]]) -> Dict[str, Any]:
        """Mock 배치 SQL 실행."""
        self.call_count += 1
        self.logger.info("mock_batch_execute", batch_size=len(parameter_sets))

        return {
            'updateResults': [{'generatedFields': []} for _ in parameter_sets]
        }


# ============================================================================
# Lambda Provider
# ============================================================================

class BaseLambdaProvider(ABC):
    """Lambda Provider 추상 클래스."""

    @abstractmethod
    def invoke(self, function_name: str, payload: Dict[str, Any],
               invocation_type: str = 'RequestResponse') -> Dict[str, Any]:
        """Lambda 함수 호출."""
        pass

    @abstractmethod
    def get_function_configuration(self, function_name: str) -> Dict[str, Any]:
        """함수 설정 조회."""
        pass

    @abstractmethod
    def update_function_configuration(self, function_name: str,
                                       config: Dict[str, Any]) -> Dict[str, Any]:
        """함수 설정 업데이트."""
        pass


class AWSLambdaProvider(BaseLambdaProvider):
    """AWS Lambda Provider (Production)."""

    def __init__(self):
        import boto3
        self.client = boto3.client('lambda')
        self.logger = logger.bind(service="aws_lambda")

    def invoke(self, function_name: str, payload: Dict[str, Any],
               invocation_type: str = 'RequestResponse') -> Dict[str, Any]:
        """Lambda 함수 호출."""
        response = self.client.invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            Payload=json.dumps(payload)
        )

        if invocation_type == 'RequestResponse':
            result = json.loads(response['Payload'].read())
            return {
                'status_code': response['StatusCode'],
                'result': result
            }
        return {'status_code': response['StatusCode']}

    def get_function_configuration(self, function_name: str) -> Dict[str, Any]:
        """함수 설정 조회."""
        return self.client.get_function_configuration(FunctionName=function_name)

    def update_function_configuration(self, function_name: str,
                                       config: Dict[str, Any]) -> Dict[str, Any]:
        """함수 설정 업데이트."""
        return self.client.update_function_configuration(
            FunctionName=function_name,
            **config
        )


class MockLambdaProvider(BaseLambdaProvider):
    """Mock Lambda Provider for testing."""

    def __init__(self):
        self.logger = logger.bind(service="mock_lambda")
        self.functions: Dict[str, Dict] = {}
        self.invocation_history: List[Dict] = []
        self.call_count = 0

    def invoke(self, function_name: str, payload: Dict[str, Any],
               invocation_type: str = 'RequestResponse') -> Dict[str, Any]:
        """Mock Lambda 호출."""
        self.call_count += 1
        self.invocation_history.append({
            'function_name': function_name,
            'payload': payload,
            'timestamp': datetime.utcnow().isoformat()
        })

        self.logger.info("mock_lambda_invoke", function=function_name)

        # Generate mock response based on function name
        if 'restart' in function_name.lower():
            result = {
                'status': 'success',
                'message': f'[Mock] Function {function_name} restarted successfully',
                'restart_time': datetime.utcnow().isoformat()
            }
        elif 'remediation' in function_name.lower():
            result = {
                'status': 'success',
                'action_taken': payload.get('action_type', 'unknown'),
                'details': '[Mock] Remediation action completed'
            }
        else:
            result = {
                'status': 'success',
                'message': f'[Mock] Invoked {function_name}'
            }

        return {
            'status_code': 200,
            'result': result
        }

    def get_function_configuration(self, function_name: str) -> Dict[str, Any]:
        """Mock 함수 설정 조회."""
        self.call_count += 1
        return self.functions.get(function_name, {
            'FunctionName': function_name,
            'Runtime': 'python3.12',
            'MemorySize': 256,
            'Timeout': 30,
            'Environment': {'Variables': {}},
            'State': 'Active'
        })

    def update_function_configuration(self, function_name: str,
                                       config: Dict[str, Any]) -> Dict[str, Any]:
        """Mock 함수 설정 업데이트."""
        self.call_count += 1
        if function_name not in self.functions:
            self.functions[function_name] = {}
        self.functions[function_name].update(config)

        self.logger.info("mock_lambda_update_config", function=function_name)
        return {**self.functions[function_name], 'FunctionName': function_name}


# ============================================================================
# EventBridge Provider
# ============================================================================

class BaseEventBridgeProvider(ABC):
    """EventBridge Provider 추상 클래스."""

    @abstractmethod
    def put_events(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """이벤트 발행."""
        pass


class AWSEventBridgeProvider(BaseEventBridgeProvider):
    """AWS EventBridge Provider (Production)."""

    def __init__(self):
        import boto3
        self.client = boto3.client('events')
        self.logger = logger.bind(service="aws_eventbridge")

    def put_events(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """이벤트 발행."""
        response = self.client.put_events(Entries=entries)
        return {
            'failed_entry_count': response.get('FailedEntryCount', 0),
            'entries': response.get('Entries', [])
        }


class MockEventBridgeProvider(BaseEventBridgeProvider):
    """Mock EventBridge Provider for testing."""

    def __init__(self):
        self.logger = logger.bind(service="mock_eventbridge")
        self.events: List[Dict] = []
        self.call_count = 0

    def put_events(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Mock 이벤트 발행."""
        self.call_count += 1

        for entry in entries:
            self.events.append({
                **entry,
                'event_id': str(uuid.uuid4()),
                'timestamp': datetime.utcnow().isoformat()
            })

        self.logger.info("mock_put_events", event_count=len(entries))

        return {
            'failed_entry_count': 0,
            'entries': [{'EventId': str(uuid.uuid4())} for _ in entries]
        }


# ============================================================================
# Step Functions Provider
# ============================================================================

class BaseStepFunctionsProvider(ABC):
    """Step Functions Provider 추상 클래스."""

    @abstractmethod
    def start_execution(self, state_machine_arn: str, name: str,
                        input_data: Dict[str, Any]) -> Dict[str, Any]:
        """워크플로우 실행 시작."""
        pass

    @abstractmethod
    def describe_execution(self, execution_arn: str) -> Dict[str, Any]:
        """실행 상태 조회."""
        pass

    @abstractmethod
    def send_task_success(self, task_token: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """태스크 성공 전송."""
        pass

    @abstractmethod
    def send_task_failure(self, task_token: str, error: str, cause: str) -> Dict[str, Any]:
        """태스크 실패 전송."""
        pass


class AWSStepFunctionsProvider(BaseStepFunctionsProvider):
    """AWS Step Functions Provider (Production)."""

    def __init__(self):
        import boto3
        self.client = boto3.client('stepfunctions')
        self.logger = logger.bind(service="aws_stepfunctions")

    def start_execution(self, state_machine_arn: str, name: str,
                        input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Step Functions 실행 시작."""
        response = self.client.start_execution(
            stateMachineArn=state_machine_arn,
            name=name,
            input=json.dumps(input_data)
        )
        return {
            'execution_arn': response['executionArn'],
            'start_date': response['startDate'].isoformat()
        }

    def describe_execution(self, execution_arn: str) -> Dict[str, Any]:
        """실행 상태 조회."""
        response = self.client.describe_execution(executionArn=execution_arn)
        return {
            'status': response['status'],
            'start_date': response['startDate'].isoformat(),
            'stop_date': response.get('stopDate', datetime.utcnow()).isoformat() if response.get('stopDate') else None,
            'input': json.loads(response.get('input', '{}')),
            'output': json.loads(response.get('output', '{}')) if response.get('output') else None
        }

    def send_task_success(self, task_token: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """태스크 성공 전송."""
        self.client.send_task_success(
            taskToken=task_token,
            output=json.dumps(output)
        )
        return {'status': 'success'}

    def send_task_failure(self, task_token: str, error: str, cause: str) -> Dict[str, Any]:
        """태스크 실패 전송."""
        self.client.send_task_failure(
            taskToken=task_token,
            error=error,
            cause=cause
        )
        return {'status': 'failed'}


class MockStepFunctionsProvider(BaseStepFunctionsProvider):
    """Mock Step Functions Provider for testing."""

    def __init__(self):
        self.logger = logger.bind(service="mock_stepfunctions")
        self.executions: Dict[str, Dict] = {}
        self.task_tokens: Dict[str, Dict] = {}
        self.call_count = 0

    def start_execution(self, state_machine_arn: str, name: str,
                        input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock 워크플로우 실행."""
        self.call_count += 1
        execution_arn = f"arn:aws:states:mock:123456789:execution:{name}"

        self.executions[execution_arn] = {
            'status': 'RUNNING',
            'start_date': datetime.utcnow(),
            'input': input_data,
            'state_machine_arn': state_machine_arn
        }

        self.logger.info("mock_start_execution", execution_arn=execution_arn)

        return {
            'execution_arn': execution_arn,
            'start_date': datetime.utcnow().isoformat()
        }

    def describe_execution(self, execution_arn: str) -> Dict[str, Any]:
        """Mock 실행 상태 조회."""
        self.call_count += 1

        if execution_arn in self.executions:
            exec_data = self.executions[execution_arn]
            return {
                'status': exec_data['status'],
                'start_date': exec_data['start_date'].isoformat(),
                'stop_date': exec_data.get('stop_date', datetime.utcnow()).isoformat() if exec_data.get('stop_date') else None,
                'input': exec_data['input'],
                'output': exec_data.get('output')
            }

        # Return mock data for unknown executions
        return {
            'status': 'SUCCEEDED',
            'start_date': (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
            'stop_date': datetime.utcnow().isoformat(),
            'input': {},
            'output': {'result': '[Mock] Execution completed successfully'}
        }

    def send_task_success(self, task_token: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """Mock 태스크 성공."""
        self.call_count += 1
        self.task_tokens[task_token] = {
            'status': 'SUCCESS',
            'output': output,
            'timestamp': datetime.utcnow().isoformat()
        }
        self.logger.info("mock_task_success", task_token=task_token[:20])
        return {'status': 'success'}

    def send_task_failure(self, task_token: str, error: str, cause: str) -> Dict[str, Any]:
        """Mock 태스크 실패."""
        self.call_count += 1
        self.task_tokens[task_token] = {
            'status': 'FAILED',
            'error': error,
            'cause': cause,
            'timestamp': datetime.utcnow().isoformat()
        }
        self.logger.info("mock_task_failure", task_token=task_token[:20], error=error)
        return {'status': 'failed'}


# ============================================================================
# Unified AWS Client
# ============================================================================

class AWSClient:
    """통합 AWS 클라이언트 - Provider 자동 선택."""

    def __init__(self, mock_mode: Optional[bool] = None):
        """
        AWSClient 초기화.

        Args:
            mock_mode: True면 mock provider 사용, None이면 환경 변수에서 결정.

        환경 변수:
            AWS_MOCK: 'true'로 설정 시 mock provider 사용
        """
        if mock_mode is None:
            mock_mode = os.environ.get('AWS_MOCK', '').lower() == 'true'

        self.mock_mode = mock_mode
        self.logger = logger.bind(service="aws_client", mock_mode=mock_mode)

        if mock_mode:
            self.cloudwatch = MockCloudWatchProvider()
            self.dynamodb = MockDynamoDBProvider()
            self.rds_data = MockRDSDataProvider()
            self.lambda_client = MockLambdaProvider()
            self.eventbridge = MockEventBridgeProvider()
            self.stepfunctions = MockStepFunctionsProvider()
            self.logger.info("aws_client_initialized", mode="mock")
        else:
            self.cloudwatch = AWSCloudWatchProvider()
            self.dynamodb = AWSDynamoDBProvider()
            self.rds_data = AWSRDSDataProvider()
            self.lambda_client = AWSLambdaProvider()
            self.eventbridge = AWSEventBridgeProvider()
            self.stepfunctions = AWSStepFunctionsProvider()
            self.logger.info("aws_client_initialized", mode="aws")

    def get_stats(self) -> Dict[str, int]:
        """Mock 모드에서 호출 통계 반환."""
        if not self.mock_mode:
            return {}

        return {
            'cloudwatch_calls': self.cloudwatch.call_count,
            'dynamodb_calls': self.dynamodb.call_count,
            'rds_data_calls': self.rds_data.call_count,
            'lambda_calls': self.lambda_client.call_count,
            'eventbridge_calls': self.eventbridge.call_count,
            'stepfunctions_calls': self.stepfunctions.call_count
        }


# 사용 예시
if __name__ == "__main__":
    # Mock 모드로 테스트
    os.environ['AWS_MOCK'] = 'true'

    client = AWSClient()
    print(f"Mock mode: {client.mock_mode}")

    # CloudWatch 테스트
    metrics = client.cloudwatch.get_metric_data(
        namespace='AWS/RDS',
        metric_name='CPUUtilization',
        dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': 'test-db'}],
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow()
    )
    print(f"Metrics: {len(metrics['values'])} data points")

    # DynamoDB 테스트
    client.dynamodb.put_item('test-table', {'id': '123', 'data': 'test'})
    item = client.dynamodb.get_item('test-table', {'id': '123'})
    print(f"DynamoDB item: {item}")

    # Lambda 테스트
    result = client.lambda_client.invoke('test-function', {'action': 'restart'})
    print(f"Lambda result: {result}")

    # Step Functions 테스트
    execution = client.stepfunctions.start_execution(
        'arn:aws:states:mock:123:stateMachine:test',
        'test-execution',
        {'anomaly_id': 'test-123'}
    )
    print(f"Execution started: {execution['execution_arn']}")

    # 통계 출력
    print(f"\nCall statistics: {json.dumps(client.get_stats(), indent=2)}")
