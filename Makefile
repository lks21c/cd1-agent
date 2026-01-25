# CD1 Agent Makefile
# Build, test, and deployment automation

.PHONY: help install dev test lint format wheel layer build publish clean
.PHONY: server-dev server-hdsp server-bdp server-drift server-all
.PHONY: docker-server-build docker-server-up docker-server-down docker-server-logs

# Default target
help:
	@echo "CD1 Agent Build Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install      Install package in development mode"
	@echo "  make dev          Install with all development dependencies"
	@echo "  make test         Run tests with coverage"
	@echo "  make lint         Run linting (ruff + mypy)"
	@echo "  make format       Format code with black"
	@echo ""
	@echo "HTTP Server (K8s migration):"
	@echo "  make server-dev       Install server dependencies"
	@echo "  make server-hdsp      Run HDSP agent server (port 8002)"
	@echo "  make server-bdp       Run BDP agent server (port 8003)"
	@echo "  make server-drift     Run Drift agent server (port 8004)"
	@echo ""
	@echo "Docker Server:"
	@echo "  make docker-server-build   Build all agent Docker images"
	@echo "  make docker-server-up      Start all servers with docker-compose"
	@echo "  make docker-server-down    Stop all docker-compose services"
	@echo "  make docker-server-logs    View server logs"
	@echo ""
	@echo "Build:"
	@echo "  make wheel        Build wheel package"
	@echo "  make layer        Build Lambda layer (basic)"
	@echo "  make layer-full   Build Lambda layer with all optional deps"
	@echo "  make build        Build wheel + Lambda layer (both)"
	@echo ""
	@echo "Publish:"
	@echo "  make publish      Publish to CodeArtifact"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        Remove build artifacts"

# Development
install:
	pip install -e .

dev:
	pip install -e ".[dev,luminol,vllm,gemini,rds]"

# HTTP Server Development
server-dev:
	pip install -e ".[all,server]"

server-hdsp:
	@echo "=== Starting HDSP Agent Server on port 8002 ==="
	AWS_PROVIDER=mock LLM_PROVIDER=mock DEBUG=true \
		uvicorn src.agents.hdsp.server:app --reload --port 8002

server-bdp:
	@echo "=== Starting BDP Agent Server on port 8003 ==="
	AWS_PROVIDER=mock LLM_PROVIDER=mock RDS_PROVIDER=mock DEBUG=true \
		uvicorn src.agents.bdp.server:app --reload --port 8003

server-drift:
	@echo "=== Starting Drift Agent Server on port 8004 ==="
	AWS_PROVIDER=mock LLM_PROVIDER=mock DEBUG=true \
		uvicorn src.agents.drift.server:app --reload --port 8004

# Docker server commands
docker-server-build:
	@echo "=== Building all agent Docker images ==="
	docker build --build-arg AGENT_NAME=hdsp -t cd1-agent-hdsp .
	docker build --build-arg AGENT_NAME=bdp -t cd1-agent-bdp .
	docker build --build-arg AGENT_NAME=drift -t cd1-agent-drift .
	@echo "=== All images built ==="

docker-server-up:
	@echo "=== Starting all agent servers with docker-compose ==="
	docker-compose -f docker-compose.server.yml up -d
	@echo "Waiting for services to be healthy..."
	@sleep 10
	@echo ""
	@echo "=== Services ready ==="
	@echo "HDSP Agent:  http://localhost:8002 (profile: hdsp)"
	@echo "BDP Agent:   http://localhost:8003 (profile: bdp)"
	@echo "Drift Agent: http://localhost:8004 (profile: drift)"

docker-server-down:
	@echo "=== Stopping all docker-compose services ==="
	docker-compose -f docker-compose.server.yml down -v

docker-server-logs:
	docker-compose -f docker-compose.server.yml logs -f

docker-server-test:
	@echo "=== Testing all agent health endpoints ==="
	@curl -s http://localhost:8002/health | python3 -m json.tool 2>/dev/null || echo "HDSP agent not available"
	@curl -s http://localhost:8003/health | python3 -m json.tool 2>/dev/null || echo "BDP agent not available"
	@curl -s http://localhost:8004/health | python3 -m json.tool 2>/dev/null || echo "Drift agent not available"

