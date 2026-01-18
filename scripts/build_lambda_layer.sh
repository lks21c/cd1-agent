#!/bin/bash
# Build Lambda Layer for CD1 Agent
# Creates a Lambda-compatible layer with all dependencies
# Usage: ./scripts/build_lambda_layer.sh [--with-vllm] [--with-gemini] [--with-rds]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== CD1 Agent Lambda Layer Build ==="

# Parse arguments
WITH_VLLM=false
WITH_GEMINI=false
WITH_RDS=false

for arg in "$@"; do
    case $arg in
        --with-vllm)
            WITH_VLLM=true
            ;;
        --with-gemini)
            WITH_GEMINI=true
            ;;
        --with-rds)
            WITH_RDS=true
            ;;
    esac
done

# Build wheel first
echo "[1/5] Building wheel..."
./scripts/build_wheel.sh

# Create layer directory structure
LAYER_DIR="$PROJECT_DIR/layer"
echo "[2/5] Creating layer directory..."
rm -rf "$LAYER_DIR"
mkdir -p "$LAYER_DIR/python"

# Install dependencies with manylinux platform
echo "[3/5] Installing dependencies..."
python3 -m pip install \
    --platform manylinux2014_x86_64 \
    --target "$LAYER_DIR/python" \
    --implementation cp \
    --python-version 3.13 \
    --only-binary=:all: \
    --upgrade \
    pydantic boto3 langchain-core langgraph

# Install optional dependencies
if [ "$WITH_VLLM" = true ]; then
    echo "    Installing vLLM dependencies..."
    python3 -m pip install \
        --platform manylinux2014_x86_64 \
        --target "$LAYER_DIR/python" \
        --implementation cp \
        --python-version 3.13 \
        --only-binary=:all: \
        --upgrade \
        openai httpx
fi

if [ "$WITH_GEMINI" = true ]; then
    echo "    Installing Gemini dependencies..."
    python3 -m pip install \
        --platform manylinux2014_x86_64 \
        --target "$LAYER_DIR/python" \
        --implementation cp \
        --python-version 3.13 \
        --only-binary=:all: \
        --upgrade \
        google-generativeai
fi

if [ "$WITH_RDS" = true ]; then
    echo "    Installing RDS dependencies..."
    python3 -m pip install \
        --platform manylinux2014_x86_64 \
        --target "$LAYER_DIR/python" \
        --implementation cp \
        --python-version 3.13 \
        --only-binary=:all: \
        --upgrade \
        pymysql cryptography
fi

# Install the package itself (extract wheel directly to avoid Python version check)
echo "[4/5] Installing cd1-agent package..."
unzip -q -o dist/*.whl -d "$LAYER_DIR/python/"

# Create ZIP file
echo "[5/5] Creating Lambda layer ZIP..."
cd "$LAYER_DIR"
zip -r9 "$PROJECT_DIR/dist/cd1-agent-layer.zip" python/

# Calculate size
LAYER_SIZE=$(du -h "$PROJECT_DIR/dist/cd1-agent-layer.zip" | cut -f1)

echo ""
echo "=== Lambda Layer Build Complete ==="
echo "Layer file: dist/cd1-agent-layer.zip"
echo "Layer size: $LAYER_SIZE"
echo ""
echo "Lambda layer limit: 50MB compressed, 250MB uncompressed"
echo ""
echo "To upload to AWS:"
echo "  aws lambda publish-layer-version \\"
echo "    --layer-name cd1-agent \\"
echo "    --zip-file fileb://dist/cd1-agent-layer.zip \\"
echo "    --compatible-runtimes python3.13"
