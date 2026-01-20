#!/bin/bash
# Scenario: RDS Gradual Cost Increase
# Injects a gradual 3x cost increase for Amazon RDS over 3 days
#
# Baseline: $150/day
# Day 1: $225/day (1.5x)
# Day 2: $337/day (2.25x)
# Day 3: $450/day (3x)
#
# Expected Detection:
#   - Detection methods: trend
#   - Severity: HIGH
#   - Pattern: Exponential growth
#
# Usage:
#   ./rds-cost-spike.sh
#   # or via make: make cost-scenario-rds

set -e

echo "=== Injecting RDS Gradual Cost Increase Scenario ==="

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
TABLE_NAME="cost-service-history"
SERVICE_NAME="Amazon RDS"

export AWS_ENDPOINT_URL="$ENDPOINT"
export AWS_DEFAULT_REGION="$REGION"

# Get current timestamp
NOW=$(date -u +%s)

echo "Service: $SERVICE_NAME"
echo "Pattern: Gradual increase over 3 days"
echo ""

# Inject 3 days of gradually increasing costs
for i in 0 1 2; do
    TIMESTAMP=$((NOW - i * 86400))

    # Calculate cost with exponential increase (reverse order - most recent highest)
    case $((2 - i)) in
        0)
            COST="225.00"
            USAGE="1575"  # instance-hours
            ;;
        1)
            COST="337.50"
            USAGE="2362"
            ;;
        2)
            COST="450.00"
            USAGE="3150"
            ;;
    esac

    # Use date command compatible with both macOS and Linux
    if [[ "$OSTYPE" == "darwin"* ]]; then
        DATE_STR=$(date -u -r $TIMESTAMP +%Y-%m-%d)
        FULL_TIMESTAMP=$(date -u -r $TIMESTAMP +%Y-%m-%dT%H:%M:%SZ)
    else
        DATE_STR=$(date -u -d @$TIMESTAMP +%Y-%m-%d)
        FULL_TIMESTAMP=$(date -u -d @$TIMESTAMP +%Y-%m-%dT%H:%M:%SZ)
    fi

    echo "Day $((3 - i)): $DATE_STR - \$$COST"

    awslocal dynamodb put-item \
        --table-name "$TABLE_NAME" \
        --item '{
            "pk": {"S": "SERVICE#'"$SERVICE_NAME"'"},
            "sk": {"S": "DATE#'"$DATE_STR"'"},
            "service_name": {"S": "'"$SERVICE_NAME"'"},
            "cost": {"N": "'"$COST"'"},
            "usage_quantity": {"N": "'"$USAGE"'"},
            "region": {"S": "'"$REGION"'"},
            "timestamp": {"S": "'"$FULL_TIMESTAMP"'"},
            "currency": {"S": "USD"},
            "scenario": {"S": "rds-gradual-increase"},
            "is_spike": {"BOOL": true}
        }' \
        --region "$REGION"
done

echo ""
echo "=== RDS Gradual Increase Injected ==="
echo ""
echo "Expected Detection Results:"
echo "  - Service: $SERVICE_NAME"
echo "  - Baseline: ~\$150/day"
echo "  - Final cost: \$450/day (3x)"
echo "  - Pattern: Exponential growth"
echo "  - Detection methods: trend"
echo "  - Expected severity: HIGH"
echo ""
echo "Verify with:"
echo "  awslocal dynamodb query \\"
echo "    --table-name $TABLE_NAME \\"
echo "    --key-condition-expression 'pk = :pk' \\"
echo "    --expression-attribute-values '{\":pk\": {\"S\": \"SERVICE#$SERVICE_NAME\"}}' \\"
echo "    --scan-index-forward false \\"
echo "    --limit 5"
