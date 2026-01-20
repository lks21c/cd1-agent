#!/bin/bash
# Scenario: Multi-Service Cost Spike
# Injects simultaneous cost increases across multiple services
#
# EC2: $200 → $400 (2x)
# Lambda: $60 → $180 (3x)
# RDS: $150 → $225 (1.5x)
#
# Expected Detection:
#   - Batch detection should identify all three anomalies
#   - Indicates: Possible environment-wide issue (DDoS, traffic spike, etc.)
#   - Combined severity: CRITICAL
#
# Usage:
#   ./multi-service-spike.sh
#   # or via make: make cost-scenario-multi

set -e

echo "=== Injecting Multi-Service Cost Spike Scenario ==="

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
TABLE_NAME="cost-service-history"

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

echo "Date: $TODAY"
echo ""

# Service configurations: name|cost|usage
declare -a SERVICES=(
    "Amazon EC2|400.00|4000|2.0"
    "AWS Lambda|180.00|90000000|3.0"
    "Amazon RDS|225.00|1575|1.5"
)

for service_config in "${SERVICES[@]}"; do
    IFS='|' read -r service_name cost usage multiplier <<< "$service_config"

    echo "Injecting $service_name: \$$cost (${multiplier}x baseline)"

    awslocal dynamodb put-item \
        --table-name "$TABLE_NAME" \
        --item '{
            "pk": {"S": "SERVICE#'"$service_name"'"},
            "sk": {"S": "DATE#'"$TODAY"'"},
            "service_name": {"S": "'"$service_name"'"},
            "cost": {"N": "'"$cost"'"},
            "usage_quantity": {"N": "'"$usage"'"},
            "region": {"S": "'"$REGION"'"},
            "timestamp": {"S": "'"$TIMESTAMP"'"},
            "currency": {"S": "USD"},
            "scenario": {"S": "multi-service-spike"},
            "is_spike": {"BOOL": true}
        }' \
        --region "$REGION"
done

echo ""
echo "=== Multi-Service Cost Spike Injected ==="
echo ""
echo "Expected Detection Results:"
echo "  Services Affected:"
echo "    - Amazon EC2: \$200 → \$400 (2x) - HIGH"
echo "    - AWS Lambda: \$60 → \$180 (3x) - HIGH"
echo "    - Amazon RDS: \$150 → \$225 (1.5x) - MEDIUM"
echo ""
echo "  Total Impact:"
echo "    - Normal daily total: ~\$410"
echo "    - Spike daily total: ~\$805"
echo "    - Combined increase: ~96%"
echo ""
echo "  Expected Behavior:"
echo "    - Batch detection should find all 3 anomalies"
echo "    - Correlation analysis may identify common cause"
echo "    - Overall severity: CRITICAL (multiple services affected)"
echo ""
echo "Security Note:"
echo "  - Multi-service spikes may indicate:"
echo "    * DDoS attack response"
echo "    * Major traffic event"
echo "    * Infrastructure misconfiguration"
echo "    * Cryptocurrency mining attack"
echo ""
echo "Verify with:"
echo "  for svc in 'Amazon EC2' 'AWS Lambda' 'Amazon RDS'; do"
echo "    echo \"=== \$svc ===\""
echo "    awslocal dynamodb query \\"
echo "      --table-name $TABLE_NAME \\"
echo "      --key-condition-expression 'pk = :pk' \\"
echo "      --expression-attribute-values '{\":pk\": {\"S\": \"SERVICE#'\$svc'\"}}' \\"
echo "      --scan-index-forward false \\"
echo "      --limit 2"
echo "  done"
