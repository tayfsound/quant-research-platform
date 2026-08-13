"""Piyasa Rejimi Motoru v2 — Faz 319-343 (Cognitive Core 2.0).

Mevcut kombine rejim etiketi (engines/cognitive_pipeline.py::
f"{trend}_{volatility_regime}", weight-snapshot seçimini besliyor) SADECE
hızlı/gürültülü `trend` alanını (ema20 vs ema50, hiçbir gecikme koruması
yok) kullanıyor — signal_engine.compute_quant_signals'ın ZATEN ürettiği,
tam olarak bunun için inşa edilmiş iki daha sağlam sinyali hiç
kullanmıyor:
- long_term_trend_regime: 200-EMA tabanlı, YAVAŞ ama gürültüsüz.
- regime_changepoint_detected: Welch t-test tabanlı, gerçek yön
  değişimini (long_term_trend_regime'ın kaçırdığı) yakalayan HIZLI sinyal
  — gerçek bir olaydan (2026-08-12, 50 ardışık kayıp) sonra eklenmişti,
  ama o olaydan bu yana hâlâ hiçbir rejim etiketine dahil edilmemişti.

Bu modül üçünü birleştiren daha zengin bir etiket üretiyor: "rejim GENEL
OLARAK ne" (long_term_trend_regime_volatility_regime) ile "şu an gerçekten
dönüyor mu" (_reversing eki) ayrımını taşıyor.

Kasıtlı olarak SADECE yeni bir sınıflandırma sunuyor — cognitive_
pipeline.py'deki GERÇEKTEN canlıda kullanılan, weight-snapshot seçimini
etkileyen current_regime hesaplamasını burada DEĞİŞTİRMİYOR; oraya geçiş
ayrı, insan onaylı bir karar."""


def compute_regime_v2(features: dict) -> str:
    """features: ctx.market.features (ya da eşdeğer bir dict) —
    long_term_trend_regime/volatility_regime/regime_changepoint_detected
    alanlarını okur. long_term_trend_regime "insufficient_data"ysa (ya da
    hiç yoksa) dürüstçe "insufficient_data" döner — icat edilmiş bir rejim
    asla üretilmez."""
    trend_regime = features.get("long_term_trend_regime", "insufficient_data")
    if trend_regime == "insufficient_data":
        return "insufficient_data"

    volatility_regime = features.get("volatility_regime", "normal")
    label = f"{trend_regime}_{volatility_regime}"

    if features.get("regime_changepoint_detected", False):
        label += "_reversing"

    return label
