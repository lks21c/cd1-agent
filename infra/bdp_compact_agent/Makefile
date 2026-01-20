.PHONY: up down init logs test clean athena-spike lambda-spike multi-drift detect status

ENDPOINT ?= http://localhost:4566
AGENT_URL ?= http://localhost:8005

# Docker Compose commands
up:
	docker-compose up -d
	@echo "Waiting for LocalStack to be ready..."
	@sleep 5
	$(MAKE) init

down:
	docker-compose down -v

logs:
	docker-compose logs -f

# Initialization
init:
	@echo "Initializing BDP Compact infrastructure..."
	LOCALSTACK_ENDPOINT=$(ENDPOINT) bash init/01-create-tables.sh
	LOCALSTACK_ENDPOINT=$(ENDPOINT) bash init/02-setup-eventbridge.sh
	LOCALSTACK_ENDPOINT=$(ENDPOINT) bash init/03-inject-baseline.sh

# Scenario injection
athena-spike:
	@echo "Injecting Athena spike scenario..."
	LOCALSTACK_ENDPOINT=$(ENDPOINT) bash scenarios/athena-spike.sh

lambda-spike:
	@echo "Injecting Lambda spike scenario..."
	LOCALSTACK_ENDPOINT=$(ENDPOINT) bash scenarios/lambda-spike.sh

multi-drift:
	@echo "Injecting multi-account drift scenario..."
	LOCALSTACK_ENDPOINT=$(ENDPOINT) bash scenarios/multi-account-drift.sh

# Agent commands
detect:
	@echo "Running cost drift detection..."
	curl -s -X POST $(AGENT_URL)/api/v1/detect \
		-H "Content-Type: application/json" \
		-d '{"days": 14, "publish_alerts": true}' | python3 -m json.tool

status:
	@echo "Getting agent status..."
	curl -s $(AGENT_URL)/api/v1/status | python3 -m json.tool

accounts:
	@echo "Getting configured accounts..."
	curl -s $(AGENT_URL)/api/v1/accounts | python3 -m json.tool

# Testing
test:
	@echo "Running BDP Compact tests..."
	cd ../.. && pytest tests/agents/bdp_compact/ -v

test-localstack:
	@echo "Running LocalStack integration tests..."
	cd ../.. && pytest tests/agents/bdp_compact/ -v -m localstack

# Cleanup
clean:
	docker-compose down -v
	rm -rf localstack_data

# Help
help:
	@echo "BDP Compact Agent LocalStack Environment"
	@echo ""
	@echo "Commands:"
	@echo "  make up           - Start LocalStack and initialize"
	@echo "  make down         - Stop and remove containers"
	@echo "  make init         - Initialize tables and baseline data"
	@echo "  make logs         - Follow container logs"
	@echo ""
	@echo "Scenarios:"
	@echo "  make athena-spike - Inject Athena cost spike"
	@echo "  make lambda-spike - Inject Lambda cost spike"
	@echo "  make multi-drift  - Inject multi-account drift"
	@echo ""
	@echo "Agent:"
	@echo "  make detect       - Run cost drift detection"
	@echo "  make status       - Get agent status"
	@echo "  make accounts     - Get configured accounts"
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run unit tests"
	@echo "  make test-localstack - Run LocalStack integration tests"
