# BDP Compact Agent - Lambda 배포

## Lambda Layer 빌드

```bash
# Standalone Wheel + Lambda Layer 빌드
./scripts/build-bdp-cost.sh

# 출력 파일:
# - dist/bdp_cost/bdp_cost-1.0.0-py3-none-any.whl
# - dist/bdp_cost/lambda-layer.zip
```

## Lambda 설정

| 속성 | 값 |
|------|-----|
| **Runtime** | Python 3.12 |
| **Architecture** | ARM64 (Graviton2) |
| **Memory** | 512MB |
| **Timeout** | 120s |
| **Handler** | `bdp_cost.handler.handler` |
| **Layer** | `dist/bdp_cost/lambda-layer.zip` |

## Lambda 배포 (AWS CLI)

### 1. Layer 업로드

```bash
aws lambda publish-layer-version \
  --layer-name bdp-cost-deps \
  --zip-file fileb://dist/bdp_cost/lambda-layer.zip \
  --compatible-runtimes python3.12 \
  --compatible-architectures arm64
```

### 2. Lambda 함수 생성

```bash
aws lambda create-function \
  --function-name bdp-cost-agent \
  --runtime python3.12 \
  --architectures arm64 \
  --handler bdp_cost.handler.handler \
  --role arn:aws:iam::111111111111:role/bdp-cost-execution-role \
  --zip-file fileb://dist/bdp_cost/bdp_cost-1.0.0-py3-none-any.whl \
  --timeout 120 \
  --memory-size 512 \
  --layers arn:aws:lambda:ap-northeast-2:111111111111:layer:bdp-cost-deps:1 \
  --environment "Variables={BDP_PROVIDER=real,BDP_ACCOUNT_NAME=my-account,BDP_SENSITIVITY=0.7}"
```

### 3. Lambda 함수 업데이트

```bash
aws lambda update-function-code \
  --function-name bdp-cost-agent \
  --zip-file fileb://dist/bdp_cost/bdp_cost-1.0.0-py3-none-any.whl
```

## IAM Role 설정

### Execution Role Trust Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### Execution Role Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "events:PutEvents"
      ],
      "Resource": "arn:aws:events:*:*:event-bus/cd1-agent-events"
    }
  ]
}
```

## EventBridge 스케줄 설정

매일 오전 9시(KST)에 실행:

```bash
aws events put-rule \
  --name bdp-cost-daily \
  --schedule-expression "cron(0 0 * * ? *)" \
  --state ENABLED

aws events put-targets \
  --rule bdp-cost-daily \
  --targets "Id"="1","Arn"="arn:aws:lambda:ap-northeast-2:111111111111:function:bdp-cost-agent"
```

## Lambda 호출 테스트

```bash
aws lambda invoke \
  --function-name bdp-cost-agent \
  --payload '{"days": 14, "min_cost_threshold": 10000}' \
  --cli-binary-format raw-in-base64-out \
  response.json

cat response.json
```

## CloudFormation/SAM 템플릿

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  BDPCostFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: bdp-cost-agent
      Runtime: python3.12
      Architectures:
        - arm64
      Handler: bdp_cost.handler.handler
      CodeUri: dist/bdp_cost/
      MemorySize: 512
      Timeout: 120
      Layers:
        - !Ref BDPCostDepsLayer
      Environment:
        Variables:
          BDP_PROVIDER: real
          BDP_ACCOUNT_NAME: !Ref AccountName
          BDP_SENSITIVITY: "0.7"
          BDP_PATTERN_RECOGNITION: "true"
      Policies:
        - Statement:
            - Effect: Allow
              Action:
                - ce:GetCostAndUsage
                - ce:GetCostForecast
              Resource: "*"
            - Effect: Allow
              Action:
                - events:PutEvents
              Resource: !Sub "arn:aws:events:${AWS::Region}:${AWS::AccountId}:event-bus/cd1-agent-events"
      Events:
        DailySchedule:
          Type: Schedule
          Properties:
            Schedule: cron(0 0 * * ? *)
            Enabled: true

  BDPCostDepsLayer:
    Type: AWS::Serverless::LayerVersion
    Properties:
      LayerName: bdp-cost-deps
      ContentUri: dist/bdp_cost/lambda-layer.zip
      CompatibleRuntimes:
        - python3.12
      CompatibleArchitectures:
        - arm64

Parameters:
  AccountName:
    Type: String
    Default: my-account
```
