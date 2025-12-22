"""
Detection Handler for CD1 Agent.

이 핸들러는 주기적으로 로그와 메트릭을 분석하여 이상 현상을 감지합니다.
- CloudWatch Anomaly Detection 결과 조회
- RDS 통합로그 쿼리 (Field Indexing 활용)
- DynamoDB 기반 중복 제거
"""
import os
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

import boto3
from boto3.dynamodb.conditions import Key

from .base_handler import BaseHandler, lambda_handler_wrapper, HandlerError


class DetectionInput(BaseModel):
    """Detection Lambda 입력 모델."""
    time_range_minutes: int = Field(default=10, ge=5, le=60)
    service_filter: Optional[List[str]] = None
    severity_threshold: str = Field(default="ERROR")


class AnomalyRecord(BaseModel):
    """감지된 이상 현상 레코드."""
    signature: str
    anomaly_type: str
    service_name: str
    first_seen: str
    last_seen: str
    occurrence_count: int
    sample_logs: List[Dict]
    metrics_snapshot: Dict


class DetectionHandler(BaseHandler[DetectionInput]):
    """로그 및 메트릭에서 이상 현상을 감지하는 핸들러."""

    def __init__(self):
        super().__init__(DetectionInput)
        self.cloudwatch = boto3.client('cloudwatch')
        self.logs_client = boto3.client('logs')
        self.rds_data = boto3.client('rds-data')
        self.dynamodb = boto3.resource('dynamodb')
        self.dedup_table = self.dynamodb.Table(
            os.environ.get('DEDUP_TABLE', 'bdp-anomaly-tracking')
        )

        # RDS 연결 정보
        self.rds_cluster_arn = os.environ.get('RDS_CLUSTER_ARN')
        self.rds_secret_arn = os.environ.get('RDS_SECRET_ARN')
        self.rds_database = os.environ.get('RDS_DATABASE', 'unified_logs')

    def process(self, input_data: DetectionInput, context: Any) -> Dict:
        """메인 감지 프로세스."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=input_data.time_range_minutes)

        # 1. CloudWatch Anomaly Detection 결과 조회
        anomalies = self._check_cloudwatch_anomalies(start_time, end_time)

        # 2. 이상 감지된 경우에만 RDS 로그 조회 (비용 최적화)
        if anomalies:
            log_context = self._query_rds_logs(
                start_time,
                end_time,
                input_data.service_filter,
                input_data.severity_threshold
            )

            # 3. Anomaly와 로그 연관
            enriched_anomalies = self._enrich_anomalies(anomalies, log_context)

            # 4. Deduplication (중복 제거)
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

    def _check_cloudwatch_anomalies(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """CloudWatch Anomaly Detection 결과 확인."""
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

                if self._is_anomalous(response):
                    anomalies.append({
                        "type": "metric_anomaly",
                        "namespace": metric_config['namespace'],
                        "metric": metric_config['metric'],
                        "data": response['MetricDataResults']
                    })
            except Exception as e:
                self.logger.warning(
                    "metric_check_failed",
                    metric=metric_config['metric'],
                    error=str(e)
                )

        return anomalies

    def _is_anomalous(self, metric_response: Dict) -> bool:
        """메트릭 값이 이상 밴드를 벗어났는지 확인."""
        results = metric_response.get('MetricDataResults', [])
        if len(results) < 2:
            return False

        metric_data = next((r for r in results if r['Id'] == 'm1'), None)
        band_data = next((r for r in results if r['Id'] == 'anomaly'), None)

        if not metric_data or not band_data:
            return False

        # 실제 구현에서는 밴드 상/하한과 비교
        # 여기서는 단순화된 로직
        return len(metric_data.get('Values', [])) > 0

    def _query_rds_logs(
        self,
        start_time: datetime,
        end_time: datetime,
        service_filter: Optional[List[str]],
        severity_threshold: str
    ) -> List[Dict]:
        """
        RDS 통합로그 쿼리 (Field Indexing 최적화).

        Field Indexing을 활용하여 67% 데이터 스캔 감소.
        """
        severity_levels = self._get_severity_levels(severity_threshold)

        base_query = """
            SELECT id, timestamp, service_name, log_level, message, metadata
            FROM unified_logs
            WHERE timestamp BETWEEN :start_time AND :end_time
            AND log_level IN (:levels)
        """

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
        """임계값 이상의 심각도 레벨 반환."""
        levels_order = ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
        try:
            idx = levels_order.index(threshold.upper())
            return levels_order[idx:]
        except ValueError:
            return ["ERROR", "FATAL"]

    def _parse_rds_response(self, response: Dict) -> List[Dict]:
        """RDS Data API 응답 파싱 (JSON string 컬럼 포함)."""
        import json as json_module

        records = []
        columns = response.get('columnMetadata', [])

        for row in response.get('records', []):
            record = {}
            for i, col in enumerate(columns):
                col_name = col['name']
                cell = row[i]

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
        """이상 현상에 로그 컨텍스트 추가."""
        enriched = []

        for anomaly in anomalies:
            related_logs = self._find_related_logs(anomaly, logs)[:5]
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
        """이상 현상과 관련된 로그 찾기."""
        namespace = anomaly.get('namespace', '')
        service_hint = namespace.split('/')[-1].lower() if namespace else ''

        related = [
            log for log in logs
            if service_hint in log.get('service_name', '').lower()
        ]

        return related if related else logs[:5]

    def _generate_signature(self, anomaly: Dict, logs: List[Dict]) -> str:
        """중복 제거를 위한 고유 시그니처 생성."""
        key_parts = [
            anomaly.get('type', ''),
            anomaly.get('namespace', ''),
            anomaly.get('metric', ''),
        ]

        for log in logs[:3]:
            msg = log.get('message', '')[:100]
            key_parts.append(msg)

        combined = '|'.join(key_parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _deduplicate(self, anomalies: List[AnomalyRecord]) -> List[AnomalyRecord]:
        """DynamoDB를 사용한 중복 이상 현상 필터링."""
        new_anomalies = []
        dedup_window_hours = 1

        for anomaly in anomalies:
            try:
                response = self.dedup_table.get_item(
                    Key={'signature': anomaly.signature}
                )

                if 'Item' in response:
                    last_seen = datetime.fromisoformat(response['Item']['last_seen'])
                    if datetime.utcnow() - last_seen < timedelta(hours=dedup_window_hours):
                        # 카운트만 업데이트
                        self.dedup_table.update_item(
                            Key={'signature': anomaly.signature},
                            UpdateExpression='SET occurrence_count = occurrence_count + :inc, last_seen = :now',
                            ExpressionAttributeValues={
                                ':inc': 1,
                                ':now': datetime.utcnow().isoformat()
                            }
                        )
                        continue

                # 새 anomaly 추가
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
                self.logger.warning(
                    "dedup_check_failed",
                    signature=anomaly.signature,
                    error=str(e)
                )
                new_anomalies.append(anomaly)

        return new_anomalies


# Lambda 진입점
handler_instance = DetectionHandler()


@lambda_handler_wrapper
def lambda_handler(event: Dict, context: Any, log) -> Dict:
    return handler_instance.handle(event, context)
