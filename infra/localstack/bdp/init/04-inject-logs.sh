#!/bin/bash
# Inject baseline CloudWatch Logs for BDP Agent testing
# Executed automatically when LocalStack starts

set -e

echo "=== Injecting CloudWatch Logs ==="

REGION="ap-northeast-2"
LOG_GROUP="/aws/lambda/test-function"
LOG_STREAM="test-stream-$(date +%Y%m%d)"
NOW=$(date -u +%s%3N)

# Create log group
awslocal logs create-log-group \
    --log-group-name "$LOG_GROUP" \
    --region "$REGION" || true

echo "Created log group: $LOG_GROUP"

# Create log stream
awslocal logs create-log-stream \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --region "$REGION" || true

echo "Created log stream: $LOG_STREAM"

# Inject baseline log events (normal operation)
EVENTS='[
    {"timestamp": '"$NOW"', "message": "INFO: Function started successfully"},
    {"timestamp": '"$((NOW+1000))"', "message": "INFO: Processing request id=abc-123"},
    {"timestamp": '"$((NOW+2000))"', "message": "INFO: Database connection established"},
    {"timestamp": '"$((NOW+3000))"', "message": "INFO: Query executed in 50ms"},
    {"timestamp": '"$((NOW+4000))"', "message": "INFO: Response sent to client"},
    {"timestamp": '"$((NOW+5000))"', "message": "INFO: Function completed successfully"}
]'

awslocal logs put-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --log-events "$EVENTS" \
    --region "$REGION"

echo "Injected baseline log events"

# Create additional log groups for multi-service testing
for service in auth-service api-gateway data-processor; do
    SERVICE_LOG_GROUP="/aws/lambda/$service"
    SERVICE_LOG_STREAM="$service-stream-$(date +%Y%m%d)"

    awslocal logs create-log-group \
        --log-group-name "$SERVICE_LOG_GROUP" \
        --region "$REGION" || true

    awslocal logs create-log-stream \
        --log-group-name "$SERVICE_LOG_GROUP" \
        --log-stream-name "$SERVICE_LOG_STREAM" \
        --region "$REGION" || true

    # Inject normal logs for each service
    NORMAL_EVENTS='[
        {"timestamp": '"$NOW"', "message": "INFO: '"$service"' started"},
        {"timestamp": '"$((NOW+1000))"', "message": "INFO: Health check passed"},
        {"timestamp": '"$((NOW+2000))"', "message": "INFO: Request processed successfully"}
    ]'

    awslocal logs put-log-events \
        --log-group-name "$SERVICE_LOG_GROUP" \
        --log-stream-name "$SERVICE_LOG_STREAM" \
        --log-events "$NORMAL_EVENTS" \
        --region "$REGION"

    echo "Created log group and injected logs for: $service"
done

# List log groups to verify
awslocal logs describe-log-groups --region "$REGION"

echo "=== CloudWatch Logs Injection Complete ==="
