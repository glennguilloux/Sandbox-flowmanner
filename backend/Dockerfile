# ============================================================
# Flowmanner Backend — Hardened Multi-Stage Dockerfile
# ============================================================

# ---------- Stage 1: builder ----------
FROM python:3.11.11-slim-bookworm AS builder

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install build-time system dependencies (gcc for C extensions, Playwright system deps)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        git \
        libpq-dev \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libxshmfence1 libx11-6 libx11-xcb1 libxcb1 libxext6 \
        libxfixes3 libxrender1 libxcb-shape0 libxcb-shm0 \
        libxcb-xfixes0 libxcb-randr0 libxcb-image0 libxcb-keysyms1 \
        libxcb-xtest0 libxcb-sync1 libxcb-util1 \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment so we can copy only it into runtime
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies first (cached layer)
COPY requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /build/requirements.txt

# Install Playwright browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install chromium

# ---------- Stage 2: runtime ----------
FROM python:3.11.11-slim-bookworm AS runtime

LABEL maintainer="flowmanner" \
      description="Flowmanner backend – hardened production image"

# Only the runtime system libraries (no gcc, no dev headers)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        curl \
        libpq5 \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libxshmfence1 libx11-6 libx11-xcb1 libxcb1 libxext6 \
        libxfixes3 libxrender1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd --gid 1000 flowmanner \
    && useradd --uid 1000 --gid flowmanner --create-home --shell /bin/bash flowmanner

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy only application code (not tests, scripts, docs, .git, etc.)
COPY app/ /app/app/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini
COPY pyproject.toml /app/pyproject.toml
COPY mcp_gateway/ /app/mcp_gateway/
COPY agent_definitions/ /app/agent_definitions/
COPY scripts/ /app/scripts/

# Ensure no stray __pycache__ or .pyc from the host leak in
RUN find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
    find /app -name '*.pyc' -delete 2>/dev/null; \
    chown -R flowmanner:flowmanner /app

# Pre-create uploads directory so Docker volume (mounted at runtime) inherits the parent dir's permissions
RUN mkdir -p /app/uploads && chown flowmanner:flowmanner /app/uploads

# Copy Playwright browsers from builder
COPY --from=builder /ms-playwright /ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Copy entrypoint and set as root entrypoint
COPY docker-entrypoint.py /docker-entrypoint.py
RUN chmod +x /docker-entrypoint.py

ENTRYPOINT ["/docker-entrypoint.py"]

# Pre-create uploads directory so Docker volume (mounted at runtime) inherits the parent dir's permissions
RUN mkdir -p /app/uploads && chown flowmanner:flowmanner /app/uploads

# Switch to non-root user (entrypoint drops to this user after chown)
USER flowmanner

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main_fastapi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
