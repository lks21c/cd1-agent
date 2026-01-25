.PHONY: help install dev test lint format clean build-wheel build-lambda run

# Variables
PYTHON := python3
PIP := pip3
PORT ?= 8006

help:
	@echo "BDP Drift Agent - Available commands:"
	@echo ""
	@echo "  install       - Install dependencies"
	@echo "  dev           - Install development dependencies"
	@echo "  test          - Run tests"
	@echo "  lint          - Run linting"
	@echo "  format        - Format code"
	@echo "  clean         - Clean build artifacts"
	@echo "  build-wheel   - Build Python wheel"
	@echo "  build-lambda  - Build Lambda layer"
	@echo "  run           - Run FastAPI server"
	@echo ""

install:
	$(PIP) install -e .

dev:
	$(PIP) install -e ".[dev]"

test:
	pytest tests/ -v --tb=short

lint:
	ruff check .
	mypy bdp_drift/

format:
	ruff format .
	ruff check --fix .

clean:
	rm -rf dist/ build/ *.egg-info/
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage

build-wheel:
	$(PYTHON) -m build

build-lambda:
	@echo "Building Lambda layer..."
	./scripts/build_lambda_layer.sh

run:
	DRIFT_PROVIDER=mock \
	BASELINE_DB_PROVIDER=sqlite \
	BASELINE_SQLITE_PATH=:memory: \
	uvicorn server:app --host 0.0.0.0 --port $(PORT) --reload

run-prod:
	DRIFT_PROVIDER=aws \
	BASELINE_DB_PROVIDER=mysql \
	uvicorn server:app --host 0.0.0.0 --port $(PORT)

# Database commands
init-db:
	$(PYTHON) scripts/init_baseline_db.py

# Test commands
test-detect:
	curl -X POST http://localhost:$(PORT)/api/v1/detect \
		-H "Content-Type: application/json" \
		-d '{"resource_types": ["glue", "athena"], "publish_alerts": false}'

test-baselines:
	curl http://localhost:$(PORT)/api/v1/baselines

test-resources:
	curl http://localhost:$(PORT)/api/v1/resources
