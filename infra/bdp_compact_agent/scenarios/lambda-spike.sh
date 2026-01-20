#!/bin/bash
# Inject Lambda cost spike scenario

set -e

ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
REGION="${AWS_REGION:-ap-northeast-2}"
TABLE_NAME="bdp-cost-history"

echo "Injecting Lambda cost spike scenario..."

TODAY=$(date +%Y-%m-%d)
ACCOUNT_ID="222222222222"
ACCOUNT_NAME="hyundaicard-member"
SERVICE_NAME="AWS Lambda"

# Spike: 일평균 8만원 → 40만원 (400% 상승)
# 갑작스러운 1일 스파이크
COST=400000

aws --endpoint-url=$ENDPOINT dynamodb put-item \
    --table-name $TABLE_NAME \
    --item "{
        \"pk\": {\"S\": \"ACCOUNT#${ACCOUNT_ID}#SERVICE#${SERVICE_NAME}\"},
        \"sk\": {\"S\": \"DATE#${TODAY}\"},
        \"account_id\": {\"S\": \"${ACCOUNT_ID}\"},
        \"account_name\": {\"S\": \"${ACCOUNT_NAME}\"},
        \"service_name\": {\"S\": \"${SERVICE_NAME}\"},
        \"cost\": {\"N\": \"${COST}\"},
        \"currency\": {\"S\": \"KRW\"},
        \"timestamp\": {\"S\": \"${TODAY}T23:59:59Z\"},
        \"scenario\": {\"S\": \"lambda-spike\"},
        \"is_spike\": {\"BOOL\": true}
    }" \
    --region $REGION

echo "Lambda spike scenario injected!"
echo ""
echo "Expected detection:"
echo "  - Service: AWS Lambda"
echo "  - Account: hyundaicard-member"
echo "  - Severity: CRITICAL"
echo "  - Change: ~400% 상승"
echo "  - Spike duration: 1일"
echo ""
echo "Run detection:"
echo "  curl -X POST http://localhost:8005/api/v1/detect -H 'Content-Type: application/json' -d '{\"days\": 14}'"
