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

# Faz 312 — 3. dış rapor bulgusu (kullanıcı doğrulattı): image ~11.6GB,
# çünkü pyproject.toml'daki "torch>=2.3.0" pip'i PyPI'daki VARSAYILAN
# (CUDA çalışma zamanı gömülü) linux wheel'ine düşürüyordu — bu ortamın
# GPU'su yok, o CUDA kütüphaneleri hiç kullanılmıyor, sadece disk/pull
# süresini şişiriyordu. Gerçek ölçüm (2026-08-20, download.pytorch.org +
# pypi.org JSON API): torch 2.6.0 cp313-linux_x86_64 CUDA'lı 766.6MB,
# CPU-only (download.pytorch.org/whl/cpu) SADECE 178.5MB — tek paket
# ~589MB azalıyor. pyproject.toml'daki "torch>=2.3.0" KASITLI OLARAK
# değiştirilmedi — "torch==X+cpu" pin'i macOS/Windows'ta (bu +cpu
# etiketi SADECE Linux'ta var) yerel `pip install .`'ı tamamen kırardı.
# Bunun yerine CPU-only sürüm burada, `pip install .`'DAN ÖNCE açıkça
# kuruluyor — pip .'daki "torch>=2.3.0" kısıtını zaten karşılanmış bulup
# YENİDEN İNMİYOR (2.6.0 >= 2.3.0), CUDA'lı varyantı hiç görmüyor.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --extra-index-url https://download.pytorch.org/whl/cpu "torch==2.6.0+cpu" && \
    pip install .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
