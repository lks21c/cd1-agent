#!/bin/bash
# Setup EventBridge for BDP Compact Agent

set -e

ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
REGION="${AWS_REGION:-ap-northeast-2}"

echo "Setting up EventBridge for BDP Compact Agent..."

# Create event bus
aws --endpoint-url=$ENDPOINT events create-event-bus \
    --name bdp-compact-events \
    --region $REGION \
    2>/dev/null || echo "Event bus bdp-compact-events already exists"

# Create rule for cost drift events
aws --endpoint-url=$ENDPOINT events put-rule \
    --name bdp-compact-cost-drift-rule \
    --event-bus-name bdp-compact-events \
    --event-pattern '{
        "source": ["cd1-agent.bdp-compact"],
        "detail-type": ["Cost Drift Detected", "Cost Drift Batch Detected"]
    }' \
    --state ENABLED \
    --region $REGION \
    2>/dev/null || echo "Rule already exists"

echo "EventBridge setup completed!"

# List event buses
aws --endpoint-url=$ENDPOINT events list-event-buses --region $REGION
