#!/bin/bash
# Inject baseline cost data for BDP Compact Agent testing

set -e

ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
REGION="${AWS_REGION:-ap-northeast-2}"
TABLE_NAME="bdp-cost-history"
DAYS="${BDP_BASELINE_DAYS:-14}"

echo "Injecting baseline cost data for $DAYS days..."

# Account configurations
declare -A ACCOUNTS
ACCOUNTS["111111111111"]="hyundaicard-payer"
ACCOUNTS["222222222222"]="hyundaicard-member"

# Service configurations: service_name base_cost_krw variance_pct
SERVICES=(
    "Amazon Athena:250000:15"
    "AWS Lambda:80000:10"
    "Amazon S3:120000:8"
    "Amazon EC2:500000:12"
    "Amazon DynamoDB:90000:10"
    "Amazon RDS:350000:7"
    "AWS CloudWatch:30000:20"
    "Amazon API Gateway:60000:15"
)

# Generate dates
END_DATE=$(date +%Y-%m-%d)

for ACCOUNT_ID in "${!ACCOUNTS[@]}"; do
    ACCOUNT_NAME="${ACCOUNTS[$ACCOUNT_ID]}"
    echo "Injecting data for account: $ACCOUNT_NAME ($ACCOUNT_ID)"

    for SERVICE_CONFIG in "${SERVICES[@]}"; do
        IFS=':' read -r SERVICE_NAME BASE_COST VARIANCE_PCT <<< "$SERVICE_CONFIG"

        for ((DAY=0; DAY<DAYS; DAY++)); do
            DATE=$(date -v-${DAY}d +%Y-%m-%d 2>/dev/null || date -d "$DAY days ago" +%Y-%m-%d)

            # Calculate cost with variance
            VARIANCE=$(echo "scale=0; $BASE_COST * $VARIANCE_PCT / 100" | bc)
            RANDOM_VAR=$((RANDOM % (2 * VARIANCE + 1) - VARIANCE))
            COST=$((BASE_COST + RANDOM_VAR))

            # Create DynamoDB item
            aws --endpoint-url=$ENDPOINT dynamodb put-item \
                --table-name $TABLE_NAME \
                --item "{
                    \"pk\": {\"S\": \"ACCOUNT#${ACCOUNT_ID}#SERVICE#${SERVICE_NAME}\"},
                    \"sk\": {\"S\": \"DATE#${DATE}\"},
                    \"account_id\": {\"S\": \"${ACCOUNT_ID}\"},
                    \"account_name\": {\"S\": \"${ACCOUNT_NAME}\"},
                    \"service_name\": {\"S\": \"${SERVICE_NAME}\"},
                    \"cost\": {\"N\": \"${COST}\"},
                    \"currency\": {\"S\": \"KRW\"},
                    \"timestamp\": {\"S\": \"${DATE}T23:59:59Z\"}
                }" \
                --region $REGION \
                2>/dev/null
        done
        echo "  - $SERVICE_NAME: baseline data injected"
    done
done

echo "Baseline data injection completed!"

# Show sample data
echo ""
echo "Sample data:"
aws --endpoint-url=$ENDPOINT dynamodb scan \
    --table-name $TABLE_NAME \
    --limit 5 \
    --region $REGION
