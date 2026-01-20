#!/bin/bash
# ============================================================================
# Drift Scenario: MSK Broker Configuration Drift
# ============================================================================
#
# Simulates drift in MSK (Kafka) cluster configuration:
#   - Broker instance type downgrade (kafka.m5.large -> kafka.t3.small)
#
# Expected severity: HIGH (performance impact)
#
# Usage:
#   LOCALSTACK_ENDPOINT=http://localhost:4566 ./msk-broker-drift.sh
#
# ============================================================================

set -e

ENDPOINT=${LOCALSTACK_ENDPOINT:-http://localhost:4566}
REGION=${AWS_REGION:-ap-northeast-2}
TABLE_NAME=${DRIFT_CURRENT_TABLE:-drift-current-configs}
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Injecting MSK broker drift scenario..."
echo "Endpoint: $ENDPOINT"
echo "Table: $TABLE_NAME"

# Drifted MSK configuration
# - instance_type: kafka.m5.large -> kafka.t3.small (significant downgrade)
DRIFTED_CONFIG=$(cat <<'EOF'
{
    "cluster_name": "production-kafka",
    "kafka_version": "3.5.1",
    "broker_config": {
        "instance_type": "kafka.t3.small",
        "number_of_broker_nodes": 3,
        "storage_info": {
            "ebs_storage_info": {
                "volume_size": 1000,
                "provisioned_throughput": {
                    "enabled": true,
                    "volume_throughput": 250
                }
            }
        }
    },
    "encryption_info": {
        "encryption_at_rest": true,
        "encryption_in_transit": "TLS"
    },
    "enhanced_monitoring": "PER_TOPIC_PER_BROKER",
    "tags": {
        "Environment": "production"
    }
}
EOF
)

# Build DynamoDB item
ITEM=$(cat <<EOF
{
    "pk": {"S": "RESOURCE#msk#production-kafka"},
    "sk": {"S": "FETCH#${TIMESTAMP}"},
    "resource_type": {"S": "msk"},
    "resource_id": {"S": "production-kafka"},
    "resource_arn": {"S": "arn:aws:kafka:ap-northeast-2:123456789012:cluster/production-kafka/abc123"},
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
echo "MSK broker drift scenario injected successfully!"
echo ""
echo "Drift details:"
echo "  - Resource: msk/production-kafka"
echo "  - Drift: broker instance_type changed from kafka.m5.large to kafka.t3.small"
echo "  - Impact: Significant performance degradation expected"
echo "  - Expected severity: HIGH"
