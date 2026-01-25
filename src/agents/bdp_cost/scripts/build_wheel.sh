#!/bin/bash
# BDP Compact Agent Wheel Build
# Builds a standalone Python wheel package
# Output: $REPO_ROOT/dist/bdp_cost/
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(cd "$PROJECT_DIR/../../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist/bdp_cost"

cd "$PROJECT_DIR"

echo "=== BDP Compact Agent Wheel Build ==="
echo "Project directory: $PROJECT_DIR"
echo "Output directory:  $DIST_DIR"
echo ""

# Clean previous builds (local temp only, not central dist)
echo "[1/4] Cleaning local build artifacts..."
rm -rf build/ *.egg-info bdp_cost.egg-info

# Create output directory
echo "[2/4] Creating output directory..."
mkdir -p "$DIST_DIR"

# Install build dependencies
echo "[3/4] Installing build tools..."
python3 -m pip install --quiet --upgrade build wheel

# Build wheel with output to central dist
echo "[4/4] Building wheel..."
python3 -m build --wheel --outdir "$DIST_DIR"

echo ""
echo "=== Build Complete ==="
ls -la "$DIST_DIR/"

# Show wheel contents
echo ""
echo "=== Wheel Contents ==="
WHEEL_FILE=$(ls "$DIST_DIR"/*.whl 2>/dev/null | head -1)
if [ -n "$WHEEL_FILE" ]; then
    python3 -c "import zipfile; zf=zipfile.ZipFile('$WHEEL_FILE'); print('\n'.join(sorted([f.filename for f in zf.filelist])[:20]))"
    echo "..."
fi

# Clean up local build artifacts
echo ""
echo "Cleaning up local build artifacts..."
rm -rf build/ *.egg-info bdp_cost.egg-info
