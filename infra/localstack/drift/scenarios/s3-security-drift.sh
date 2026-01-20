#!/bin/bash
# ============================================================================
# Drift Scenario: S3 Bucket Security Drift (CRITICAL)
# ============================================================================
#
# Simulates critical security drift in S3 bucket configuration:
#   - block_public_acls disabled (was enabled)
#
# This is a CRITICAL severity drift as it could expose sensitive data.
#
# Expected severity: CRITICAL
#
# Usage:
#   LOCALSTACK_ENDPOINT=http://localhost:4566 ./s3-security-drift.sh
#
# ============================================================================

set -e

ENDPOINT=${LOCALSTACK_ENDPOINT:-http://localhost:4566}
REGION=${AWS_REGION:-ap-northeast-2}
TABLE_NAME=${DRIFT_CURRENT_TABLE:-drift-current-configs}
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Injecting S3 security drift scenario (CRITICAL)..."
echo "Endpoint: $ENDPOINT"
echo "Table: $TABLE_NAME"

# Drifted S3 configuration
# - block_public_acls: true -> false (CRITICAL security issue)
DRIFTED_CONFIG=$(cat <<'EOF'
{
    "bucket_name": "company-data-lake-prod",
    "versioning": {
        "status": "Enabled"
    },
    "encryption": {
        "sse_algorithm": "aws:kms",
        "kms_master_key_id": "alias/data-lake-key",
        "bucket_key_enabled": true
    },
    "public_access_block": {
        "block_public_acls": false,
        "ignore_public_acls": true,
        "block_public_policy": true,
        "restrict_public_buckets": true
    },
    "tags": {
        "Environment": "production",
        "DataClassification": "confidential"
    }
}
EOF
)

# Build DynamoDB item
ITEM=$(cat <<EOF
{
    "pk": {"S": "RESOURCE#s3#company-data-lake-prod"},
    "sk": {"S": "FETCH#${TIMESTAMP}"},
    "resource_type": {"S": "s3"},
    "resource_id": {"S": "company-data-lake-prod"},
    "resource_arn": {"S": "arn:aws:s3:::company-data-lake-prod"},
    "config": {"S": $(echo "$DRIFTED_CONFIG" | jq -c '.' | jq -Rs '.')},
    "fetched_at": {"S": "${TIMESTAMP}"},
    "is_latest": {"BOOL": true}
}
EOF
)

# Put item to DynamoDB
aws dynamodb put-item \
    --endpoint-url "$ENDPOINT" \
    --region "$REGION" \
    --table-name "$TABLE_NAME" \
    --item "$ITEM" \
    --no-cli-pager 2>/dev/null

echo ""
echo "S3 security drift scenario injected successfully!"
echo ""
echo "Drift details:"
echo "  - Resource: s3/company-data-lake-prod"
echo "  - Drift: block_public_acls changed from true to false"
echo "  - Data classification: confidential"
echo "  - Expected severity: CRITICAL"
echo ""
echo "WARNING: This simulates a critical security vulnerability!"
