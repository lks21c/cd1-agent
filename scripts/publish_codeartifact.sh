#!/bin/bash
# Publish to AWS CodeArtifact (for financial/enterprise environments)
# Usage: ./scripts/publish_codeartifact.sh [--domain DOMAIN] [--repository REPO]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Default values (override via environment or arguments)
CODEARTIFACT_DOMAIN="${CODEARTIFACT_DOMAIN:-my-domain}"
CODEARTIFACT_REPOSITORY="${CODEARTIFACT_REPOSITORY:-python-packages}"
CODEARTIFACT_OWNER="${CODEARTIFACT_OWNER:-}"
AWS_REGION="${AWS_REGION:-ap-northeast-2}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --domain)
            CODEARTIFACT_DOMAIN="$2"
            shift 2
            ;;
        --repository)
            CODEARTIFACT_REPOSITORY="$2"
            shift 2
            ;;
        --owner)
            CODEARTIFACT_OWNER="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=== CD1 Agent CodeArtifact Publish ==="
echo "Domain: $CODEARTIFACT_DOMAIN"
echo "Repository: $CODEARTIFACT_REPOSITORY"
echo "Region: $AWS_REGION"
echo ""

# Check if wheel exists
if [ ! -d "dist" ] || [ -z "$(ls -A dist/*.whl 2>/dev/null)" ]; then
    echo "[1/4] Building wheel first..."
    ./scripts/build_wheel.sh
else
    echo "[1/4] Using existing wheel in dist/"
fi

# Get authorization token
echo "[2/4] Getting CodeArtifact authorization token..."
OWNER_ARG=""
if [ -n "$CODEARTIFACT_OWNER" ]; then
    OWNER_ARG="--domain-owner $CODEARTIFACT_OWNER"
fi

CODEARTIFACT_AUTH_TOKEN=$(aws codeartifact get-authorization-token \
    --domain "$CODEARTIFACT_DOMAIN" \
    $OWNER_ARG \
    --region "$AWS_REGION" \
    --query authorizationToken \
    --output text)

# Get repository endpoint
echo "[3/4] Getting repository endpoint..."
CODEARTIFACT_REPOSITORY_URL=$(aws codeartifact get-repository-endpoint \
    --domain "$CODEARTIFACT_DOMAIN" \
    $OWNER_ARG \
    --repository "$CODEARTIFACT_REPOSITORY" \
    --format pypi \
    --region "$AWS_REGION" \
    --query repositoryEndpoint \
    --output text)

# Configure twine
export TWINE_USERNAME=aws
export TWINE_PASSWORD="$CODEARTIFACT_AUTH_TOKEN"
export TWINE_REPOSITORY_URL="${CODEARTIFACT_REPOSITORY_URL}simple/"

# Publish
echo "[4/4] Publishing to CodeArtifact..."
python3 -m pip install --quiet twine
twine upload dist/*.whl

echo ""
echo "=== Publish Complete ==="
echo ""
echo "To install from CodeArtifact:"
echo "  python3 -m pip install cd1-agent --index-url ${CODEARTIFACT_REPOSITORY_URL}simple/"
echo ""
echo "Or configure python3 -m pip.conf:"
echo "  aws codeartifact login --tool python3 -m pip --domain $CODEARTIFACT_DOMAIN --repository $CODEARTIFACT_REPOSITORY"
