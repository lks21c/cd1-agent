#!/bin/bash
# BDP Compact Agent Lambda Layer Build
# Builds a Lambda layer ZIP containing the package and dependencies
# Output: $REPO_ROOT/dist/bdp_cost/
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(cd "$PROJECT_DIR/../../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist/bdp_cost"
LAYER_DIR="$PROJECT_DIR/.layer_build"  # Temporary build directory

cd "$PROJECT_DIR"

echo "=== BDP Compact Agent Lambda Layer Build ==="
echo "Project directory: $PROJECT_DIR"
echo "Output directory:  $DIST_DIR"
echo ""

# Build wheel first (outputs to DIST_DIR)
echo "[1/5] Building wheel..."
"$SCRIPT_DIR/build_wheel.sh"

# Create layer directory
echo ""
echo "[2/5] Creating layer directory..."
rm -rf "$LAYER_DIR"
mkdir -p "$LAYER_DIR/python"

# Install dependencies for Lambda (manylinux platform)
# NOTE: Lightweight Lambda layer optimization
#   - boto3: Excluded - Lambda runtime provides boto3 1.28+ (Cost Explorer API supported)
#   - pyod/scipy: Excluded - Optional ML dependencies, ratio-based fallback available
#   - Only pydantic + numpy for core functionality
echo "[3/5] Installing dependencies for Lambda..."
python3 -m pip install \
    --platform manylinux2014_x86_64 \
    --target "$LAYER_DIR/python" \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all: \
    --upgrade \
    pydantic numpy 2>/dev/null || {
    echo "Warning: manylinux wheel download failed, using local platform..."
    python3 -m pip install \
        --target "$LAYER_DIR/python" \
        --upgrade \
        pydantic numpy
}

# Install the bdp-cost package
echo "[4/5] Installing bdp-cost package..."
WHEEL_FILE=$(ls "$DIST_DIR"/*.whl 2>/dev/null | head -1)
if [ -z "$WHEEL_FILE" ]; then
    echo "Error: No wheel file found in $DIST_DIR"
    exit 1
fi

# Unzip wheel directly into the python directory
unzip -q -o "$WHEEL_FILE" -d "$LAYER_DIR/python/"

# Remove unnecessary files to reduce size
echo "Cleaning up unnecessary files..."
find "$LAYER_DIR/python" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$LAYER_DIR/python" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$LAYER_DIR/python" -name "*.pyc" -delete 2>/dev/null || true
find "$LAYER_DIR/python" -name "*.pyo" -delete 2>/dev/null || true

# Create Lambda layer ZIP
echo "[5/5] Creating Lambda layer ZIP..."
LAYER_ZIP="$DIST_DIR/bdp-cost-layer.zip"
cd "$LAYER_DIR"
zip -r9 "$LAYER_ZIP" python/

# Calculate size
LAYER_SIZE=$(du -h "$LAYER_ZIP" | cut -f1)
LAYER_SIZE_BYTES=$(stat -f%z "$LAYER_ZIP" 2>/dev/null || stat -c%s "$LAYER_ZIP" 2>/dev/null)

# Cleanup temporary build directory
cd "$PROJECT_DIR"
rm -rf "$LAYER_DIR"

# Lambda layer size limits:
#   - Compressed: 50MB per layer
#   - Uncompressed: 250MB total (all layers + deployment package)
# Expected size after optimization: ~30-40MB (pydantic + numpy + bdp-cost)
echo ""
echo "=== Lambda Layer Build Complete ==="
echo "Layer file: $LAYER_ZIP"
echo "Layer size: $LAYER_SIZE"

if [ "$LAYER_SIZE_BYTES" -gt 52428800 ]; then  # 50MB
    echo ""
    echo "Warning: Layer size exceeds 50MB limit!"
    echo "Consider further optimization or splitting layers"
elif [ "$LAYER_SIZE_BYTES" -gt 41943040 ]; then  # 40MB
    echo ""
    echo "Note: Layer size is approaching 50MB limit"
fi

echo ""
echo "=== Output Files ==="
ls -la "$DIST_DIR/"

echo ""
echo "=== Usage ==="
echo "Deploy to AWS Lambda:"
echo "  aws lambda publish-layer-version \\"
echo "      --layer-name bdp-cost \\"
echo "      --zip-file fileb://$LAYER_ZIP \\"
echo "      --compatible-runtimes python3.11 python3.12"
