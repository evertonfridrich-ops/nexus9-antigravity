# Multi-stage build for NEXUS9 MCP Server
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock.txt .
RUN python -m pip install --no-cache-dir --user --require-hashes -r requirements.lock.txt

# Final Minimal Runtime Stage
FROM python:3.12-slim-bookworm AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/nexus9/.local/bin:$PATH" \
    PYTHONPATH="/app/src"

RUN groupadd -g 10001 nexus9 && \
    useradd -u 10001 -g nexus9 -m -s /bin/bash nexus9

WORKDIR /app

COPY --from=builder /root/.local /home/nexus9/.local
COPY --chown=nexus9:nexus9 pyproject.toml .
COPY --chown=nexus9:nexus9 src ./src
COPY --chown=nexus9:nexus9 server.py .
COPY --chown=nexus9:nexus9 integration.py .

USER nexus9

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import sys; from nexus9.suite import NexusSuite; sys.exit(0)" || exit 1

ENTRYPOINT ["python", "server.py"]
