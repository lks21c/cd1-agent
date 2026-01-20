# CD1 Agent HTTP Server Dockerfile
# Multi-agent Dockerfile using build ARG for agent selection
#
# Build examples:
#   docker build --build-arg AGENT_NAME=cost -t cd1-agent-cost .
#   docker build --build-arg AGENT_NAME=hdsp -t cd1-agent-hdsp .
#   docker build --build-arg AGENT_NAME=bdp -t cd1-agent-bdp .
#   docker build --build-arg AGENT_NAME=drift -t cd1-agent-drift .

ARG PYTHON_VERSION=3.13

# ============================================================================
# Builder Stage
# ============================================================================
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml .
COPY README.md .

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install package with all optional dependencies including server
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[all,server]"

# ============================================================================
# Runtime Stage
# ============================================================================
FROM python:${PYTHON_VERSION}-slim AS runtime

# Build argument for agent selection
ARG AGENT_NAME=cost

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source code
COPY src/ ./src/
COPY conf/ ./conf/ 2>/dev/null || true

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Environment configuration
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    AGENT_NAME=${AGENT_NAME} \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the agent server
# Note: Using shell form to allow variable expansion
CMD uvicorn src.agents.${AGENT_NAME}.server:app --host ${HOST} --port ${PORT} --workers 2
