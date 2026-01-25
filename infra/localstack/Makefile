# ============================================================================
# CD1 Agent - Shared LocalStack Infrastructure Makefile
# ============================================================================
#
# This Makefile provides unified orchestration for all CD1 Agent test
# infrastructure running on LocalStack.
#
# Supported Agents:
#   - BDP (Behavioral Detection Patterns)
#   - HDSP (Health Detection Service Patterns) - future
#   - Drift (Configuration Drift Detection) - future
#
# Usage:
#   make help           # Show available commands
#   make up             # Start LocalStack
#   make down           # Stop LocalStack
#   make test-all       # Run all agent tests
#
# ============================================================================

.PHONY: help up down status clean \
        init-common bdp-init drift-init \
        bdp-baseline drift-baseline \
        bdp-scenarios drift-scenarios \
        test-all test-bdp test-drift \
        drift-scenario-eks drift-scenario-s3 drift-scenario-msk \
        drift-scenario-mwaa drift-scenario-multi

# Default target
.DEFAULT_GOAL := help

# Configuration
DOCKER_COMPOSE := docker compose
LOCALSTACK_ENDPOINT ?= http://localhost:4566
REGION ?= ap-northeast-2

# Colors for output
GREEN  := \033[0;32m
YELLOW := \033[0;33m
CYAN   := \033[0;36m
NC     := \033[0m # No Color

# ============================================================================
# Help
# ============================================================================

help:
	@echo ""
	@echo "$(CYAN)CD1 Agent LocalStack Infrastructure$(NC)"
	@echo "======================================"
	@echo ""
	@echo "$(GREEN)Core Commands:$(NC)"
	@echo "  make up              Start LocalStack services"
	@echo "  make up-full         Start LocalStack + MySQL (for BDP)"
	@echo "  make down            Stop all services"
	@echo "  make status          Show service status"
	@echo "  make clean           Stop services and remove data"
	@echo ""
	@echo "$(GREEN)Initialization:$(NC)"
	@echo "  make init-common     Create common DynamoDB tables & EventBridge"
	@echo "  make bdp-init        Initialize BDP agent (tables + metrics)"
	@echo "  make drift-init      Initialize Drift agent (tables + baselines)"
	@echo "  make init-all        Initialize all agents"
	@echo ""
	@echo "$(GREEN)Data Injection:$(NC)"
	@echo "  make bdp-baseline    Inject BDP baseline metrics"
	@echo "  make drift-baseline  Inject Drift baseline configs"
	@echo ""
	@echo "$(GREEN)Drift Scenarios:$(NC)"
	@echo "  make drift-scenario-eks    EKS instance downgrade drift"
	@echo "  make drift-scenario-s3     S3 public access drift (CRITICAL)"
	@echo "  make drift-scenario-msk    MSK broker downgrade drift"
	@echo "  make drift-scenario-mwaa   MWAA worker capacity drift"
	@echo "  make drift-scenario-multi  Multi-resource simultaneous drift"
	@echo ""
	@echo "$(GREEN)BDP Scenarios:$(NC)"
	@echo "  make bdp-scenario-cpu       High CPU spike"
	@echo "  make bdp-scenario-error     Error flood"
	@echo "  make bdp-scenario-auth      Auth failure pattern"
	@echo "  make bdp-scenario-timeout   DB timeout pattern"
	@echo ""
	@echo "$(GREEN)Testing:$(NC)"
	@echo "  make test-all        Run all LocalStack tests"
	@echo "  make test-bdp        Run BDP agent tests"
	@echo "  make test-drift      Run Drift agent tests"
	@echo ""
	@echo "$(GREEN)Utilities:$(NC)"
	@echo "  make logs            Show LocalStack logs"
	@echo "  make shell           Open bash shell in LocalStack"
	@echo "  make list-tables     List all DynamoDB tables"
	@echo "  make list-rules      List all EventBridge rules"
	@echo ""

# ============================================================================
# Core Infrastructure Commands
# ============================================================================

up:
	@echo "$(GREEN)Starting LocalStack...$(NC)"
	$(DOCKER_COMPOSE) up -d localstack
	@echo "Waiting for LocalStack to be healthy..."
	@until curl -s $(LOCALSTACK_ENDPOINT)/_localstack/health | grep -q '"ready": "true"'; do \
		echo "Waiting for LocalStack..."; \
		sleep 2; \
	done
	@echo "$(GREEN)LocalStack is ready!$(NC)"

up-full:
	@echo "$(GREEN)Starting LocalStack + MySQL...$(NC)"
	$(DOCKER_COMPOSE) --profile full up -d
	@echo "Waiting for services to be healthy..."
	@until curl -s $(LOCALSTACK_ENDPOINT)/_localstack/health | grep -q '"ready": "true"'; do \
		echo "Waiting for LocalStack..."; \
		sleep 2; \
	done
	@echo "$(GREEN)All services are ready!$(NC)"

down:
	@echo "$(YELLOW)Stopping services...$(NC)"
	$(DOCKER_COMPOSE) --profile full down

status:
	@echo "$(CYAN)Service Status:$(NC)"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "$(CYAN)LocalStack Health:$(NC)"
	@curl -s $(LOCALSTACK_ENDPOINT)/_localstack/health 2>/dev/null | python3 -m json.tool || echo "LocalStack not running"

clean:
	@echo "$(YELLOW)Stopping services and cleaning data...$(NC)"
	$(DOCKER_COMPOSE) --profile full down -v
	rm -rf ./data/*
	@echo "$(GREEN)Clean complete$(NC)"

logs:
	$(DOCKER_COMPOSE) logs -f localstack

shell:
	docker exec -it cd1-localstack bash

# ============================================================================
# Initialization Commands
# ============================================================================

init-common: up
	@echo "$(GREEN)Creating common DynamoDB tables...$(NC)"
	@chmod +x ./init/01-create-tables.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./init/01-create-tables.sh
	@echo ""
	@echo "$(GREEN)Setting up EventBridge...$(NC)"
	@chmod +x ./init/02-setup-eventbridge.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./init/02-setup-eventbridge.sh

bdp-init: init-common
	@echo "$(GREEN)Initializing BDP agent...$(NC)"
	@if [ -f ./bdp/init/03-inject-metrics.sh ]; then \
		chmod +x ./bdp/init/03-inject-metrics.sh; \
		LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./bdp/init/03-inject-metrics.sh; \
	fi
	@if [ -f ./bdp/init/04-inject-logs.sh ]; then \
		chmod +x ./bdp/init/04-inject-logs.sh; \
		LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./bdp/init/04-inject-logs.sh; \
	fi
	@echo "$(GREEN)BDP initialization complete$(NC)"

drift-init: init-common
	@echo "$(GREEN)Creating Drift agent DynamoDB tables...$(NC)"
	@chmod +x ./drift/init/03-create-drift-tables.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./drift/init/03-create-drift-tables.sh
	@echo ""
	@echo "$(GREEN)Injecting drift baseline configurations...$(NC)"
	@chmod +x ./drift/init/04-inject-drift-baselines.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./drift/init/04-inject-drift-baselines.sh
	@echo "$(GREEN)Drift initialization complete$(NC)"

init-all: init-common bdp-init drift-init
	@echo "$(GREEN)All agents initialized!$(NC)"

# ============================================================================
# Data Injection Commands
# ============================================================================

bdp-baseline: up
	@echo "$(GREEN)Injecting BDP baseline metrics...$(NC)"
	@if [ -f ./bdp/init/03-inject-metrics.sh ]; then \
		chmod +x ./bdp/init/03-inject-metrics.sh; \
		LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./bdp/init/03-inject-metrics.sh; \
	fi

drift-baseline: up
	@echo "$(GREEN)Injecting drift baseline configurations...$(NC)"
	@chmod +x ./drift/init/04-inject-drift-baselines.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./drift/init/04-inject-drift-baselines.sh

# ============================================================================
# Drift Scenario Commands
# ============================================================================

drift-scenario-eks: drift-init
	@echo "$(GREEN)Injecting EKS cluster drift scenario...$(NC)"
	@chmod +x ./drift/scenarios/eks-cluster-drift.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./drift/scenarios/eks-cluster-drift.sh

drift-scenario-s3: drift-init
	@echo "$(GREEN)Injecting S3 security drift scenario (CRITICAL)...$(NC)"
	@chmod +x ./drift/scenarios/s3-security-drift.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./drift/scenarios/s3-security-drift.sh

drift-scenario-msk: drift-init
	@echo "$(GREEN)Injecting MSK broker drift scenario...$(NC)"
	@chmod +x ./drift/scenarios/msk-broker-drift.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./drift/scenarios/msk-broker-drift.sh

drift-scenario-mwaa: drift-init
	@echo "$(GREEN)Injecting MWAA environment drift scenario...$(NC)"
	@chmod +x ./drift/scenarios/mwaa-env-drift.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./drift/scenarios/mwaa-env-drift.sh

drift-scenario-multi: drift-init
	@echo "$(GREEN)Injecting multi-resource drift scenario...$(NC)"
	@chmod +x ./drift/scenarios/multi-resource-drift.sh
	@LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./drift/scenarios/multi-resource-drift.sh

drift-scenarios: drift-scenario-eks drift-scenario-s3 drift-scenario-msk drift-scenario-mwaa drift-scenario-multi
	@echo "$(GREEN)All drift scenarios injected$(NC)"

# ============================================================================
# BDP Scenario Commands
# ============================================================================

bdp-scenario-cpu: bdp-init
	@echo "$(GREEN)Injecting high CPU spike scenario...$(NC)"
	@if [ -f ./bdp/scenarios/high-cpu-spike.sh ]; then \
		chmod +x ./bdp/scenarios/high-cpu-spike.sh; \
		LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./bdp/scenarios/high-cpu-spike.sh; \
	fi

bdp-scenario-error: bdp-init
	@echo "$(GREEN)Injecting error flood scenario...$(NC)"
	@if [ -f ./bdp/scenarios/error-flood.sh ]; then \
		chmod +x ./bdp/scenarios/error-flood.sh; \
		LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./bdp/scenarios/error-flood.sh; \
	fi

bdp-scenario-auth: bdp-init
	@echo "$(GREEN)Injecting auth failure scenario...$(NC)"
	@if [ -f ./bdp/scenarios/auth-failure.sh ]; then \
		chmod +x ./bdp/scenarios/auth-failure.sh; \
		LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./bdp/scenarios/auth-failure.sh; \
	fi

bdp-scenario-timeout: bdp-init
	@echo "$(GREEN)Injecting DB timeout scenario...$(NC)"
	@if [ -f ./bdp/scenarios/db-timeout.sh ]; then \
		chmod +x ./bdp/scenarios/db-timeout.sh; \
		LOCALSTACK_ENDPOINT=$(LOCALSTACK_ENDPOINT) ./bdp/scenarios/db-timeout.sh; \
	fi

bdp-scenarios: bdp-scenario-cpu bdp-scenario-error bdp-scenario-auth bdp-scenario-timeout
	@echo "$(GREEN)All BDP scenarios injected$(NC)"

# ============================================================================
# Testing Commands
# ============================================================================

test-all: init-all
	@echo "$(GREEN)Running all LocalStack tests...$(NC)"
	cd ../.. && pytest tests/ -m localstack -v

test-bdp: bdp-init
	@echo "$(GREEN)Running BDP agent tests...$(NC)"
	cd ../.. && pytest tests/agents/bdp/ -m localstack -v

test-drift: drift-init
	@echo "$(GREEN)Running Drift agent tests...$(NC)"
	cd ../.. && pytest tests/agents/drift/ -m localstack -v

# ============================================================================
# Utility Commands
# ============================================================================

list-tables:
	@echo "$(CYAN)DynamoDB Tables:$(NC)"
	@awslocal dynamodb list-tables --region $(REGION) 2>/dev/null || \
		docker exec cd1-localstack awslocal dynamodb list-tables --region $(REGION)

list-rules:
	@echo "$(CYAN)EventBridge Rules:$(NC)"
	@awslocal events list-rules --event-bus-name cd1-agent-events --region $(REGION) 2>/dev/null || \
		docker exec cd1-localstack awslocal events list-rules --event-bus-name cd1-agent-events --region $(REGION)

