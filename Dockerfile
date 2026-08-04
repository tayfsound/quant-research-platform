# Sprint 25-26: docker-compose.yml has referenced this file since before
# this session (build: dockerfile: Dockerfile) but it never existed —
# `docker-compose up --build` on the api service has never actually worked.
FROM python:3.13-slim AS base

WORKDIR /app

# System deps for psycopg2 (compiled) and bcrypt/cryptography.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# A BuildKit cache mount for pip's download/wheel cache (replacing
# --no-cache-dir) means that even when dependencies change (e.g. adding
# celery in Sprint 27, after the first build here had already pulled
# torch + sentence-transformers — together >1GB, ~35 minutes on this
# connection), pip reuses already-downloaded wheels for every unchanged
# package instead of re-fetching the whole dependency set from scratch.
COPY pyproject.toml ./
COPY . .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
