#!/bin/bash
# Scenario: EC2 Cost Spike
# Injects a sudden 4x cost increase for Amazon EC2
#
# Baseline: $200/day
# Spike: $800/day (4x increase)
#
# Expected Detection:
#   - Detection methods: ratio, stddev
#   - Severity: HIGH
#   - Change ratio: 4.0
#
# Usage:
#   ./ec2-cost-spike.sh
#   # or via make: make cost-scenario-ec2

set -e

echo "=== Injecting EC2 Cost Spike Scenario ==="

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
TABLE_NAME="cost-service-history"
SERVICE_NAME="Amazon EC2"

export AWS_ENDPOINT_URL="$ENDPOINT"
export AWS_DEFAULT_REGION="$REGION"

# Get current timestamp
NOW=$(date -u +%s)

# Use date command compatible with both macOS and Linux
if [[ "$OSTYPE" == "darwin"* ]]; then
    TODAY=$(date -u -r $NOW +%Y-%m-%d)
    YESTERDAY=$(date -u -r $((NOW - 86400)) +%Y-%m-%d)
    TIMESTAMP=$(date -u -r $NOW +%Y-%m-%dT%H:%M:%SZ)
else
    TODAY=$(date -u -d @$NOW +%Y-%m-%d)
    YESTERDAY=$(date -u -d @$((NOW - 86400)) +%Y-%m-%d)
    TIMESTAMP=$(date -u -d @$NOW +%Y-%m-%dT%H:%M:%SZ)
fi

SPIKE_COST="800.00"
SPIKE_USAGE="8000"  # 8000 instance-hours

echo "Service: $SERVICE_NAME"
echo "Date: $TODAY"
echo "Spike Cost: \$$SPIKE_COST (4x baseline)"
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
        "scenario": {"S": "ec2-cost-spike"},
        "is_spike": {"BOOL": true}
    }' \
    --region "$REGION"

echo "=== EC2 Cost Spike Injected ==="
echo ""
echo "Expected Detection Results:"
echo "  - Service: $SERVICE_NAME"
echo "  - Baseline: ~\$200/day"
echo "  - Spike: \$$SPIKE_COST/day"
echo "  - Change ratio: 4.0"
echo "  - Detection methods: ratio, stddev"
echo "  - Expected severity: HIGH"
echo ""
echo "Verify with:"
echo "  awslocal dynamodb query \\"
echo "    --table-name $TABLE_NAME \\"
echo "    --key-condition-expression 'pk = :pk' \\"
echo "    --expression-attribute-values '{\":pk\": {\"S\": \"SERVICE#$SERVICE_NAME\"}}' \\"
echo "    --scan-index-forward false \\"
echo "    --limit 5"
