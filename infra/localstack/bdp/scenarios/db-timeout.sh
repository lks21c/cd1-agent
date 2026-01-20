#!/bin/bash
# Scenario: Database Timeout
# Injects database timeout logs to trigger log_anomaly and pattern_anomaly
# Expected: log_anomaly + pattern match on timeout patterns

set -e

REGION="ap-northeast-2"
LOG_GROUP="${1:-/aws/lambda/data-processor}"
LOCALSTACK_ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
MYSQL_HOST="${MYSQL_HOST:-localhost}"
MYSQL_USER="${MYSQL_USER:-cd1_user}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-cd1_password}"
MYSQL_DATABASE="${MYSQL_DATABASE:-cd1_agent}"

echo "=== Injecting DB Timeout Scenario ==="
echo "Log Group: $LOG_GROUP"
echo "Endpoint: $LOCALSTACK_ENDPOINT"

export AWS_ENDPOINT_URL="$LOCALSTACK_ENDPOINT"
export AWS_DEFAULT_REGION="$REGION"

NOW=$(date -u +%s%3N)
LOG_STREAM="db-timeout-$(date +%Y%m%d%H%M%S)"

# Create log group if not exists
awslocal logs create-log-group \
    --log-group-name "$LOG_GROUP" \
    --region "$REGION" 2>/dev/null || true

# Create log stream for this scenario
awslocal logs create-log-stream \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --region "$REGION" 2>/dev/null || true

# Build diverse database timeout log events
EVENTS='[
    {"timestamp": '"$NOW"', "message": "ERROR: Database timeout - Query execution exceeded 30000ms limit"},
    {"timestamp": '"$((NOW + 2000))"', "message": "ERROR: Connection timeout connecting to database host rds-prod.cluster-xyz.ap-northeast-2.rds.amazonaws.com:3306"},
    {"timestamp": '"$((NOW + 4000))"', "message": "FATAL: Lock wait timeout exceeded; try restarting transaction"},
    {"timestamp": '"$((NOW + 6000))"', "message": "ERROR: Read timeout waiting for response from database after 60000ms"},
    {"timestamp": '"$((NOW + 8000))"', "message": "ERROR: Database timeout - Connection pool exhausted, no available connections"},
    {"timestamp": '"$((NOW + 10000))"', "message": "CRITICAL: Multiple database operations timing out - potential database overload"},
    {"timestamp": '"$((NOW + 12000))"', "message": "ERROR: SocketTimeoutException while executing SELECT query on users table"},
    {"timestamp": '"$((NOW + 14000))"', "message": "ERROR: Database timeout - Deadlock detected, transaction rolled back"},
    {"timestamp": '"$((NOW + 16000))"', "message": "WARN: Database response time degraded - average latency 5000ms (normal: 50ms)"},
    {"timestamp": '"$((NOW + 18000))"', "message": "ERROR: ConnectTimeoutException - Unable to establish database connection after 3 retries"}
]'

echo "Injecting database timeout log events..."
awslocal logs put-log-events \
    --log-group-name "$LOG_GROUP" \
    --log-stream-name "$LOG_STREAM" \
    --log-events "$EVENTS" \
    --region "$REGION"

# Inject into MySQL slow_query_log if MySQL is available
if command -v mysql &> /dev/null; then
    echo "Injecting slow queries into MySQL..."
    mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" <<EOF 2>/dev/null || true
INSERT INTO slow_query_log (query_hash, query_text, execution_time_ms, rows_examined, database_name) VALUES
('abc123', 'SELECT * FROM users WHERE status = "active"', 35000, 1000000, 'production'),
('def456', 'UPDATE orders SET status = "completed" WHERE created_at < NOW() - INTERVAL 30 DAY', 45000, 500000, 'production'),
('ghi789', 'SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id', 60000, 2000000, 'production'),
('jkl012', 'DELETE FROM sessions WHERE expires_at < NOW()', 30000, 100000, 'production'),
('mno345', 'SELECT COUNT(*) FROM logs WHERE timestamp > NOW() - INTERVAL 1 HOUR', 40000, 5000000, 'production');
EOF
    echo "MySQL slow_query_log updated"
fi

echo ""
echo "=== DB Timeout Scenario Injected ==="
echo "Expected Detections:"
echo ""
echo "1. Log Anomaly:"
echo "   - anomaly_type: log_anomaly"
echo "   - error_count: >= 10"
echo "   - severity: high"
echo ""
echo "2. Pattern Anomaly (timeout):"
echo "   - anomaly_type: pattern_anomaly"
echo "   - pattern_type: timeout"
echo "   - pattern_id: timeout_db"
echo "   - severity: critical"
echo ""
echo "3. Pattern Anomaly (resource_exhaustion):"
echo "   - pattern_type: resource_exhaustion"
echo "   - pattern_id: res_conn_pool"
echo ""
echo "Verify CloudWatch:"
echo "  awslocal logs filter-log-events \\"
echo "    --log-group-name $LOG_GROUP \\"
echo "    --filter-pattern 'timeout OR Timeout OR TIMEOUT' \\"
echo "    --start-time $((NOW - 60000))"
echo ""
echo "Verify MySQL slow queries:"
echo "  mysql -h $MYSQL_HOST -u $MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DATABASE \\"
echo "    -e \"SELECT * FROM slow_query_log ORDER BY execution_time_ms DESC LIMIT 10;\""
