#!/bin/bash
# Create common DynamoDB tables for CD1 Agent
# Shared across all agents (BDP, Cost, HDSP, Drift)
# Executed automatically when LocalStack starts

set -e

echo "=== Creating Common DynamoDB Tables ==="

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"

# Create cd1-agent-results table (shared across all agents)
awslocal dynamodb create-table \
    --table-name cd1-agent-results \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION" 2>/dev/null || echo "Table cd1-agent-results already exists"

echo "Created table: cd1-agent-results"

# Create cd1-agent-patterns table (for detection patterns cache)
awslocal dynamodb create-table \
    --table-name cd1-agent-patterns \
    --attribute-definitions \
        AttributeName=pattern_id,AttributeType=S \
    --key-schema \
        AttributeName=pattern_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION" 2>/dev/null || echo "Table cd1-agent-patterns already exists"

echo "Created table: cd1-agent-patterns"

# Verify tables created
awslocal dynamodb list-tables --region "$REGION"

echo "=== Common DynamoDB Tables Created Successfully ==="