# Testing
test:
	pytest tests/ -v --cov=src --cov-report=term-missing

test-unit:
	pytest tests/ -v -m "unit" --cov=src

test-integration:
	pytest tests/ -v -m "integration"

# Linting
lint:
	ruff check src/ tests/
	mypy src/

format:
	black src/ tests/
	ruff check --fix src/ tests/

# Build
wheel: clean
	./scripts/build_wheel.sh

layer: wheel
	./scripts/build_lambda_layer.sh

layer-vllm: wheel
	./scripts/build_lambda_layer.sh --with-vllm

layer-gemini: wheel
	./scripts/build_lambda_layer.sh --with-gemini

layer-rds: wheel
	./scripts/build_lambda_layer.sh --with-rds

layer-full: wheel
	./scripts/build_lambda_layer.sh --with-vllm --with-gemini --with-rds

build: wheel layer
	@echo "=== Build Complete: Wheel + Layer ==="

# Publish
publish: wheel
	./scripts/publish_codeartifact.sh

# Cleanup
clean:
	rm -rf dist/ build/ layer/ *.egg-info
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Docker (optional)
docker-build:
	docker build -t cd1-agent .

docker-test:
	docker run --rm cd1-agent pytest tests/ -v

# Local testing with mock providers
run-mock:
	AWS_PROVIDER=mock LLM_PROVIDER=mock RDS_PROVIDER=mock \
		python -c "from src.agents.bdp.handler import handler; print(handler({'detection_type': 'scheduled'}, None))"

# ============================================================================
# LocalStack Integration
# ============================================================================

.PHONY: localstack-up localstack-down localstack-test localstack-logs localstack-status
.PHONY: scenario-cpu-spike scenario-error-flood scenario-auth-failure scenario-db-timeout

# LocalStack environment management
localstack-up:
	@echo "=== Starting LocalStack environment ==="
	docker-compose -f infra/bdp_agent/docker-compose.yml up -d
	@echo "Waiting for LocalStack to be healthy..."
	@timeout 60 bash -c 'until curl -s http://localhost:4566/_localstack/health | grep -q "running"; do sleep 2; done' || (echo "LocalStack failed to start" && exit 1)
	@echo "Waiting for MySQL to be healthy..."
	@timeout 60 bash -c 'until docker-compose -f infra/bdp_agent/docker-compose.yml exec -T mysql mysqladmin ping -h localhost -u root -plocalstack 2>/dev/null; do sleep 2; done' || (echo "MySQL failed to start" && exit 1)
	@echo "=== LocalStack environment ready ==="

localstack-down:
	@echo "=== Stopping LocalStack environment ==="
	docker-compose -f infra/bdp_agent/docker-compose.yml down -v
	@echo "=== LocalStack environment stopped ==="

localstack-logs:
	docker-compose -f infra/bdp_agent/docker-compose.yml logs -f

localstack-status:
	@echo "=== LocalStack Status ==="
	@curl -s http://localhost:4566/_localstack/health | python3 -m json.tool 2>/dev/null || echo "LocalStack not running"
	@echo ""
	@echo "=== MySQL Status ==="
	@docker-compose -f infra/bdp_agent/docker-compose.yml exec -T mysql mysqladmin status -h localhost -u root -plocalstack 2>/dev/null || echo "MySQL not running"

# Run tests against LocalStack
localstack-test:
	@echo "=== Running tests against LocalStack ==="
	TEST_AWS_PROVIDER=localstack LOCALSTACK_ENDPOINT=http://localhost:4566 \
		pytest tests/agents/bdp/test_localstack_scenarios.py -v -m localstack

localstack-test-all:
	@echo "=== Running all BDP tests against LocalStack ==="
	TEST_AWS_PROVIDER=localstack LOCALSTACK_ENDPOINT=http://localhost:4566 \
		pytest tests/agents/bdp/ -v

