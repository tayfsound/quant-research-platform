# Geliştirme Ortamı Kurulumu

## Gereksinimler

- Python 3.12+
- Node.js 20+
- Docker

## Adımlar

1. Depoyu klonla
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -e ".[dev]"`
4. `docker compose up -d`
5. `cd dashboard && npm install`
