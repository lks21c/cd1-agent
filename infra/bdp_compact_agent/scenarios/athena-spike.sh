#!/bin/bash
# Inject Athena cost spike scenario

set -e

ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
REGION="${AWS_REGION:-ap-northeast-2}"
TABLE_NAME="bdp-cost-history"

echo "Injecting Athena cost spike scenario..."

TODAY=$(date +%Y-%m-%d)
ACCOUNT_ID="111111111111"
ACCOUNT_NAME="hyundaicard-payer"
SERVICE_NAME="Amazon Athena"

# Spike: 일평균 25만원 → 58만원 (132% 상승)
# 3일 연속 상승
for ((DAY=0; DAY<3; DAY++)); do
    DATE=$(date -v-${DAY}d +%Y-%m-%d 2>/dev/null || date -d "$DAY days ago" +%Y-%m-%d)

    # 상승 패턴: 오늘 58만, 어제 45만, 그저께 35만
    case $DAY in
        0) COST=580000 ;;
        1) COST=450000 ;;
        2) COST=350000 ;;
    esac

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
            \"timestamp\": {\"S\": \"${DATE}T23:59:59Z\"},
            \"scenario\": {\"S\": \"athena-spike\"},
            \"is_spike\": {\"BOOL\": true}
        }" \
        --region $REGION

    echo "  Injected: $DATE - $COST KRW"
done

echo ""
echo "Athena spike scenario injected!"
echo "Expected detection:"
echo "  - Service: Amazon Athena"
echo "  - Account: hyundaicard-payer"
echo "  - Severity: HIGH or CRITICAL"
echo "  - Change: ~132% 상승"
echo "  - Spike duration: 3일"
echo ""
echo "Run detection:"
echo "  curl -X POST http://localhost:8005/api/v1/detect -H 'Content-Type: application/json' -d '{\"days\": 14}'"