# Failure scenario injection
scenario-cpu-spike:
	@echo "=== Injecting CPU Spike Scenario ==="
	LOCALSTACK_ENDPOINT=http://localhost:4566 ./infra/bdp_agent/scenarios/high-cpu-spike.sh test-function

scenario-error-flood:
	@echo "=== Injecting Error Flood Scenario ==="
	LOCALSTACK_ENDPOINT=http://localhost:4566 ./infra/bdp_agent/scenarios/error-flood.sh /aws/lambda/test-function

scenario-auth-failure:
	@echo "=== Injecting Auth Failure Scenario ==="
	LOCALSTACK_ENDPOINT=http://localhost:4566 MYSQL_HOST=localhost ./infra/bdp_agent/scenarios/auth-failure.sh /aws/lambda/auth-service

scenario-db-timeout:
	@echo "=== Injecting DB Timeout Scenario ==="
	LOCALSTACK_ENDPOINT=http://localhost:4566 MYSQL_HOST=localhost ./infra/bdp_agent/scenarios/db-timeout.sh /aws/lambda/data-processor

# Quick verification commands
localstack-verify-metrics:
	@echo "=== Verifying CloudWatch Metrics ==="
	awslocal cloudwatch list-metrics --namespace AWS/Lambda --endpoint-url http://localhost:4566

localstack-verify-logs:
	@echo "=== Verifying CloudWatch Logs ==="
	awslocal logs describe-log-groups --endpoint-url http://localhost:4566

localstack-verify-dynamodb:
	@echo "=== Verifying DynamoDB Tables ==="
	awslocal dynamodb list-tables --endpoint-url http://localhost:4566

localstack-verify-eventbridge:
	@echo "=== Verifying EventBridge ==="
	awslocal events list-event-buses --endpoint-url http://localhost:4566

localstack-verify-mysql:
	@echo "=== Verifying MySQL Patterns ==="
	docker-compose -f infra/bdp_agent/docker-compose.yml exec -T mysql \
		mysql -u cd1_user -pcd1_password cd1_agent -e "SELECT pattern_id, pattern_name, severity FROM detection_patterns;"

# ============================================================================
# HDSP Agent - Prometheus Test Environment
# ============================================================================

.PHONY: hdsp-up hdsp-down hdsp-test hdsp-logs hdsp-status
.PHONY: hdsp-scenario-crash-loop hdsp-scenario-oom hdsp-scenario-node-pressure
.PHONY: hdsp-scenario-high-cpu hdsp-scenario-high-memory hdsp-scenario-pod-restarts
.PHONY: all-up all-down

# HDSP environment management
hdsp-up:
	@echo "=== Starting HDSP Prometheus environment ==="
	docker-compose -f infra/hdsp_agent/docker-compose.yml up -d
	@echo "Waiting for Prometheus to be healthy..."
	@timeout 60 bash -c 'until curl -s http://localhost:9090/-/healthy | grep -q "Prometheus Server is Healthy"; do sleep 2; done' || (echo "Prometheus failed to start" && exit 1)
	@echo "Waiting for Pushgateway to be healthy..."
	@timeout 60 bash -c 'until curl -s http://localhost:9091/-/healthy | grep -q "OK"; do sleep 2; done' || (echo "Pushgateway failed to start" && exit 1)
	@echo "=== HDSP Prometheus environment ready ==="
	@echo ""
	@echo "Prometheus UI: http://localhost:9090"
	@echo "Pushgateway UI: http://localhost:9091"

hdsp-down:
	@echo "=== Stopping HDSP Prometheus environment ==="
	docker-compose -f infra/hdsp_agent/docker-compose.yml down -v
	@echo "=== HDSP Prometheus environment stopped ==="

hdsp-logs:
	docker-compose -f infra/hdsp_agent/docker-compose.yml logs -f

