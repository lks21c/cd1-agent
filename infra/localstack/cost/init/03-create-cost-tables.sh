#!/bin/bash
# Create Cost Agent-specific DynamoDB tables
# Simulates AWS Cost Explorer data storage
#
# Usage:
#   ./03-create-cost-tables.sh
#   # or via make: make cost-init

set -e

echo "=== Creating Cost Agent DynamoDB Tables ==="

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"

export AWS_ENDPOINT_URL="$ENDPOINT"
export AWS_DEFAULT_REGION="$REGION"

# ============================================================================
# cost-service-history: Service-level daily cost data
# ============================================================================
# Schema:
#   PK: SERVICE#{service_name} (e.g., SERVICE#AWS Lambda)
#   SK: DATE#{yyyy-mm-dd} (e.g., DATE#2024-01-15)
#   Attributes: cost, usage_quantity, region, timestamp

awslocal dynamodb create-table \
    --table-name cost-service-history \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION" 2>/dev/null || echo "Table cost-service-history already exists"

echo "Created table: cost-service-history"

# ============================================================================
# cost-anomaly-tracking: Detected cost anomalies
# ============================================================================
# Schema:
#   PK: ANOMALY#{anomaly_id}
#   SK: COST#{timestamp}
#   Attributes: service_name, severity, confidence_score, etc.

awslocal dynamodb create-table \
    --table-name cost-anomaly-tracking \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION" 2>/dev/null || echo "Table cost-anomaly-tracking already exists"

echo "Created table: cost-anomaly-tracking"

# ============================================================================
# cost-forecast-data: Cost forecasts
# ============================================================================
# Schema:
#   PK: FORECAST#{date}
#   SK: SERVICE#{service_name}
#   Attributes: mean, min, max, confidence

awslocal dynamodb create-table \
    --table-name cost-forecast-data \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION" 2>/dev/null || echo "Table cost-forecast-data already exists"

echo "Created table: cost-forecast-data"

# Verify tables created
echo ""
echo "Cost Agent tables:"
awslocal dynamodb list-tables --region "$REGION" | grep -E "cost-"

echo "=== Cost Agent DynamoDB Tables Created Successfully ==="
