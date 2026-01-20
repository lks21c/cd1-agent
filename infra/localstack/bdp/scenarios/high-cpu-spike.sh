#!/bin/bash
# Scenario: High CPU Spike
# Injects CPU metrics with a 95% spike to trigger metric anomaly detection
# Expected: z-score > 2.0, severity: high

set -e

REGION="ap-northeast-2"
NAMESPACE="AWS/Lambda"
FUNCTION_NAME="${1:-test-function}"
LOCALSTACK_ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"

echo "=== Injecting High CPU Spike Scenario ==="
echo "Function: $FUNCTION_NAME"
echo "Endpoint: $LOCALSTACK_ENDPOINT"

export AWS_ENDPOINT_URL="$LOCALSTACK_ENDPOINT"
export AWS_DEFAULT_REGION="$REGION"

NOW=$(date -u +%s)

# Inject historical normal CPU values (35% average with small variance)
echo "Injecting historical normal CPU metrics..."
for i in {1..24}; do
    TIMESTAMP=$((NOW - i * 3600))
    VALUE=$((35 + RANDOM % 5))  # 35-40%

    awslocal cloudwatch put-metric-data \
        --namespace "$NAMESPACE" \
        --metric-name "CPUUtilization" \
        --dimensions Name=FunctionName,Value="$FUNCTION_NAME" \
        --value "$VALUE" \
        --timestamp "$(date -u -r $TIMESTAMP +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d @$TIMESTAMP +%Y-%m-%dT%H:%M:%SZ)" \
        --region "$REGION" 2>/dev/null || true
done

# Inject the spike (95%)
echo "Injecting CPU spike (95%)..."
awslocal cloudwatch put-metric-data \
    --namespace "$NAMESPACE" \
    --metric-name "CPUUtilization" \
    --dimensions Name=FunctionName,Value="$FUNCTION_NAME" \
    --value 95 \
    --timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --region "$REGION"

echo ""
echo "=== CPU Spike Scenario Injected ==="
echo "Expected Detection:"
echo "  - anomaly_type: metric_anomaly"
echo "  - metric: CPUUtilization"
echo "  - z_score: > 2.0 (estimated ~12.0)"
echo "  - severity: high"
echo ""
echo "Verify with: awslocal cloudwatch get-metric-statistics \\"
echo "    --namespace $NAMESPACE \\"
echo "    --metric-name CPUUtilization \\"
echo "    --dimensions Name=FunctionName,Value=$FUNCTION_NAME \\"
echo "    --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ) \\"
echo "    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \\"
echo "    --period 3600 \\"
echo "    --statistics Average"
