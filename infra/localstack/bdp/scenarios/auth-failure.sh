#!/bin/bash
# Scenario: Authentication Failure
# Injects 8 consecutive auth failures to trigger pattern anomaly
# Expected: critical pattern_anomaly (exceeds threshold of 5)

set -e

REGION="ap-northeast-2"
LOG_GROUP="${1:-/aws/lambda/auth-service}"
LOCALSTACK_ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
MYSQL_HOST="${MYSQL_HOST:-localhost}"
MYSQL_USER="${MYSQL_USER:-cd1_user}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-cd1_password}"
MYSQL_DATABASE="${MYSQL_DATABASE:-cd1_agent}"

echo "=== Injecting Auth Failure Scenario ==="
echo "Log Group: $LOG_GROUP"
echo "Endpoint: $LOCALSTACK_ENDPOINT"
echo "MySQL Host: $MYSQL_HOST"

export AWS_ENDPOINT_URL="$LOCALSTACK_ENDPOINT"
export AWS_DEFAULT_REGION="$REGION"

NOW=$(date -u +%s%3N)
LOG_STREAM="auth-failure-$(date +%Y%m%d%H%M%S)"
TARGET_USER="attacker@suspicious.com"
SOURCE_IP="203.0.113.42"

# Create log group if not exists
awslocal logs create-log-group \
    --log-group-name "$LOG_GROUP" \
    --region "$REGION" 2>/dev/null || true

# Create log stream for this scenario
awslocal logs create-log-stream \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --region "$REGION" 2>/dev/null || true

# Build auth failure log events
EVENTS='['
for i in {1..8}; do
    TIMESTAMP=$((NOW + i * 5000))  # 5 second intervals
    if [ $i -gt 1 ]; then
        EVENTS+=','
    fi
    EVENTS+='{"timestamp": '"$TIMESTAMP"', "message": "ERROR AuthService: Failed login attempt for '"$TARGET_USER"' from IP '"$SOURCE_IP"' - Invalid credentials (attempt '"$i"')"}'
done
EVENTS+=']'

echo "Injecting 8 auth failure log events..."
awslocal logs put-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --log-events "$EVENTS" \
    --region "$REGION"

# Inject into MySQL auth_logs if MySQL is available
if command -v mysql &> /dev/null; then
    echo "Injecting auth failures into MySQL..."
    for i in {1..8}; do
        mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e \
            "INSERT INTO auth_logs (username, ip_address, success, failure_reason) VALUES ('$TARGET_USER', '$SOURCE_IP', FALSE, 'Invalid credentials - attempt $i');" 2>/dev/null || true
    done
    echo "MySQL auth_logs updated"
fi

echo ""
echo "=== Auth Failure Scenario Injected ==="
echo "Expected Detection:"
echo "  - anomaly_type: pattern_anomaly"
echo "  - pattern_type: auth_failure"
echo "  - pattern_id: auth_failed_login"
echo "  - match_count: 8 (threshold: 5)"
echo "  - severity: critical"
echo ""
echo "Verify CloudWatch:"
echo "  awslocal logs filter-log-events \\"
echo "    --log-group-name $LOG_GROUP \\"
echo "    --filter-pattern 'Failed login' \\"
echo "    --start-time $((NOW - 60000))"
echo ""
echo "Verify MySQL:"
echo "  mysql -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE \\"
echo "    -e \"SELECT * FROM auth_logs WHERE success = FALSE ORDER BY timestamp DESC LIMIT 10;\""
