#!/bin/bash
# Inject multi-account cost drift scenario

set -e

ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
REGION="${AWS_REGION:-ap-northeast-2}"
TABLE_NAME="bdp-cost-history"

echo "Injecting multi-account cost drift scenario..."

TODAY=$(date +%Y-%m-%d)

# Account 1: hyundaicard-payer - EC2 spike
echo "Account 1: EC2 spike (payer account)"
aws --endpoint-url=$ENDPOINT dynamodb put-item \
    --table-name $TABLE_NAME \
    --item "{
        \"pk\": {\"S\": \"ACCOUNT#111111111111#SERVICE#Amazon EC2\"},
        \"sk\": {\"S\": \"DATE#${TODAY}\"},
        \"account_id\": {\"S\": \"111111111111\"},
        \"account_name\": {\"S\": \"hyundaicard-payer\"},
        \"service_name\": {\"S\": \"Amazon EC2\"},
        \"cost\": {\"N\": \"1500000\"},
        \"currency\": {\"S\": \"KRW\"},
        \"timestamp\": {\"S\": \"${TODAY}T23:59:59Z\"},
        \"scenario\": {\"S\": \"multi-account-drift\"},
        \"is_spike\": {\"BOOL\": true}
    }" \
    --region $REGION

# Account 1: RDS gradual increase
echo "Account 1: RDS gradual increase"
for ((DAY=0; DAY<5; DAY++)); do
    DATE=$(date -v-${DAY}d +%Y-%m-%d 2>/dev/null || date -d "$DAY days ago" +%Y-%m-%d)
    COST=$((350000 + (4-DAY) * 50000))  # 550000 → 400000

    aws --endpoint-url=$ENDPOINT dynamodb put-item \
        --table-name $TABLE_NAME \
        --item "{
            \"pk\": {\"S\": \"ACCOUNT#111111111111#SERVICE#Amazon RDS\"},
            \"sk\": {\"S\": \"DATE#${DATE}\"},
            \"account_id\": {\"S\": \"111111111111\"},
            \"account_name\": {\"S\": \"hyundaicard-payer\"},
            \"service_name\": {\"S\": \"Amazon RDS\"},
            \"cost\": {\"N\": \"${COST}\"},
            \"currency\": {\"S\": \"KRW\"},
            \"timestamp\": {\"S\": \"${DATE}T23:59:59Z\"},
            \"scenario\": {\"S\": \"multi-account-drift\"}
        }" \
        --region $REGION
done

# Account 2: hyundaicard-member - S3 spike
echo "Account 2: S3 spike (member account)"
aws --endpoint-url=$ENDPOINT dynamodb put-item \
    --table-name $TABLE_NAME \
    --item "{
        \"pk\": {\"S\": \"ACCOUNT#222222222222#SERVICE#Amazon S3\"},
        \"sk\": {\"S\": \"DATE#${TODAY}\"},
        \"account_id\": {\"S\": \"222222222222\"},
        \"account_name\": {\"S\": \"hyundaicard-member\"},
        \"service_name\": {\"S\": \"Amazon S3\"},
        \"cost\": {\"N\": \"450000\"},
        \"currency\": {\"S\": \"KRW\"},
        \"timestamp\": {\"S\": \"${TODAY}T23:59:59Z\"},
        \"scenario\": {\"S\": \"multi-account-drift\"},
        \"is_spike\": {\"BOOL\": true}
    }" \
    --region $REGION

echo ""
echo "Multi-account drift scenario injected!"
echo ""
echo "Expected detections:"
echo "  1. EC2 (hyundaicard-payer): ~200% 상승 - HIGH/CRITICAL"
echo "  2. RDS (hyundaicard-payer): gradual increase - MEDIUM"
echo "  3. S3 (hyundaicard-member): ~275% 상승 - HIGH/CRITICAL"
echo ""
echo "Run detection:"
echo "  curl -X POST http://localhost:8005/api/v1/detect -H 'Content-Type: application/json' -d '{\"days\": 14}'"
