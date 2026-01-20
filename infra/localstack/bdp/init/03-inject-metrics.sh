#!/bin/bash
# Inject baseline CloudWatch metrics for BDP Agent testing
# Executed automatically when LocalStack starts

set -e

echo "=== Injecting CloudWatch Metrics ==="

REGION="ap-northeast-2"
NAMESPACE="AWS/Lambda"
NOW=$(date -u +%s)

# Function to inject metric data
inject_metric() {
    local metric_name=$1
    local function_name=$2
    local value=$3
    local timestamp=$4

    awslocal cloudwatch put-metric-data \
        --namespace "$NAMESPACE" \
        --metric-name "$metric_name" \
        --dimensions Name=FunctionName,Value="$function_name" \
        --value "$value" \
        --timestamp "$timestamp" \
        --region "$REGION"
}

# Inject baseline CPU metrics for test-function (normal values ~30-40%)
echo "Injecting CPU metrics for test-function..."
for i in {0..23}; do
    TIMESTAMP=$((NOW - i * 3600))
    # Normal CPU values around 35% with slight variance
    VALUE=$((35 + RANDOM % 10))
    inject_metric "CPUUtilization" "test-function" "$VALUE" "$(date -u -r $TIMESTAMP +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d @$TIMESTAMP +%Y-%m-%dT%H:%M:%SZ)"
done

# Inject baseline error metrics (normal ~0-2)
echo "Injecting Error metrics for test-function..."
for i in {0..23}; do
    TIMESTAMP=$((NOW - i * 3600))
    VALUE=$((RANDOM % 3))
    inject_metric "Errors" "test-function" "$VALUE" "$(date -u -r $TIMESTAMP +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d @$TIMESTAMP +%Y-%m-%dT%H:%M:%SZ)"
done

# Inject baseline Duration metrics (normal ~100-200ms)
echo "Injecting Duration metrics for test-function..."
for i in {0..23}; do
    TIMESTAMP=$((NOW - i * 3600))
    VALUE=$((100 + RANDOM % 100))
    inject_metric "Duration" "test-function" "$VALUE" "$(date -u -r $TIMESTAMP +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d @$TIMESTAMP +%Y-%m-%dT%H:%M:%SZ)"
done

# Inject baseline Invocations metrics (normal ~100-150)
echo "Injecting Invocations metrics for test-function..."
for i in {0..23}; do
    TIMESTAMP=$((NOW - i * 3600))
    VALUE=$((100 + RANDOM % 50))
    inject_metric "Invocations" "test-function" "$VALUE" "$(date -u -r $TIMESTAMP +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d @$TIMESTAMP +%Y-%m-%dT%H:%M:%SZ)"
done

# List metrics to verify
awslocal cloudwatch list-metrics \
    --namespace "$NAMESPACE" \
    --region "$REGION"

echo "=== CloudWatch Metrics Injection Complete ==="
