# Proje Hafızası — AI Quant Research Platform

## Misyon
Kurumsal seviyede, on yıllar boyunca evrilebilecek, yapay zekâ ile kantitatif araştırma yapan bir işletim sistemi inşa etmek.
Canlı ticaret YOKTUR; sadece kâğıt ticaret.

## Teknoloji Yığını
- Backend: Python 3.12, FastAPI, PostgreSQL+TimescaleDB, Redis, pgvector
- Frontend: React, TypeScript, TradingView Lightweight Charts, Plotly, ECharts
- ML: PyTorch, scikit-learn, XGBoost, LightGBM
- Altyapı: Docker, GitHub Actions, Prometheus+Grafana

## Kritik Prensipler
- Risk motoru AI'dan tamamen izole, imzalı yapılandırma ile çalışır.
- Her şey olay günlüğüne yazılır, hiçbir veri silinmez.
- Mimari Clean Architecture + DDD; bağımlılıklar sadece aşağıya doğru.
- Her bileşen değiştirilebilir.

## İletişim
Tüm kararlar ADR'ler ile kaydedilir.
