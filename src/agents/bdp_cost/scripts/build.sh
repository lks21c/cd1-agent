#!/bin/bash
# BDP Compact Agent Build Script
# Unified build script for wheel and Lambda layer
#
# Usage:
#   ./build.sh              # Build both wheel and Lambda layer
#   ./build.sh wheel        # Build wheel only
#   ./build.sh layer        # Build Lambda layer only
#   ./build.sh clean        # Clean all build artifacts
#   ./build.sh --help       # Show help
#
# Output: $REPO_ROOT/dist/bdp_cost/
#   - bdp_cost-*.whl     # Python wheel package
#   - bdp-cost-layer.zip # AWS Lambda layer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(cd "$PROJECT_DIR/../../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist/bdp_cost"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${GREEN}BDP Compact Agent Build${NC}                           ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_help() {
    echo "BDP Compact Agent Build Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  (none)    Build both wheel and Lambda layer (default)"
    echo "  wheel     Build Python wheel package only"
    echo "  layer     Build Lambda layer (includes wheel build)"
    echo "  clean     Clean all build artifacts"
    echo "  --help    Show this help message"
    echo ""
    echo "Output directory: \$REPO_ROOT/dist/bdp_cost/"
    echo ""
    echo "Examples:"
    echo "  $0              # Full build"
    echo "  $0 wheel        # Wheel only"
    echo "  $0 layer        # Lambda layer"
    echo "  $0 clean        # Clean artifacts"
}

clean_artifacts() {
    echo -e "${YELLOW}[Clean]${NC} Removing build artifacts..."

    cd "$PROJECT_DIR"

    # Clean local build artifacts
    rm -rf build/ *.egg-info bdp_cost.egg-info .layer_build/

    # Clean dist directory
    if [ -d "$DIST_DIR" ]; then
        rm -rf "$DIST_DIR"
        echo -e "  ${GREEN}✓${NC} Removed $DIST_DIR"
    fi

    echo -e "${GREEN}[Clean]${NC} Done!"
}

build_wheel() {
    echo -e "${YELLOW}[Wheel]${NC} Building Python wheel..."
    "$SCRIPT_DIR/build_wheel.sh"
    echo -e "${GREEN}[Wheel]${NC} Complete!"
}

build_layer() {
    echo -e "${YELLOW}[Layer]${NC} Building Lambda layer..."
    "$SCRIPT_DIR/build_lambda_layer.sh"
    echo -e "${GREEN}[Layer]${NC} Complete!"
}

show_summary() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${GREEN}Build Summary${NC}                                      ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Output directory: ${YELLOW}$DIST_DIR${NC}"
    echo ""

    if [ -d "$DIST_DIR" ]; then
        echo "Files:"
        ls -lh "$DIST_DIR/" 2>/dev/null | tail -n +2 | while read line; do
            echo -e "  ${GREEN}✓${NC} $line"
        done
    fi

    echo ""

    # Show Lambda deployment command if layer exists
    LAYER_ZIP="$DIST_DIR/bdp-cost-layer.zip"
    if [ -f "$LAYER_ZIP" ]; then
        echo -e "${BLUE}Deploy Lambda layer:${NC}"
        echo "  aws lambda publish-layer-version \\"
        echo "      --layer-name bdp-cost \\"
        echo "      --zip-file fileb://$LAYER_ZIP \\"
        echo "      --compatible-runtimes python3.11 python3.12"
        echo ""
    fi
}

# Main
print_header

case "${1:-all}" in
    --help|-h|help)
        print_help
        exit 0
        ;;
    clean)
        clean_artifacts
        ;;
    wheel)
        build_wheel
        show_summary
        ;;
    layer)
        build_layer
        show_summary
        ;;
    all|"")
        build_layer  # layer build includes wheel
        show_summary
        ;;
    *)
        echo -e "${RED}Error:${NC} Unknown command '$1'"
        echo ""
        print_help
        exit 1
        ;;
esac
