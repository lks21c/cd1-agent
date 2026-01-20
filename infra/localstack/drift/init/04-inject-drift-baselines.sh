#!/bin/bash
# ============================================================================
# Drift Agent - Baseline Configuration Injection Script
# ============================================================================
#
# Injects baseline configurations into DynamoDB for drift testing.
# These baselines represent the "expected" state that will be compared
# against "current" configurations (which may have drifted).
#
# Supported resources:
#   - EKS: production-eks cluster
#   - MSK: production-kafka cluster
#   - S3: company-data-lake-prod bucket
#   - EMR: j-XXXXX cluster
#   - MWAA: bdp-airflow-prod environment
#
# Usage:
#   LOCALSTACK_ENDPOINT=http://localhost:4566 ./04-inject-drift-baselines.sh
#
# ============================================================================

set -e

ENDPOINT=${LOCALSTACK_ENDPOINT:-http://localhost:4566}
REGION=${AWS_REGION:-ap-northeast-2}
TABLE_NAME=${DRIFT_BASELINE_TABLE:-drift-baseline-configs}
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Injecting Drift Agent baseline configurations..."
echo "Endpoint: $ENDPOINT"
echo "Region: $REGION"
echo "Table: $TABLE_NAME"
echo "Timestamp: $TIMESTAMP"

# Helper function to put baseline item
put_baseline() {
    local resource_type=$1
    local resource_id=$2
    local config=$3

    # Compute simple hash (first 12 chars of md5)
    local config_hash=$(echo -n "$config" | md5sum | cut -c1-12)

    local item=$(cat <<EOF
{
    "pk": {"S": "RESOURCE#${resource_type}#${resource_id}"},
    "sk": {"S": "VERSION#${TIMESTAMP}"},
    "resource_type": {"S": "${resource_type}"},
    "resource_id": {"S": "${resource_id}"},
    "config": {"S": $(echo "$config" | jq -c '.' | jq -Rs '.')},
    "config_hash": {"S": "${config_hash}"},
    "timestamp": {"S": "${TIMESTAMP}"},
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

    echo "  - $resource_type/$resource_id (hash: $config_hash)"
}

# ----------------------------------------------------------------------------
# EKS Baseline: production-eks
# ----------------------------------------------------------------------------
echo ""
echo "Injecting EKS baseline..."

EKS_CONFIG=$(cat <<'EOF'
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
            "instance_types": ["m6i.xlarge", "m6i.2xlarge"],
            "scaling_config": {
                "min_size": 3,
                "max_size": 10,
                "desired_size": 5
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

put_baseline "eks" "production-eks" "$EKS_CONFIG"

# Also inject into current-configs (no drift initially)
CURRENT_TABLE=${DRIFT_CURRENT_TABLE:-drift-current-configs}
CURRENT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

inject_current_config() {
    local resource_type=$1
    local resource_id=$2
    local config=$3
    local resource_arn=$4

    local item=$(cat <<EOF
{
    "pk": {"S": "RESOURCE#${resource_type}#${resource_id}"},
    "sk": {"S": "FETCH#${CURRENT_TIMESTAMP}"},
    "resource_type": {"S": "${resource_type}"},
    "resource_id": {"S": "${resource_id}"},
    "resource_arn": {"S": "${resource_arn}"},
    "config": {"S": $(echo "$config" | jq -c '.' | jq -Rs '.')},
    "fetched_at": {"S": "${CURRENT_TIMESTAMP}"},
    "is_latest": {"BOOL": true}
}
EOF
)

    aws dynamodb put-item \
        --endpoint-url "$ENDPOINT" \
        --region "$REGION" \
        --table-name "$CURRENT_TABLE" \
        --item "$item" \
        --no-cli-pager 2>/dev/null
}

# Inject EKS current config (same as baseline - no drift)
inject_current_config "eks" "production-eks" "$EKS_CONFIG" \
    "arn:aws:eks:ap-northeast-2:123456789012:cluster/production-eks"

# ----------------------------------------------------------------------------
# MSK Baseline: production-kafka
# ----------------------------------------------------------------------------
echo ""
echo "Injecting MSK baseline..."

MSK_CONFIG=$(cat <<'EOF'
{
    "cluster_name": "production-kafka",
    "kafka_version": "3.5.1",
    "broker_config": {
        "instance_type": "kafka.m5.large",
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

put_baseline "msk" "production-kafka" "$MSK_CONFIG"
inject_current_config "msk" "production-kafka" "$MSK_CONFIG" \
    "arn:aws:kafka:ap-northeast-2:123456789012:cluster/production-kafka/abc123"

# ----------------------------------------------------------------------------
# S3 Baseline: company-data-lake-prod
# ----------------------------------------------------------------------------
echo ""
echo "Injecting S3 baseline..."

S3_CONFIG=$(cat <<'EOF'
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
        "block_public_acls": true,
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

put_baseline "s3" "company-data-lake-prod" "$S3_CONFIG"
inject_current_config "s3" "company-data-lake-prod" "$S3_CONFIG" \
    "arn:aws:s3:::company-data-lake-prod"

# ----------------------------------------------------------------------------
# EMR Baseline: j-XXXXX
# ----------------------------------------------------------------------------
echo ""
echo "Injecting EMR baseline..."

EMR_CONFIG=$(cat <<'EOF'
{
    "cluster_name": "analytics-emr-prod",
    "release_label": "emr-7.0.0",
    "applications": ["Spark", "Hadoop", "Hive"],
    "instance_groups": {
        "master": {
            "instance_type": "m5.xlarge",
            "instance_count": 1
        },
        "core": {
            "instance_type": "r5.2xlarge",
            "instance_count": 4
        }
    },
    "tags": {
        "Environment": "production"
    }
}
EOF
)

put_baseline "emr" "j-XXXXX" "$EMR_CONFIG"
inject_current_config "emr" "j-XXXXX" "$EMR_CONFIG" \
    "arn:aws:elasticmapreduce:ap-northeast-2:123456789012:cluster/j-XXXXX"

# ----------------------------------------------------------------------------
# MWAA Baseline: bdp-airflow-prod
# ----------------------------------------------------------------------------
echo ""
echo "Injecting MWAA baseline..."

MWAA_CONFIG=$(cat <<'EOF'
{
    "environment_name": "bdp-airflow-prod",
    "airflow_version": "2.8.1",
    "environment_class": "mw1.medium",
    "min_workers": 2,
    "max_workers": 10,
    "schedulers": 2,
    "webserver_access_mode": "PRIVATE_ONLY",
    "tags": {
        "Environment": "production"
    }
}
EOF
)

put_baseline "mwaa" "bdp-airflow-prod" "$MWAA_CONFIG"
inject_current_config "mwaa" "bdp-airflow-prod" "$MWAA_CONFIG" \
    "arn:aws:airflow:ap-northeast-2:123456789012:environment/bdp-airflow-prod"

# ----------------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------------
echo ""
echo "Baseline injection complete!"
echo ""
echo "Baselines in $TABLE_NAME:"
aws dynamodb scan \
    --endpoint-url "$ENDPOINT" \
    --region "$REGION" \
    --table-name "$TABLE_NAME" \
    --projection-expression "pk, resource_type, resource_id, config_hash" \
    --no-cli-pager 2>/dev/null | \
    jq -r '.Items[] | "  - \(.resource_type.S)/\(.resource_id.S) (hash: \(.config_hash.S))"' || true

echo ""
echo "Current configs in $CURRENT_TABLE:"
aws dynamodb scan \
    --endpoint-url "$ENDPOINT" \
    --region "$REGION" \
    --table-name "$CURRENT_TABLE" \
    --select COUNT \
    --no-cli-pager 2>/dev/null | \
    jq -r '"  Total items: \(.Count)"' || true
