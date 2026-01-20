#!/bin/bash
# Inject baseline cost data for Cost Agent testing
# Generates 30 days of historical cost data for 7 AWS services
#
# Services and daily baseline costs:
#   - AWS Lambda: $50-70 (±20%)
#   - Amazon EC2: $180-220 (±10%)
#   - Amazon RDS: $140-160 (±7%)
#   - Amazon S3: $25-35 (±17%)
#   - Amazon DynamoDB: $70-90 (±13%)
#   - AWS CloudWatch: $15-25 (±25%)
#   - Amazon API Gateway: $30-50 (±25%)
#
# Usage:
#   ./04-inject-cost-baseline.sh
#   # or via make: make cost-baseline

set -e

echo "=== Injecting Cost Baseline Data ==="

REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
TABLE_NAME="cost-service-history"
DAYS="${COST_BASELINE_DAYS:-30}"

export AWS_ENDPOINT_URL="$ENDPOINT"
export AWS_DEFAULT_REGION="$REGION"

# Service configurations: name|base_cost|variance_percent
declare -a SERVICES=(
    "AWS Lambda|60|20"
    "Amazon EC2|200|10"
    "Amazon RDS|150|7"
    "Amazon S3|30|17"
    "Amazon DynamoDB|80|13"
    "AWS CloudWatch|20|25"
    "Amazon API Gateway|40|25"
)

# Function to generate cost with variance
generate_cost() {
    local base=$1
    local variance_pct=$2
    local day_seed=$3

    # Deterministic random based on seed for reproducibility
    local variance_range=$((base * variance_pct / 100))
    local random_offset=$(( (day_seed * 17 + 31) % (variance_range * 2 + 1) - variance_range ))
    local cost=$((base + random_offset))

    # Add decimal part
    local decimal=$((day_seed % 100))
    echo "$cost.$decimal"
}

# Function to generate usage quantity based on service type
generate_usage() {
    local service=$1
    local cost=$2

    case "$service" in
        "AWS Lambda")
            # Invocations: cost * 100000 (roughly $0.20 per 1M requests)
            echo "$((${cost%.*} * 500000))"
            ;;
        "Amazon EC2")
            # Hours: cost / 0.10 (roughly $0.10/hour average)
            echo "$((${cost%.*} * 10))"
            ;;
        "Amazon RDS")
            # Hours: cost / 0.15 (roughly $0.15/hour average)
            echo "$((${cost%.*} * 7))"
            ;;
        "Amazon S3")
            # GB: cost / 0.023 (roughly $0.023/GB)
            echo "$((${cost%.*} * 43))"
            ;;
        "Amazon DynamoDB")
            # RCU: cost * 1000
            echo "$((${cost%.*} * 1000))"
            ;;
        "AWS CloudWatch")
            # Metrics: cost * 100
            echo "$((${cost%.*} * 100))"
            ;;
        "Amazon API Gateway")
            # Requests: cost * 300000 (roughly $3.50 per 1M)
            echo "$((${cost%.*} * 300000))"
            ;;
        *)
            echo "$((${cost%.*} * 100))"
            ;;
    esac
}

# Get current timestamp
NOW=$(date -u +%s)
INJECT_COUNT=0

echo "Injecting $DAYS days of cost data for ${#SERVICES[@]} services..."

for service_config in "${SERVICES[@]}"; do
    IFS='|' read -r service_name base_cost variance_pct <<< "$service_config"

    echo ""
    echo "Processing: $service_name (base: \$$base_cost, variance: ±$variance_pct%)"

    for day in $(seq 0 $((DAYS - 1))); do
        # Calculate date
        TIMESTAMP=$((NOW - day * 86400))

        # Use date command compatible with both macOS and Linux
        if [[ "$OSTYPE" == "darwin"* ]]; then
            DATE_STR=$(date -u -r $TIMESTAMP +%Y-%m-%d)
            FULL_TIMESTAMP=$(date -u -r $TIMESTAMP +%Y-%m-%dT23:59:59Z)
        else
            DATE_STR=$(date -u -d @$TIMESTAMP +%Y-%m-%d)
            FULL_TIMESTAMP=$(date -u -d @$TIMESTAMP +%Y-%m-%dT23:59:59Z)
        fi

        # Generate cost with variance
        DAY_SEED=$((TIMESTAMP / 86400 + ${#service_name}))
        COST=$(generate_cost $base_cost $variance_pct $DAY_SEED)
        USAGE=$(generate_usage "$service_name" "$COST")

        # Insert into DynamoDB
        awslocal dynamodb put-item \
            --table-name "$TABLE_NAME" \
            --item '{
                "pk": {"S": "SERVICE#'"$service_name"'"},
                "sk": {"S": "DATE#'"$DATE_STR"'"},
                "service_name": {"S": "'"$service_name"'"},
                "cost": {"N": "'"$COST"'"},
                "usage_quantity": {"N": "'"$USAGE"'"},
                "region": {"S": "'"$REGION"'"},
                "timestamp": {"S": "'"$FULL_TIMESTAMP"'"},
                "currency": {"S": "USD"}
            }' \
            --region "$REGION" 2>/dev/null

        INJECT_COUNT=$((INJECT_COUNT + 1))
    done

    echo "  Injected $DAYS records for $service_name"
done

echo ""
echo "=== Cost Baseline Data Injection Complete ==="
echo "Total records injected: $INJECT_COUNT"
echo ""
echo "Verify with:"
echo "  awslocal dynamodb scan --table-name $TABLE_NAME --select COUNT"
echo "  awslocal dynamodb query --table-name $TABLE_NAME --key-condition-expression 'pk = :pk' --expression-attribute-values '{\":pk\": {\"S\": \"SERVICE#AWS Lambda\"}}'"
