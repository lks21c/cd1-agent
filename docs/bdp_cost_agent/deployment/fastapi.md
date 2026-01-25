# BDP Compact Agent - FastAPI 서버

## API 엔드포인트

### 탐지 관련

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/api/v1/detect` | 비용 드리프트 탐지 실행 |
| `GET` | `/api/v1/status` | 에이전트 상태 조회 |
| `GET` | `/api/v1/account` | 현재 계정 정보 조회 |

### HITL 관련

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v1/hitl/pending` | 대기 중인 HITL 요청 조회 |
| `POST` | `/api/v1/hitl/{request_id}/respond` | HITL 요청 응답 |

## 서버 실행

### 개발 모드

```bash
# 직접 실행
python -m src.agents.bdp_cost.server

# Uvicorn으로 실행 (auto-reload)
uvicorn src.agents.bdp_cost.server:app --port 8005 --reload
```

### 프로덕션 모드

```bash
uvicorn src.agents.bdp_cost.server:app --host 0.0.0.0 --port 8005 --workers 4
```

## API 사용 예시

### 탐지 요청

```bash
curl -X POST http://localhost:8005/api/v1/detect \
  -H "Content-Type: application/json" \
  -d '{
    "days": 14,
    "min_cost_threshold": 10000,
    "publish_alerts": true
  }'
```

### 탐지 응답

```json
{
  "detection_type": "cost_drift",
  "period_days": 14,
  "accounts_analyzed": 1,
  "services_analyzed": 10,
  "anomalies_detected": true,
  "total_anomalies": 5,
  "severity_breakdown": {
    "critical": 1,
    "high": 2,
    "medium": 1,
    "low": 1
  },
  "summary": "총 5건의 비용 이상이 탐지되었습니다...",
  "results": [
    {
      "service_name": "Amazon Athena",
      "account_id": "111111111111",
      "account_name": "bdp-prod",
      "severity": "critical",
      "confidence_score": 0.92,
      "raw_confidence_score": 0.95,
      "pattern_contexts": ["평일 평균 대비 정상 범위"],
      "current_cost": 580000,
      "historical_average": 250000,
      "change_percent": 132.0,
      "spike_duration_days": 3,
      "trend_direction": "increasing",
      "spike_start_date": "2024-01-12",
      "detection_method": "ensemble",
      "summary": "아테나(bdp-prod) 비용이..."
    }
  ],
  "hitl_request_id": "uuid-if-critical",
  "detection_timestamp": "2024-01-15T10:30:00Z"
}
```

### 상태 조회

```bash
curl http://localhost:8005/api/v1/status
```

```json
{
  "status": "healthy",
  "agent": "bdp-cost",
  "version": "1.0.0",
  "provider": "real",
  "sensitivity": 0.7,
  "pattern_recognition": true,
  "currency": "KRW"
}
```

### 계정 정보 조회

```bash
curl http://localhost:8005/api/v1/account
```

```json
{
  "account_id": "111111111111",
  "account_name": "bdp-prod"
}
```

## Docker 배포

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy wheel file
COPY dist/bdp_cost/bdp_cost-1.0.0-py3-none-any.whl .

# Install dependencies
RUN pip install --no-cache-dir bdp_cost-1.0.0-py3-none-any.whl

# Environment variables
ENV BDP_PROVIDER=real
ENV BDP_ACCOUNT_NAME=default
ENV BDP_SENSITIVITY=0.7
ENV BDP_PATTERN_RECOGNITION=true

# Expose port
EXPOSE 8005

# Run server
CMD ["uvicorn", "bdp_cost.server:app", "--host", "0.0.0.0", "--port", "8005"]
```

### Docker 빌드 및 실행

```bash
# 빌드
docker build -t bdp-cost-agent:latest .

# 실행
docker run -d \
  -p 8005:8005 \
  -e BDP_PROVIDER=real \
  -e BDP_ACCOUNT_NAME=my-account \
  -e AWS_ACCESS_KEY_ID=... \
  -e AWS_SECRET_ACCESS_KEY=... \
  --name bdp-cost \
  bdp-cost-agent:latest
```

### Docker Compose

```yaml
version: '3.8'

services:
  bdp-cost:
    build: .
    ports:
      - "8005:8005"
    environment:
      - BDP_PROVIDER=real
      - BDP_ACCOUNT_NAME=my-account
      - BDP_SENSITIVITY=0.7
      - BDP_PATTERN_RECOGNITION=true
      - AWS_REGION=ap-northeast-2
    volumes:
      - ~/.aws:/root/.aws:ro
    restart: unless-stopped
```

## Kubernetes 배포

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bdp-cost-agent
spec:
  replicas: 2
  selector:
    matchLabels:
      app: bdp-cost
  template:
    metadata:
      labels:
        app: bdp-cost
    spec:
      containers:
        - name: bdp-cost
          image: bdp-cost-agent:latest
          ports:
            - containerPort: 8005
          env:
            - name: BDP_PROVIDER
              value: "real"
            - name: BDP_ACCOUNT_NAME
              valueFrom:
                configMapKeyRef:
                  name: bdp-config
                  key: account_name
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /api/v1/status
              port: 8005
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /api/v1/status
              port: 8005
            initialDelaySeconds: 5
            periodSeconds: 10
```

### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: bdp-cost-service
spec:
  selector:
    app: bdp-cost
  ports:
    - protocol: TCP
      port: 8005
      targetPort: 8005
  type: ClusterIP
```
