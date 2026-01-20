#!/bin/bash
# ============================================================================
# Drift Scenario: EKS Cluster Configuration Drift
# ============================================================================
#
# Simulates drift in EKS cluster configuration:
#   - Instance type downgrade (m6i.xlarge -> m5.large)
#   - Desired node count reduction (5 -> 3)
#
# Expected severity: HIGH
#
# Usage:
#   LOCALSTACK_ENDPOINT=http://localhost:4566 ./eks-cluster-drift.sh
#
# ============================================================================

set -e

ENDPOINT=${LOCALSTACK_ENDPOINT:-http://localhost:4566}
REGION=${AWS_REGION:-ap-northeast-2}
TABLE_NAME=${DRIFT_CURRENT_TABLE:-drift-current-configs}
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Injecting EKS cluster drift scenario..."
echo "Endpoint: $ENDPOINT"
echo "Table: $TABLE_NAME"

# Drifted EKS configuration
# - instance_types: m6i.xlarge -> m5.large (downgrade)
# - desired_size: 5 -> 3 (scale down)
DRIFTED_CONFIG=$(cat <<'EOF'
{
    "cluster_name": "production-eks",
    "version": "1.29",
    "endpoint_public_access": false,
    "endpoint_private_access": true,
    "logging": {
        "api": true,
        "audit": true,
        "authenticator": true,
        "controllerManager": true,
        "scheduler": true
    },
    "node_groups": [
        {
            "name": "general-workload",
            "instance_types": ["m5.large"],
            "scaling_config": {
                "min_size": 3,
                "max_size": 10,
                "desired_size": 3
            },
            "disk_size": 100,
            "ami_type": "AL2_x86_64",
            "capacity_type": "ON_DEMAND"
        }
    ],
    "tags": {
        "Environment": "production",
        "ManagedBy": "cd1-agent"
    }
}
EOF
)

# Build DynamoDB item
ITEM=$(cat <<EOF
{
    "pk": {"S": "RESOURCE#eks#production-eks"},
    "sk": {"S": "FETCH#${TIMESTAMP}"},
    "resource_type": {"S": "eks"},
    "resource_id": {"S": "production-eks"},
    "resource_arn": {"S": "arn:aws:eks:ap-northeast-2:123456789012:cluster/production-eks"},
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
echo "EKS drift scenario injected successfully!"
echo ""
echo "Drift details:"
echo "  - Resource: eks/production-eks"
echo "  - Drift 1: instance_types changed from [m6i.xlarge, m6i.2xlarge] to [m5.large]"
echo "  - Drift 2: desired_size changed from 5 to 3"
echo "  - Expected severity: HIGH"
