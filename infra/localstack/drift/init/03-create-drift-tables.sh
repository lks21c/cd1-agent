#!/bin/bash
# ============================================================================
# Drift Agent - DynamoDB Table Creation Script
# ============================================================================
#
# Creates DynamoDB tables required for Drift Agent LocalStack testing:
#   - drift-baseline-configs: Stores baseline configuration versions
#   - drift-current-configs: Stores simulated current configurations
#   - drift-detection-results: Stores drift detection results
#
# Usage:
#   LOCALSTACK_ENDPOINT=http://localhost:4566 ./03-create-drift-tables.sh
#
# ============================================================================

set -e

ENDPOINT=${LOCALSTACK_ENDPOINT:-http://localhost:4566}
REGION=${AWS_REGION:-ap-northeast-2}

echo "Creating Drift Agent DynamoDB tables..."
echo "Endpoint: $ENDPOINT"
echo "Region: $REGION"

# ----------------------------------------------------------------------------
# Table 1: drift-baseline-configs
# Purpose: Store baseline configurations for drift comparison
# PK: RESOURCE#{type}#{id}  SK: VERSION#{timestamp}
# ----------------------------------------------------------------------------
echo ""
echo "Creating drift-baseline-configs table..."

aws dynamodb create-table \
    --endpoint-url "$ENDPOINT" \
    --region "$REGION" \
    --table-name drift-baseline-configs \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --no-cli-pager 2>/dev/null || echo "Table drift-baseline-configs already exists"

# ----------------------------------------------------------------------------
# Table 2: drift-current-configs
# Purpose: Store simulated current configurations (what AWS would return)
# PK: RESOURCE#{type}#{id}  SK: FETCH#{timestamp}
# ----------------------------------------------------------------------------
echo ""
echo "Creating drift-current-configs table..."

aws dynamodb create-table \
    --endpoint-url "$ENDPOINT" \
    --region "$REGION" \
    --table-name drift-current-configs \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --no-cli-pager 2>/dev/null || echo "Table drift-current-configs already exists"

# ----------------------------------------------------------------------------
# Table 3: drift-detection-results
# Purpose: Store drift detection results for audit/history
# PK: DRIFT#{date}  SK: RESOURCE#{type}#{id}
# ----------------------------------------------------------------------------
echo ""
echo "Creating drift-detection-results table..."

aws dynamodb create-table \
    --endpoint-url "$ENDPOINT" \
    --region "$REGION" \
    --table-name drift-detection-results \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --no-cli-pager 2>/dev/null || echo "Table drift-detection-results already exists"

# Wait for tables to be active
echo ""
echo "Waiting for tables to be active..."

for table in drift-baseline-configs drift-current-configs drift-detection-results; do
    aws dynamodb wait table-exists \
        --endpoint-url "$ENDPOINT" \
        --region "$REGION" \
        --table-name "$table" 2>/dev/null || true
done

echo ""
echo "Drift Agent DynamoDB tables created successfully!"
echo ""
echo "Tables:"
aws dynamodb list-tables \
    --endpoint-url "$ENDPOINT" \
    --region "$REGION" \
    --query 'TableNames[?starts_with(@, `drift-`)]' \
    --output table \
    --no-cli-pager 2>/dev/null || true
