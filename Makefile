# CD1 Agent Makefile
# Build, test, and deployment automation

.PHONY: help install dev test lint format wheel layer build publish clean

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
