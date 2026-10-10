# Multi-architecture build for a local Docker host (x86_64 or ARM64).
# Pin the multi-platform base manifest; update it through reviewed validation.
# Apt snapshots are fixed too; see docs/acceptance/BUILD.md for validation limits.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENBLAS_NUM_THREADS=4 \
    OMP_NUM_THREADS=4

# System deps
# hadolint global ignore=DL3008
# Dated, signed repositories fix package/dependency resolution across builds.
COPY config/build/debian.sources /tmp/ia-debian.sources
RUN rm -f /etc/apt/sources.list /etc/apt/sources.list.d/* \
    && cp /tmp/ia-debian.sources /etc/apt/sources.list.d/debian.sources \
    && rm /tmp/ia-debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    libopenblas-dev \
    libpq-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libfontconfig1 \
    pkg-config \
    shared-mime-info \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the complete, hash-locked Poetry bootstrap dependency set.
COPY requirements-poetry.txt ./requirements-poetry.txt
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-poetry.txt

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install runtime dependencies, including llama-cpp-python.
# llama-cpp-python compiles from source so it links against OpenBLAS on the host.
# This takes several minutes, but gives materially better CPU throughput.
ENV CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS" \
    FORCE_CMAKE=1
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-root --no-interaction

# Copy source
COPY src/ ./src/
COPY alembic.ini ./alembic.ini
COPY migrations/ ./migrations/
COPY .env.example ./.env.example
RUN mkdir -p /app/scripts
COPY scripts/create_user.py ./scripts/create_user.py
COPY scripts/create_broker_key.py ./scripts/create_broker_key.py

# Create directories and set up non-root user for security
RUN mkdir -p /app/reports /app/models \
    && useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info", "--no-proxy-headers"]
