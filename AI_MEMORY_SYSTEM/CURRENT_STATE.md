# Mevcut Durum — v1.2 Dashboard Ready

**Tarih:** 2026-07-31
**Branch:** main
**Tag:** v1.2.0
**Test:** 224 passed

## v1.2 Yenilikleri
- Dashboard API (/latest, /health)
- CORS enabled for localhost:5173

## Tamamlanan
- v1.0: Core cognitive loop
- v1.1: Trusted paper cycle (forward outcome + decision persist)
- v1.2: Dashboard API

## Sistem
- 4 Agent + SourceReliabilityAgent
- Cognitive Engine (council/meta/fusion)
- Risk Gate + Enforcement
- Forward Outcome (N-bar PnL)
- Decision Recording
- ML Training Pipeline
- Backtest + Genetic Algorithm
- Market Data Provider (mock|binance)
- Simulator
- API Endpoints (/cycle, /status, /metrics, /dashboard/latest, /dashboard/health)

## Sonraki
- v1.3: Binance testnet smoke
- v1.4: WebSocket live feed (opsiyonel)
- v1.5: Dashboard UI bağlantısı
