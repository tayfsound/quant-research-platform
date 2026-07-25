# AI Quant Research Platform

Kurumsal seviye, on yıllar boyunca evrilebilecek yapay zekâ ile kantitatif araştırma işletim sistemi.

## Hızlı Başlangıç

1. `docker compose up -d`
2. `pip install -e ".[dev]"`
3. `uvicorn api.main:app --reload`
4. `cd dashboard && npm run dev`

## Temel Prensipler

- **Önce mimari, sonra kod.**
- **Risk motoru AI'dan tamamen izole.**
- **Her şey olay günlüğüne yazılır, hiçbir şey silinmez.**
- **Eğitim ve üretim özellikleri asla ayrışmaz.**