hdsp-status:
	@echo "=== Prometheus Status ==="
	@curl -s http://localhost:9090/-/healthy 2>/dev/null || echo "Prometheus not running"
	@echo ""
	@echo "=== Pushgateway Status ==="
	@curl -s http://localhost:9091/-/healthy 2>/dev/null || echo "Pushgateway not running"
	@echo ""
	@echo "=== Pushgateway Metrics ==="
	@curl -s http://localhost:9091/metrics 2>/dev/null | grep -E "^(kube_|container_)" | head -20 || echo "No K8s metrics injected"

# Run HDSP integration tests
hdsp-test:
	@echo "=== Running HDSP Prometheus integration tests ==="
	TEST_PROMETHEUS_PROVIDER=real PROMETHEUS_URL=http://localhost:9090 PUSHGATEWAY_URL=http://localhost:9091 \
		pytest tests/agents/hdsp/test_prometheus_integration.py -v -m prometheus

hdsp-test-all:
	@echo "=== Running all HDSP tests ==="
	PROMETHEUS_MOCK=true pytest tests/agents/hdsp/ -v

# Scenario injection commands
hdsp-scenario-crash-loop:
	@echo "=== Injecting CrashLoopBackOff Scenario ==="
	PUSHGATEWAY_URL=http://localhost:9091 ./infra/hdsp_agent/scenarios/crash-loop-backoff.sh spark test-crash-loop-pod

hdsp-scenario-oom:
	@echo "=== Injecting OOMKilled Scenario ==="
	PUSHGATEWAY_URL=http://localhost:9091 ./infra/hdsp_agent/scenarios/oom-killed.sh hdsp test-oom-pod

hdsp-scenario-node-pressure:
	@echo "=== Injecting Node Pressure Scenario ==="
	PUSHGATEWAY_URL=http://localhost:9091 ./infra/hdsp_agent/scenarios/node-pressure.sh worker-node-1 MemoryPressure

hdsp-scenario-high-cpu:
	@echo "=== Injecting High CPU Scenario ==="
	PUSHGATEWAY_URL=http://localhost:9091 ./infra/hdsp_agent/scenarios/high-cpu.sh default high-cpu-pod

hdsp-scenario-high-memory:
	@echo "=== Injecting High Memory Scenario ==="
	PUSHGATEWAY_URL=http://localhost:9091 ./infra/hdsp_agent/scenarios/high-memory.sh hdsp high-memory-pod

hdsp-scenario-pod-restarts:
	@echo "=== Injecting Pod Restarts Scenario ==="
	PUSHGATEWAY_URL=http://localhost:9091 ./infra/hdsp_agent/scenarios/pod-restarts.sh spark unstable-pod

# Verification commands
hdsp-verify-metrics:
	@echo "=== Verifying Prometheus Metrics ==="
	@echo "--- CrashLoopBackOff Pods ---"
	@curl -s 'http://localhost:9090/api/v1/query?query=kube_pod_container_status_waiting_reason' | python3 -m json.tool 2>/dev/null | head -30 || echo "Query failed"
	@echo ""
	@echo "--- OOMKilled Pods ---"
	@curl -s 'http://localhost:9090/api/v1/query?query=kube_pod_container_status_last_terminated_reason' | python3 -m json.tool 2>/dev/null | head -30 || echo "Query failed"
	@echo ""
	@echo "--- Node Conditions ---"
	@curl -s 'http://localhost:9090/api/v1/query?query=kube_node_status_condition{status="true"}' | python3 -m json.tool 2>/dev/null | head -30 || echo "Query failed"

hdsp-clear-metrics:
	@echo "=== Clearing all Pushgateway metrics ==="
	@curl -X DELETE http://localhost:9091/metrics/job/kube-state-metrics 2>/dev/null || true
	@curl -X DELETE http://localhost:9091/metrics/job/cadvisor 2>/dev/null || true
	@echo "Metrics cleared"

# Combined environment commands
all-up: localstack-up hdsp-up
	@echo "=== All test environments ready ==="
	@echo "LocalStack: http://localhost:4566"
	@echo "Prometheus: http://localhost:9090"
	@echo "Pushgateway: http://localhost:9091"

all-down: localstack-down hdsp-down
	@echo "=== All test environments stopped ==="
