#!/bin/bash
# Create DynamoDB tables for BDP Compact Agent

set -e

ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
REGION="${AWS_REGION:-ap-northeast-2}"

echo "Creating DynamoDB tables for BDP Compact Agent..."

# BDP Cost History Table (Multi-Account)
aws --endpoint-url=$ENDPOINT dynamodb create-table \
    --table-name bdp-cost-history \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region $REGION \
    2>/dev/null || echo "Table bdp-cost-history already exists"

# BDP Anomaly Tracking Table
aws --endpoint-url=$ENDPOINT dynamodb create-table \
    --table-name bdp-anomaly-tracking \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region $REGION \
    2>/dev/null || echo "Table bdp-anomaly-tracking already exists"

echo "DynamoDB tables created successfully!"

# List created tables
aws --endpoint-url=$ENDPOINT dynamodb list-tables --region $REGION
