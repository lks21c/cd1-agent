# CD1 Agent Build Guide

This guide covers building, packaging, and deploying the CD1 Agent.

## Quick Start

```bash
# Development installation
make dev

# Run tests
make test

# Build wheel
make wheel

# Build Lambda layer
make layer
```

## Development Installation

### Basic Installation

```bash
# Install in editable mode
pip install -e .

# Or using make
make install
```

### Full Development Setup

```bash
# Install all development dependencies
pip install -e ".[dev,luminol,vllm,gemini,rds]"

# Or using make
make dev
```

### Optional Dependencies

| Extra | Description | Command |
|-------|-------------|---------|
| `dev` | Testing, linting, formatting | `pip install -e ".[dev]"` |
| `luminol` | Cost anomaly detection (Luminol) | `pip install -e ".[luminol]"` |
| `vllm` | vLLM LLM provider | `pip install -e ".[vllm]"` |
| `gemini` | Google Gemini LLM provider | `pip install -e ".[gemini]"` |
| `rds` | RDS pattern detection (MySQL) | `pip install -e ".[rds]"` |
| `all` | All optional dependencies | `pip install -e ".[all]"` |

## Building Wheel Package

```bash
# Using make
make wheel

# Or directly
./scripts/build_wheel.sh
```

The wheel will be created in `dist/cd1_agent-X.Y.Z-py3-none-any.whl`.

## Building Lambda Layer

Lambda Layers allow you to include dependencies without bundling them in your Lambda deployment package.

### Basic Layer (Core Dependencies)

```bash
make layer
```

### Layer with Optional Dependencies

```bash
# With vLLM support
make layer-vllm

# With Gemini support
make layer-gemini

# With RDS pattern detection
make layer-rds

# Full layer (all dependencies)
make layer-full
```

### Manual Layer Build

```bash
./scripts/build_lambda_layer.sh --with-vllm --with-gemini --with-rds
```

### Deploying Lambda Layer

```bash
aws lambda publish-layer-version \
    --layer-name cd1-agent \
    --zip-file fileb://dist/cd1-agent-layer.zip \
    --compatible-runtimes python3.10 python3.11 python3.12 \
    --description "CD1 Agent dependencies"
```

### Using the Layer in Lambda

1. Add the layer ARN to your Lambda function
2. Set handler to: `src.agents.bdp.handler.handler`

## Publishing to CodeArtifact

For enterprise/financial environments using AWS CodeArtifact:

### Setup

1. Create CodeArtifact domain and repository
2. Set environment variables:

```bash
export CODEARTIFACT_DOMAIN=my-domain
export CODEARTIFACT_REPOSITORY=python-packages
export AWS_REGION=ap-northeast-2
```

### Publish

```bash
make publish

# Or with custom parameters
./scripts/publish_codeartifact.sh \
    --domain my-domain \
    --repository python-packages
```

### Installing from CodeArtifact

```bash
# Login to CodeArtifact
aws codeartifact login --tool pip \
    --domain my-domain \
    --repository python-packages

# Install
pip install cd1-agent
```

## Environment Variables

### LLM Configuration

```bash
# Provider selection (mock, vllm, gemini)
LLM_PROVIDER=vllm

# vLLM settings
VLLM_ENDPOINT=http://vllm-server:8000
VLLM_MODEL=gpt-oss-120b
VLLM_API_KEY=your-api-key

# Gemini settings
GEMINI_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your-gemini-api-key
```

### AWS Configuration

```bash
AWS_REGION=ap-northeast-2
AWS_PROVIDER=real  # or mock

DYNAMODB_TABLE=cd1-agent-results
EVENT_BUS=cd1-agent-events
```

### RDS Configuration (Pattern Detection)

```bash
RDS_HOST=your-rds-host.region.rds.amazonaws.com
RDS_PORT=3306
RDS_DATABASE=cd1_agent
RDS_USER=your-user
RDS_PASSWORD=your-password

# Use mock for testing
RDS_PROVIDER=mock
```

### Agent Parameters

```bash
MAX_ITERATIONS=5
CONFIDENCE_THRESHOLD=0.85
LOG_LEVEL=INFO
ENVIRONMENT=dev  # or prod
```

## Testing

```bash
# Run all tests
make test

# Unit tests only
make test-unit

# Integration tests
make test-integration

# With mock providers
AWS_PROVIDER=mock LLM_PROVIDER=mock RDS_PROVIDER=mock pytest tests/ -v
```

## RDS Detection Patterns Schema

For RDS-based pattern detection, create the following table:

```sql
CREATE TABLE detection_patterns (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    pattern_name VARCHAR(100) NOT NULL UNIQUE,
    pattern_type VARCHAR(50) NOT NULL,  -- SQL, METRIC, REGEX
    target_service VARCHAR(100),
    query_template TEXT NOT NULL,
    threshold_config JSON NOT NULL,
    severity VARCHAR(20) NOT NULL,      -- critical, high, medium, low
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_enabled (enabled),
    INDEX idx_target_service (target_service),
    INDEX idx_severity (severity)
);

-- Example patterns
INSERT INTO detection_patterns (pattern_name, pattern_type, target_service, query_template, threshold_config, severity) VALUES
('high_error_rate', 'SQL', NULL,
 'SELECT COUNT(*) as count FROM logs WHERE level = ''ERROR'' AND timestamp > NOW() - INTERVAL 1 HOUR',
 '{"value_field": "count", "value_threshold": 100}', 'high'),

('failed_auth', 'SQL', 'auth-service',
 'SELECT user_id, COUNT(*) as attempts FROM auth_logs WHERE success = FALSE AND timestamp > NOW() - INTERVAL 15 MINUTE GROUP BY user_id HAVING attempts >= 5',
 '{"count_threshold": 0}', 'critical');
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]
  release:
    types: [published]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: make dev

      - name: Run tests
        run: make test

      - name: Build wheel
        run: make wheel

      - name: Build Lambda layer
        run: make layer-full

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

## Troubleshooting

### Layer Size Limit

AWS Lambda layers have a 50MB compressed / 250MB uncompressed limit.

If your layer exceeds this:
1. Use minimal dependencies: `make layer` instead of `make layer-full`
2. Remove unused optional dependencies
3. Consider splitting into multiple layers

### vLLM Connection Issues

```bash
# Test vLLM connectivity
curl -X POST http://your-vllm-server:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-oss-120b", "messages": [{"role": "user", "content": "test"}]}'
```

### RDS Connection Issues

```bash
# Test RDS connectivity
mysql -h your-rds-host -u your-user -p cd1_agent -e "SELECT 1"
```
