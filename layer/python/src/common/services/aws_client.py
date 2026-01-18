"""
AWS Client with Provider Abstraction.

Supports real AWS services and mock providers for testing.
"""

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


class AWSProvider(str, Enum):
    """Supported AWS provider modes."""

    REAL = "real"
    MOCK = "mock"


class BaseAWSProvider(ABC):
    """Abstract base class for AWS providers."""

    @abstractmethod
    def get_cloudwatch_metrics(
        self,
        namespace: str,
        metric_name: str,
        dimensions: List[Dict[str, str]],
        start_time: datetime,
        end_time: datetime,
        period: int = 300,
        statistic: str = "Average",
    ) -> Dict[str, Any]:
        """Get CloudWatch metrics."""
        pass

    @abstractmethod
    def query_cloudwatch_logs(
        self,
        log_group: str,
        query: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Query CloudWatch Logs Insights."""
        pass

    @abstractmethod
    def put_dynamodb_item(
        self, table_name: str, item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Put item to DynamoDB."""
        pass

    @abstractmethod
    def get_dynamodb_item(
        self, table_name: str, key: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get item from DynamoDB."""
        pass

    @abstractmethod
    def query_dynamodb(
        self,
        table_name: str,
        key_condition: str,
        expression_values: Dict[str, Any],
        index_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query DynamoDB table."""
        pass

    @abstractmethod
    def invoke_lambda(
        self, function_name: str, payload: Dict[str, Any], invocation_type: str = "RequestResponse"
    ) -> Dict[str, Any]:
        """Invoke Lambda function."""
        pass

    @abstractmethod
    def put_eventbridge_event(
        self,
        event_bus: str,
        source: str,
        detail_type: str,
        detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Put event to EventBridge."""
        pass

    @abstractmethod
    def retrieve_knowledge_base(
        self,
        knowledge_base_id: str,
        query: str,
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve from Knowledge Base."""
        pass


class RealAWSProvider(BaseAWSProvider):
    """Real AWS provider using boto3."""

    def __init__(self, region: Optional[str] = None):
        import boto3

        self.region = region or os.getenv("AWS_REGION", "ap-northeast-2")
        self.session = boto3.Session(region_name=self.region)
        self._clients: Dict[str, Any] = {}

    def _get_client(self, service: str) -> Any:
        """Get or create boto3 client."""
        if service not in self._clients:
            self._clients[service] = self.session.client(service)
        return self._clients[service]

    def get_cloudwatch_metrics(
        self,
        namespace: str,
        metric_name: str,
        dimensions: List[Dict[str, str]],
        start_time: datetime,
        end_time: datetime,
        period: int = 300,
        statistic: str = "Average",
    ) -> Dict[str, Any]:
        """Get CloudWatch metrics."""
        client = self._get_client("cloudwatch")
        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=[{"Name": k, "Value": v} for d in dimensions for k, v in d.items()],
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=[statistic],
        )
        return {
            "namespace": namespace,
            "metric": metric_name,
            "datapoints": response.get("Datapoints", []),
        }

    def query_cloudwatch_logs(
        self,
        log_group: str,
        query: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Query CloudWatch Logs Insights."""
        client = self._get_client("logs")

        response = client.start_query(
            logGroupName=log_group,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query,
            limit=limit,
        )
        query_id = response["queryId"]

        import time

        while True:
            result = client.get_query_results(queryId=query_id)
            if result["status"] in ["Complete", "Failed", "Cancelled"]:
                break
            time.sleep(0.5)

        return [
            {field["field"]: field["value"] for field in row}
            for row in result.get("results", [])
        ]

    def put_dynamodb_item(
        self, table_name: str, item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Put item to DynamoDB."""
        client = self._get_client("dynamodb")
        from boto3.dynamodb.types import TypeSerializer

        serializer = TypeSerializer()
        serialized = {k: serializer.serialize(v) for k, v in item.items()}
        response = client.put_item(TableName=table_name, Item=serialized)
        return {"status": "success", "response": response}

    def get_dynamodb_item(
        self, table_name: str, key: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get item from DynamoDB."""
        client = self._get_client("dynamodb")
        from boto3.dynamodb.types import TypeSerializer, TypeDeserializer

        serializer = TypeSerializer()
        deserializer = TypeDeserializer()
        serialized_key = {k: serializer.serialize(v) for k, v in key.items()}

        response = client.get_item(TableName=table_name, Key=serialized_key)
        if "Item" not in response:
            return None
        return {k: deserializer.deserialize(v) for k, v in response["Item"].items()}

    def query_dynamodb(
        self,
        table_name: str,
        key_condition: str,
        expression_values: Dict[str, Any],
        index_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query DynamoDB table."""
        client = self._get_client("dynamodb")
        from boto3.dynamodb.types import TypeSerializer, TypeDeserializer

        serializer = TypeSerializer()
        deserializer = TypeDeserializer()

        params: Dict[str, Any] = {
            "TableName": table_name,
            "KeyConditionExpression": key_condition,
            "ExpressionAttributeValues": {
                k: serializer.serialize(v) for k, v in expression_values.items()
            },
            "Limit": limit,
        }
        if index_name:
            params["IndexName"] = index_name

        response = client.query(**params)
        return [
            {k: deserializer.deserialize(v) for k, v in item.items()}
            for item in response.get("Items", [])
        ]

    def invoke_lambda(
        self, function_name: str, payload: Dict[str, Any], invocation_type: str = "RequestResponse"
    ) -> Dict[str, Any]:
        """Invoke Lambda function."""
        client = self._get_client("lambda")
        response = client.invoke(
            FunctionName=function_name,
            InvocationType=invocation_type,
            Payload=json.dumps(payload).encode(),
        )

        if invocation_type == "RequestResponse":
            result = json.loads(response["Payload"].read().decode())
            return {"status_code": response["StatusCode"], "result": result}
        return {"status_code": response["StatusCode"]}

    def put_eventbridge_event(
        self,
        event_bus: str,
        source: str,
        detail_type: str,
        detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Put event to EventBridge."""
        client = self._get_client("events")
        response = client.put_events(
            Entries=[
                {
                    "EventBusName": event_bus,
                    "Source": source,
                    "DetailType": detail_type,
                    "Detail": json.dumps(detail),
                }
            ]
        )
        return {
            "failed_count": response["FailedEntryCount"],
            "entries": response["Entries"],
        }

    def retrieve_knowledge_base(
        self,
        knowledge_base_id: str,
        query: str,
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve from Knowledge Base."""
        client = self._get_client("bedrock-agent-runtime")
        response = client.retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )
        return [
            {
                "content": result["content"]["text"],
                "score": result.get("score", 0.0),
                "metadata": result.get("metadata", {}),
            }
            for result in response.get("retrievalResults", [])
        ]


class MockAWSProvider(BaseAWSProvider):
    """Mock AWS provider for testing."""

    def __init__(self, mock_data: Optional[Dict[str, Any]] = None):
        self.mock_data = mock_data or {}
        self.call_history: List[Dict[str, Any]] = []
        self._dynamodb_store: Dict[str, Dict[str, Any]] = {}
        self._events: List[Dict[str, Any]] = []

    def _record_call(self, method: str, **kwargs: Any) -> None:
        """Record method call for verification."""
        self.call_history.append({"method": method, **kwargs})

    def get_cloudwatch_metrics(
        self,
        namespace: str,
        metric_name: str,
        dimensions: List[Dict[str, str]],
        start_time: datetime,
        end_time: datetime,
        period: int = 300,
        statistic: str = "Average",
    ) -> Dict[str, Any]:
        """Return mock CloudWatch metrics."""
        self._record_call(
            "get_cloudwatch_metrics",
            namespace=namespace,
            metric_name=metric_name,
            dimensions=dimensions,
        )

        if "cloudwatch_metrics" in self.mock_data:
            return self.mock_data["cloudwatch_metrics"]

        # Generate mock datapoints
        datapoints = []
        current = start_time
        while current < end_time:
            datapoints.append(
                {
                    "Timestamp": current.isoformat(),
                    statistic: 50.0 + (hash(current.isoformat()) % 50),
                    "Unit": "Percent",
                }
            )
            current += timedelta(seconds=period)

        return {
            "namespace": namespace,
            "metric": metric_name,
            "datapoints": datapoints,
        }

    def query_cloudwatch_logs(
        self,
        log_group: str,
        query: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Return mock CloudWatch Logs query results."""
        self._record_call(
            "query_cloudwatch_logs",
            log_group=log_group,
            query=query,
        )

        if "cloudwatch_logs" in self.mock_data:
            return self.mock_data["cloudwatch_logs"]

        return [
            {
                "@timestamp": datetime.utcnow().isoformat(),
                "@message": "Mock log message",
                "@logStream": "mock-stream",
            }
        ]

    def put_dynamodb_item(
        self, table_name: str, item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Store item in mock DynamoDB."""
        self._record_call("put_dynamodb_item", table_name=table_name, item=item)

        if table_name not in self._dynamodb_store:
            self._dynamodb_store[table_name] = {}

        # Use first key as primary key
        key = str(list(item.values())[0])
        self._dynamodb_store[table_name][key] = item

        return {"status": "success"}

    def get_dynamodb_item(
        self, table_name: str, key: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get item from mock DynamoDB."""
        self._record_call("get_dynamodb_item", table_name=table_name, key=key)

        if table_name not in self._dynamodb_store:
            return None

        key_value = str(list(key.values())[0])
        return self._dynamodb_store[table_name].get(key_value)

    def query_dynamodb(
        self,
        table_name: str,
        key_condition: str,
        expression_values: Dict[str, Any],
        index_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query mock DynamoDB."""
        self._record_call(
            "query_dynamodb",
            table_name=table_name,
            key_condition=key_condition,
        )

        if "dynamodb_query" in self.mock_data:
            return self.mock_data["dynamodb_query"]

        if table_name in self._dynamodb_store:
            return list(self._dynamodb_store[table_name].values())[:limit]

        return []

    def invoke_lambda(
        self, function_name: str, payload: Dict[str, Any], invocation_type: str = "RequestResponse"
    ) -> Dict[str, Any]:
        """Mock Lambda invocation."""
        self._record_call(
            "invoke_lambda",
            function_name=function_name,
            payload=payload,
        )

        if "lambda_response" in self.mock_data:
            return self.mock_data["lambda_response"]

        return {"status_code": 200, "result": {"status": "success"}}

    def put_eventbridge_event(
        self,
        event_bus: str,
        source: str,
        detail_type: str,
        detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Store event in mock EventBridge."""
        self._record_call(
            "put_eventbridge_event",
            event_bus=event_bus,
            source=source,
            detail_type=detail_type,
        )

        self._events.append(
            {
                "event_bus": event_bus,
                "source": source,
                "detail_type": detail_type,
                "detail": detail,
            }
        )

        return {"failed_count": 0, "entries": [{"EventId": "mock-event-id"}]}

    def retrieve_knowledge_base(
        self,
        knowledge_base_id: str,
        query: str,
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return mock Knowledge Base results."""
        self._record_call(
            "retrieve_knowledge_base",
            knowledge_base_id=knowledge_base_id,
            query=query,
        )

        if "knowledge_base" in self.mock_data:
            return self.mock_data["knowledge_base"]

        return [
            {
                "content": "Mock knowledge base content relevant to query",
                "score": 0.95,
                "metadata": {"source": "mock-document.pdf"},
            }
        ]

    def get_events(self) -> List[Dict[str, Any]]:
        """Get all recorded events."""
        return self._events


class AWSClient:
    """
    Unified AWS client with provider abstraction.

    Usage:
        # Real AWS
        client = AWSClient(provider=AWSProvider.REAL)

        # Mock for testing
        client = AWSClient(provider=AWSProvider.MOCK, mock_data={"cloudwatch_metrics": {...}})

        # Get metrics
        metrics = client.get_cloudwatch_metrics(namespace="AWS/Lambda", ...)

        # Query logs
        logs = client.query_cloudwatch_logs(log_group="/aws/lambda/my-function", ...)
    """

    def __init__(
        self,
        provider: AWSProvider = AWSProvider.MOCK,
        region: Optional[str] = None,
        mock_data: Optional[Dict[str, Any]] = None,
    ):
        self.provider_type = provider
        self._provider = self._create_provider(provider, region, mock_data)

    def _create_provider(
        self,
        provider: AWSProvider,
        region: Optional[str],
        mock_data: Optional[Dict[str, Any]],
    ) -> BaseAWSProvider:
        """Create the appropriate provider instance."""
        if provider == AWSProvider.REAL:
            return RealAWSProvider(region=region)
        return MockAWSProvider(mock_data=mock_data)

    def get_cloudwatch_metrics(
        self,
        namespace: str,
        metric_name: str,
        dimensions: List[Dict[str, str]],
        start_time: datetime,
        end_time: datetime,
        period: int = 300,
        statistic: str = "Average",
    ) -> Dict[str, Any]:
        """Get CloudWatch metrics."""
        return self._provider.get_cloudwatch_metrics(
            namespace, metric_name, dimensions, start_time, end_time, period, statistic
        )

    def query_cloudwatch_logs(
        self,
        log_group: str,
        query: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Query CloudWatch Logs Insights."""
        return self._provider.query_cloudwatch_logs(
            log_group, query, start_time, end_time, limit
        )

    def put_dynamodb_item(
        self, table_name: str, item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Put item to DynamoDB."""
        return self._provider.put_dynamodb_item(table_name, item)

    def get_dynamodb_item(
        self, table_name: str, key: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get item from DynamoDB."""
        return self._provider.get_dynamodb_item(table_name, key)

    def query_dynamodb(
        self,
        table_name: str,
        key_condition: str,
        expression_values: Dict[str, Any],
        index_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query DynamoDB table."""
        return self._provider.query_dynamodb(
            table_name, key_condition, expression_values, index_name, limit
        )

    def invoke_lambda(
        self, function_name: str, payload: Dict[str, Any], invocation_type: str = "RequestResponse"
    ) -> Dict[str, Any]:
        """Invoke Lambda function."""
        return self._provider.invoke_lambda(function_name, payload, invocation_type)

    def put_eventbridge_event(
        self,
        event_bus: str,
        source: str,
        detail_type: str,
        detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Put event to EventBridge."""
        return self._provider.put_eventbridge_event(event_bus, source, detail_type, detail)

    def retrieve_knowledge_base(
        self,
        knowledge_base_id: str,
        query: str,
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve from Knowledge Base."""
        return self._provider.retrieve_knowledge_base(knowledge_base_id, query, max_results)

    @property
    def call_history(self) -> List[Dict[str, Any]]:
        """Get call history (only available for mock provider)."""
        if isinstance(self._provider, MockAWSProvider):
            return self._provider.call_history
        return []

    def get_events(self) -> List[Dict[str, Any]]:
        """Get recorded events (only available for mock provider)."""
        if isinstance(self._provider, MockAWSProvider):
            return self._provider.get_events()
        return []
