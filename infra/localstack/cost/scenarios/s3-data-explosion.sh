#!/bin/bash
# Scenario: S3 Data Explosion
# Injects a massive ~17x cost increase for Amazon S3 (data transfer explosion)
#
# Baseline: $30/day
# Spike: $500/day (~17x increase)
#
# Expected Detection:
#   - Detection methods: trend, luminol, ratio
#   - Severity: CRITICAL
#   - Indicates: Possible data exfiltration or misconfigured replication
#
# Usage:
#   ./s3-data-explosion.sh
#   # or via make: make cost-scenario-s3

set -e

echo "=== Injecting S3 Data Explosion Scenario ==="

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
TABLE_NAME="cost-service-history"
SERVICE_NAME="Amazon S3"

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

SPIKE_COST="500.00"
SPIKE_USAGE="21739"  # ~21.7 TB storage/transfer

echo "Service: $SERVICE_NAME"
echo "Date: $TODAY"
echo "Spike Cost: \$$SPIKE_COST (~17x baseline)"
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
        "scenario": {"S": "s3-data-explosion"},
        "is_spike": {"BOOL": true}
    }' \
    --region "$REGION"

echo "=== S3 Data Explosion Injected ==="
echo ""
echo "Expected Detection Results:"
echo "  - Service: $SERVICE_NAME"
echo "  - Baseline: ~\$30/day"
echo "  - Spike: \$$SPIKE_COST/day"
echo "  - Change ratio: ~16.7"
echo "  - Detection methods: trend, luminol, ratio"
echo "  - Expected severity: CRITICAL"
echo ""
echo "Security Note:"
echo "  - This pattern may indicate:"
echo "    * Data exfiltration attempt"
echo "    * Misconfigured cross-region replication"
echo "    * Runaway backup jobs"
echo "    * Compromised access credentials"
echo ""
echo "Verify with:"
echo "  awslocal dynamodb query \\"
echo "    --table-name $TABLE_NAME \\"
echo "    --key-condition-expression 'pk = :pk' \\"
echo "    --expression-attribute-values '{\":pk\": {\"S\": \"SERVICE#$SERVICE_NAME\"}}' \\"
echo "    --scan-index-forward false \\"
echo "    --limit 5"
