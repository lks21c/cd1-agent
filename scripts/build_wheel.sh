#!/bin/bash
# Build wheel package for CD1 Agent
# Usage: ./scripts/build_wheel.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== CD1 Agent Wheel Build ==="

# Clean previous builds
echo "[1/3] Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info

# Install build dependencies
echo "[2/3] Installing build dependencies..."
python3 -m pip install --quiet build wheel

# Build wheel
echo "[3/3] Building wheel..."
python3 -m build --wheel

echo ""
echo "=== Build Complete ==="
ls -la dist/

echo ""
echo "To install locally: pip install dist/*.whl"
echo "To publish: ./scripts/publish_codeartifact.sh"
