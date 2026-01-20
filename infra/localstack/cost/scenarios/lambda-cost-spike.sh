#!/bin/bash
# Scenario: Lambda Cost Spike
# Injects a sudden 5x cost increase for AWS Lambda
#
# Baseline: $60/day
# Spike: $300/day (5x increase)
#
# Expected Detection:
#   - Detection methods: ratio, stddev, luminol
#   - Severity: CRITICAL
#   - Change ratio: 5.0
#
# Usage:
#   ./lambda-cost-spike.sh
#   # or via make: make cost-scenario-lambda

set -e

echo "=== Injecting Lambda Cost Spike Scenario ==="

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
TABLE_NAME="cost-service-history"
SERVICE_NAME="AWS Lambda"

export AWS_ENDPOINT_URL="$ENDPOINT"
export AWS_DEFAULT_REGION="$REGION"

# Get current timestamp
NOW=$(date -u +%s)

# Use date command compatible with both macOS and Linux
if [[ "$OSTYPE" == "darwin"* ]]; then
    TODAY=$(date -u -r $NOW +%Y-%m-%d)
    TIMESTAMP=$(date -u -r $NOW +%Y-%m-%dT%H:%M:%SZ)
else
    TODAY=$(date -u -d @$NOW +%Y-%m-%d)
    TIMESTAMP=$(date -u -d @$NOW +%Y-%m-%dT%H:%M:%SZ)
fi

SPIKE_COST="300.00"
SPIKE_USAGE="150000000"  # 150M invocations

echo "Service: $SERVICE_NAME"
echo "Date: $TODAY"
echo "Spike Cost: \$$SPIKE_COST (5x baseline)"
echo ""

# Inject the spike
awslocal dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item '{
        "pk": {"S": "SERVICE#'"$SERVICE_NAME"'"},
        "sk": {"S": "DATE#'"$TODAY"'"},
        "service_name": {"S": "'"$SERVICE_NAME"'"},
        "cost": {"N": "'"$SPIKE_COST"'"},
        "usage_quantity": {"N": "'"$SPIKE_USAGE"'"},
        "region": {"S": "'"$REGION"'"},
        "timestamp": {"S": "'"$TIMESTAMP"'"},
        "currency": {"S": "USD"},
        "scenario": {"S": "lambda-cost-spike"},
        "is_spike": {"BOOL": true}
    }' \
    --region "$REGION"

echo "=== Lambda Cost Spike Injected ==="
echo ""
echo "Expected Detection Results:"
echo "  - Service: $SERVICE_NAME"
echo "  - Baseline: ~\$60/day"
echo "  - Spike: \$$SPIKE_COST/day"
echo "  - Change ratio: 5.0"
echo "  - Detection methods: ratio, stddev, luminol"
echo "  - Expected severity: CRITICAL"
echo ""
echo "Verify with:"
echo "  awslocal dynamodb query \\"
echo "    --table-name $TABLE_NAME \\"
echo "    --key-condition-expression 'pk = :pk' \\"
echo "    --expression-attribute-values '{\":pk\": {\"S\": \"SERVICE#$SERVICE_NAME\"}}' \\"
echo "    --scan-index-forward false \\"
echo "    --limit 5"
