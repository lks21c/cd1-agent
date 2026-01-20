#!/bin/bash
# Scenario: Error Log Flood
# Injects 15+ error logs to trigger log anomaly detection
# Expected: log_anomaly detected, EventBridge notification sent

set -e

REGION="ap-northeast-2"
LOG_GROUP="${1:-/aws/lambda/test-function}"
LOCALSTACK_ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"

echo "=== Injecting Error Flood Scenario ==="
echo "Log Group: $LOG_GROUP"
echo "Endpoint: $LOCALSTACK_ENDPOINT"

export AWS_ENDPOINT_URL="$LOCALSTACK_ENDPOINT"
export AWS_DEFAULT_REGION="$REGION"

NOW=$(date -u +%s%3N)
LOG_STREAM="error-flood-$(date +%Y%m%d%H%M%S)"

# Create log stream for this scenario
awslocal logs create-log-stream \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --region "$REGION" 2>/dev/null || true

# Build log events JSON with 15 error messages
EVENTS='['
for i in {1..15}; do
    TIMESTAMP=$((NOW + i * 1000))
    if [ $i -gt 1 ]; then
        EVENTS+=','
    fi
    EVENTS+='{"timestamp": '"$TIMESTAMP"', "message": "ERROR: Database connection timeout - attempt '"$i"' failed after 30000ms"}'
done
EVENTS+=']'

echo "Injecting 15 error log events..."
awslocal logs put-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --log-events "$EVENTS" \
    --region "$REGION"

# Also inject some related warning logs
WARNING_EVENTS='[
    {"timestamp": '"$((NOW + 16000))"', "message": "WARN: Connection pool running low - 2 connections remaining"},
    {"timestamp": '"$((NOW + 17000))"', "message": "WARN: Retry attempt 3 of 5 for database operation"},
    {"timestamp": '"$((NOW + 18000))"', "message": "WARN: Circuit breaker triggered for database service"}
]'

awslocal logs put-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --log-events "$WARNING_EVENTS" \
    --region "$REGION"

echo ""
echo "=== Error Flood Scenario Injected ==="
echo "Expected Detection:"
echo "  - anomaly_type: log_anomaly"
echo "  - error_count: >= 10 (threshold)"
echo "  - severity: high"
echo "  - EventBridge notification: sent"
echo ""
echo "Verify with: awslocal logs filter-log-events \\"
echo "    --log-group-name $LOG_GROUP \\"
echo "    --filter-pattern 'ERROR' \\"
echo "    --start-time $((NOW - 60000))"
