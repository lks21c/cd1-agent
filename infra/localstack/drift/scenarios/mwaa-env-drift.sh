#!/bin/bash
# ============================================================================
# Drift Scenario: MWAA Environment Configuration Drift
# ============================================================================
#
# Simulates drift in MWAA (Airflow) environment configuration:
#   - min_workers: 2 -> 1 (reduced capacity)
#   - max_workers: 10 -> 5 (capacity limit reduced)
#
# Expected severity: MEDIUM
#
# Usage:
#   LOCALSTACK_ENDPOINT=http://localhost:4566 ./mwaa-env-drift.sh
#
# ============================================================================

set -e

ENDPOINT=${LOCALSTACK_ENDPOINT:-http://localhost:4566}
REGION=${AWS_REGION:-ap-northeast-2}
TABLE_NAME=${DRIFT_CURRENT_TABLE:-drift-current-configs}
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Injecting MWAA environment drift scenario..."
echo "Endpoint: $ENDPOINT"
echo "Table: $TABLE_NAME"

# Drifted MWAA configuration
# - min_workers: 2 -> 1
# - max_workers: 10 -> 5
DRIFTED_CONFIG=$(cat <<'EOF'
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

# Build DynamoDB item
ITEM=$(cat <<EOF
{
    "pk": {"S": "RESOURCE#mwaa#bdp-airflow-prod"},
    "sk": {"S": "FETCH#${TIMESTAMP}"},
    "resource_type": {"S": "mwaa"},
    "resource_id": {"S": "bdp-airflow-prod"},
    "resource_arn": {"S": "arn:aws:airflow:ap-northeast-2:123456789012:environment/bdp-airflow-prod"},
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
echo "MWAA environment drift scenario injected successfully!"
echo ""
echo "Drift details:"
echo "  - Resource: mwaa/bdp-airflow-prod"
echo "  - Drift 1: min_workers changed from 2 to 1"
echo "  - Drift 2: max_workers changed from 10 to 5"
echo "  - Impact: Reduced DAG processing capacity"
echo "  - Expected severity: MEDIUM"
