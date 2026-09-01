"""Market State / Direction Motoru — Faz 401 (Cognitive Core, Market State
Katmanı Faz 1). Bkz. /Users/emreturkes/.claude/plans/velvety-whistling-
parasol.md — kullanıcı onaylı büyük mimari proje.

`regime_engine.py::compute_regime_v2()` "ne TÜR bir piyasa" sorusuna
cevap veriyor (trend × volatilite + ters-dönüş bayrağı). Bu modül FARKLI
bir soruya cevap veriyor: "şu an HANGİ YÖNE eğilmeliyim, bu okuma ne
kadar güvenilir — ajanlardan/council'den BAĞIMSIZ olarak?" İkisini
karıştırmak (piyasa yönü ile strateji/pozisyon uygunluğunu tek bir
Council→karar hattında birleştirmek) dış mimari raporunun (2026-08-21)
işaret ettiği kök mimari boşluktu.

Faz 1 kasıtlı olarak SADECE gözlem — bu modülün çıktısı hiçbir canlı
kararı (Belief/MetaStage/pozisyon açma-kapama) ETKİLEMİYOR, sadece
ctx.cognition.relevant_knowledge'a kaydediliyor (bkz. services/
cognitive_engine.py wiring notu). Girdileri icat etmiyor — signal_engine.
compute_quant_signals()'ın ZATEN her cycle'da ürettiği alanları yeniden
kullanıyor:
- long_term_trend_regime (200-EMA tabanlı, yavaş/sağlam) -> direction
- regime_changepoint_detected (Welch t-test, yön işareti tersine
  döndüğünde True) -> reversing (bu modülün asıl amacı: bugün SADECE dar,
  çifte-koşullu "sideways market" WAIT kapısının içinde gömülü kullanılan
  bu sinyali, "piyasanın ölçülen yönü az önce döndü" olarak kendi başına
  dışarı çıkarmak)
- hurst_exponent (Faz'lardır MoE Regime Router'ın AYNI amaçla — rejim
  gücü/kalıcılığı ölçümü için — canlıda kullandığı gerçek istatistik,
  0.5'ten uzaklık = daha güçlü/kalıcı bir rejim, icat edilmiş bir skor
  değil) -> confidence"""

_DIRECTION_BY_TREND_REGIME = {
    "bull_trend": "LONG",
    "bear_trend": "SHORT",
}


def compute_market_state(features: dict) -> dict:
    """features: ctx.market.features (ya da eşdeğer bir dict) —
    long_term_trend_regime/volatility_regime/regime_changepoint_detected/
    hurst_exponent alanlarını okur, hiçbir DB/IO yapmıyor. long_term_
    trend_regime "insufficient_data"ysa (ya da hiç yoksa) direction
    dürüstçe "NEUTRAL", confidence 0.0 döner — icat edilmiş bir yön/güven
    asla üretilmez."""
    trend_regime = features.get("long_term_trend_regime", "insufficient_data")
    direction = _DIRECTION_BY_TREND_REGIME.get(trend_regime, "NEUTRAL")

    hurst_exponent = features.get("hurst_exponent")
    if trend_regime == "insufficient_data" or hurst_exponent is None:
        confidence = 0.0
    else:
        # MoE Regime Router (analytics/moe_regime_router.py) AYNI mantığı
        # canlıda zaten kullanıyor: 0.5'ten (rastgele yürüyüş) uzaklaştıkça
        # rejim daha güçlü/kalıcı. [0, 1] aralığına kırpılıyor.
        confidence = round(min(max(abs(hurst_exponent - 0.5) * 2, 0.0), 1.0), 4)

    volatility_regime = features.get("volatility_regime", "normal")
    label = f"{trend_regime}_{volatility_regime}"
    reversing = bool(features.get("regime_changepoint_detected", False))
    if reversing:
        label += "_reversing"

    return {
        "direction": direction,
        "confidence": confidence,
        "reversing": reversing,
        "regime_label": label,
    }


def market_state_reversing_for_decision(agent_contributions: list[dict] | None) -> bool | None:
    """Faz 404 (Market State Katmanı Faz 4) — kaydedilmiş agent_
    contributions'tan (engines/cognitive_pipeline.py::KnowledgeStage'in
    eklediği `market_state` girdisi, bkz. services/decision_recorder.py)
    o kararın ANINDAKİ `reversing` bayrağını döner.

    `analytics/agent_combination_reliability.py::agreeing_domains_for_
    decision` ile AYNI ilke: girdi hiç yoksa (bu alan SADECE Faz 401'den
    — 2026-09-01 — SONRAKİ kararlarda var; daha eski kararlarda hiç
    kaydedilmemiş) None döner — icat edilmiş bir değer asla üretilmez,
    çağıran taraf bu kararı örneklemden dışlamalı."""
    for item in agent_contributions or []:
        if isinstance(item, dict) and item.get("type") == "market_state":
            data = item.get("data") or {}
            reversing = data.get("reversing")
            if isinstance(reversing, bool):
                return reversing
    return None
