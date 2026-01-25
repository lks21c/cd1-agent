# BDP Compact Agent - Build Automation
# ====================================
#
# Usage:
#   make wheel    - Build Python wheel package
#   make layer    - Build Lambda layer ZIP
#   make clean    - Clean local build artifacts only
#   make distclean - Clean local + central dist output
#   make install  - Install package locally
#   make test     - Run tests
#   make lint     - Run linter
#   make all      - Clean, build wheel, and build layer

.PHONY: all wheel layer clean distclean install test lint dev-install help

# Paths
REPO_ROOT := $(shell cd ../../.. && pwd)
DIST_DIR := $(REPO_ROOT)/dist/bdp_cost

# Default target
all: clean layer

# Build Python wheel
wheel:
	@echo "Building wheel..."
	./scripts/build_wheel.sh

# Build Lambda layer (includes wheel)
layer:
	@echo "Building Lambda layer..."
	./scripts/build_lambda_layer.sh

# Clean local build artifacts only (keeps central dist)
clean:
	@echo "Cleaning local build artifacts..."
	rm -rf build/ *.egg-info bdp_cost.egg-info .layer_build/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

# Clean everything including central dist output
distclean: clean
	@echo "Cleaning central dist output..."
	rm -rf $(DIST_DIR)

# Install package locally (editable mode)
install:
	@echo "Installing package..."
	pip install -e .

# Install with development dependencies
dev-install:
	@echo "Installing with dev dependencies..."
	pip install -e ".[dev,server]"

# Run tests
test:
	@echo "Running tests..."
	pytest tests/ -v --cov=bdp_cost --cov-report=term-missing

# Run linter
lint:
	@echo "Running linter..."
	ruff check bdp_cost/
	mypy bdp_cost/

# Format code
format:
	@echo "Formatting code..."
	ruff format bdp_cost/

# Show help
help:
	@echo "BDP Compact Agent - Build Commands"
	@echo "==================================="
	@echo ""
	@echo "Build targets:"
	@echo "  make wheel       Build Python wheel package"
	@echo "  make layer       Build Lambda layer ZIP (includes wheel)"
	@echo "  make clean       Clean local build artifacts"
	@echo "  make distclean   Clean local + central dist output"
	@echo "  make all         Clean + build layer"
	@echo ""
	@echo "Development targets:"
	@echo "  make install     Install package locally"
	@echo "  make dev-install Install with dev dependencies"
	@echo "  make test        Run tests"
	@echo "  make lint        Run linter"
	@echo "  make format      Format code"
	@echo ""
	@echo "Output directory: $(DIST_DIR)"
	@echo ""
	@echo "Output files:"
	@echo "  $(DIST_DIR)/bdp_cost-*.whl         Python wheel"
	@echo "  $(DIST_DIR)/bdp-cost-layer.zip     Lambda layer"
