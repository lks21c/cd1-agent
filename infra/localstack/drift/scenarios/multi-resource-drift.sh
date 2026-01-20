#!/bin/bash
# ============================================================================
# Drift Scenario: Multi-Resource Simultaneous Drift
# ============================================================================
#
# Simulates simultaneous drift across multiple resources:
#   - EKS: Instance type downgrade + scale down
#   - S3: Public access block disabled (CRITICAL)
#   - MWAA: Worker capacity reduced
#
# This scenario tests batch drift detection capability.
#
# Expected severities: CRITICAL (S3), HIGH (EKS), MEDIUM (MWAA)
#
# Usage:
#   LOCALSTACK_ENDPOINT=http://localhost:4566 ./multi-resource-drift.sh
#
# ============================================================================

set -e

ENDPOINT=${LOCALSTACK_ENDPOINT:-http://localhost:4566}
REGION=${AWS_REGION:-ap-northeast-2}
TABLE_NAME=${DRIFT_CURRENT_TABLE:-drift-current-configs}
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Injecting multi-resource drift scenario..."
echo "Endpoint: $ENDPOINT"
echo "Table: $TABLE_NAME"

# Helper function to put config
put_drifted_config() {
    local resource_type=$1
    local resource_id=$2
    local resource_arn=$3
    local config=$4

    local item=$(cat <<EOF
{
    "pk": {"S": "RESOURCE#${resource_type}#${resource_id}"},
    "sk": {"S": "FETCH#${TIMESTAMP}"},
    "resource_type": {"S": "${resource_type}"},
    "resource_id": {"S": "${resource_id}"},
    "resource_arn": {"S": "${resource_arn}"},
    "config": {"S": $(echo "$config" | jq -c '.' | jq -Rs '.')},
    "fetched_at": {"S": "${TIMESTAMP}"},
    "is_latest": {"BOOL": true}
}
EOF
)

    aws dynamodb put-item \
        --endpoint-url "$ENDPOINT" \
        --region "$REGION" \
        --table-name "$TABLE_NAME" \
        --item "$item" \
        --no-cli-pager 2>/dev/null

    echo "  - $resource_type/$resource_id"
}

# ============================================================================
# EKS Drift (HIGH)
# ============================================================================
echo ""
echo "Injecting EKS drift..."

EKS_DRIFTED=$(cat <<'EOF'
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

put_drifted_config "eks" "production-eks" \
    "arn:aws:eks:ap-northeast-2:123456789012:cluster/production-eks" \
    "$EKS_DRIFTED"

# ============================================================================
# S3 Drift (CRITICAL)
# ============================================================================
echo ""
echo "Injecting S3 security drift..."

S3_DRIFTED=$(cat <<'EOF'
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

put_drifted_config "s3" "company-data-lake-prod" \
    "arn:aws:s3:::company-data-lake-prod" \
    "$S3_DRIFTED"

# ============================================================================
# MWAA Drift (MEDIUM)
# ============================================================================
echo ""
echo "Injecting MWAA drift..."

MWAA_DRIFTED=$(cat <<'EOF'
{
    "environment_name": "bdp-airflow-prod",
    "airflow_version": "2.8.1",
    "environment_class": "mw1.medium",
    "min_workers": 1,
    "max_workers": 5,
    "schedulers": 2,
    "webserver_access_mode": "PRIVATE_ONLY",
    "tags": {
        "Environment": "production"
    }
}
EOF
)

put_drifted_config "mwaa" "bdp-airflow-prod" \
    "arn:aws:airflow:ap-northeast-2:123456789012:environment/bdp-airflow-prod" \
    "$MWAA_DRIFTED"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "Multi-resource drift scenario injected successfully!"
echo ""
echo "Drift summary:"
echo "  - EKS/production-eks: Instance downgrade + scale down (HIGH)"
echo "  - S3/company-data-lake-prod: Public access block disabled (CRITICAL)"
echo "  - MWAA/bdp-airflow-prod: Worker capacity reduced (MEDIUM)"
echo ""
echo "Expected detection:"
echo "  - Total drifts: 3 resources"
echo "  - Severity breakdown: 1 CRITICAL, 1 HIGH, 1 MEDIUM"
