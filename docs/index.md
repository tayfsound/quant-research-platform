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
- **Pozisyon boyutu çarpanları SADECE küçültür, asla büyütmez.** AI kendi
  risk tavanını (council'in önerdiği `proposed_size`) hiçbir mekanizma
  üzerinden genişletemez — her boyut/kaldıraç çarpanı `[0, 1]` (ya da
  kaldıraç için `[1.0, taban]`) aralığında, "yeterli kanıt yoksa 1.0
  (dokunma)" fail-closed ilkesiyle çalışır. 2026-08-24'te tüm mevcut
  çarpanlar tek tek doğrulandı: `kelly_size_multiplier`,
  `meta_label_size_multiplier`, `drawdown_size_multiplier`,
  `InnerCritic.confidence_multiplier` ([0.5, 1.0]),
  pump_fade `_compute_density_size_multiplier`/`_compute_regime_size_
  multiplier`, `pyramid_dampened_leverage`, `max_safe_leverage` (tavan,
  asla taban değil) — hepsi ilkeye uyuyor.
  `services/agent_confidence_model.py::predict_confidence_multiplier`
  (TEK bir ajanın kendi geçmiş kalibrasyonuna göre çalışan, boyut-sonrası
  DEĞİL ajan-güveni-öncesi bir katman) 2026-08-24'e kadar `[0.5, 1.5]`
  aralığındaydı — Faz 264'te bilinçli tasarlanmış ama final pozisyon
  boyutuna dolaylı yoldan katkısı olabileceği (yüksek güvenli tek bir
  ajan, konsensüs confidence'ını yukarı çekebilir) fark edilince
  `[0.5, 1.0]`'a sıkıştırıldı — artık istisnasız, TÜM çarpanlar aynı
  ilkeye uyuyor.
