# ==========================================
# Phase 1: Builder stage
# ==========================================
FROM python:3.11-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies inside virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# Phase 2: Final runtime container
# ==========================================
FROM python:3.11-slim as runner

WORKDIR /app

# Install runtime utilities (git, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy source tree
COPY . .

# Set default settings environment variables
ENV SAFE_MODE_ENABLED=True
ENV MAX_SHELL_TIMEOUT=30
ENV LOG_LEVEL=INFO
ENV MEMORY_DB_PATH=/app/data/memory.db
ENV VECTOR_DB_PATH=/app/data/vector_store.json

# Declare data volume mount point
VOLUME [ "/app/data" ]

# Container Entrypoint script mapping
ENTRYPOINT [ "python", "main.py" ]
CMD [ "--help" ]
