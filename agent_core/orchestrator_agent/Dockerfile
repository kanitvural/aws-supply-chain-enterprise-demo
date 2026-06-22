# Cache bust for ARM64 migration
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app

# Configure UV for container environment (no venv, compile bytecode for speed)
ENV UV_SYSTEM_PYTHON=1 UV_COMPILE_BYTECODE=1

# Install Python dependencies first (cache-friendly layer ordering)
COPY requirements.txt .
RUN uv pip install -r requirements.txt

# Install OpenTelemetry for distributed tracing and observability
RUN uv pip install aws-opentelemetry-distro>=0.10.1

# Set AWS region
ENV AWS_REGION=eu-central-1
ENV AWS_DEFAULT_REGION=eu-central-1

# Signal that this is running in a container
ENV DOCKER_CONTAINER=1

# Security: run as non-root user
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 8080

# Copy application code
COPY main.py .

# OpenTelemetry auto-instrumentation wraps the Python process to capture
# all HTTP, boto3, and framework calls for distributed tracing in CloudWatch
CMD ["opentelemetry-instrument", "python", "main.py"]
