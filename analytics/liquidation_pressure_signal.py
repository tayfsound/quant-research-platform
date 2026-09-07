"""Likidasyon Baskısı Sinyali — Faz 439 (2026-09-08). Bkz. /Users/
emreturkes/.claude/plans/velvety-whistling-parasol.md (arşiv bölümü,
Ham Feature Ingestion planı).

Bağlam: `services/binance_liquidation_listener.py` (Faz 365) Binance'in
ücretsiz `!forceOrder@arr` akışına 13+ gündür bağlı, sıfır parse/persist
hatası — ama `market_data/liquidations/liquidation_provider.py::fetch_
liquidation_pressure()`'ın okuduğu `liquidation_events` tablosu bu
ortamda 0 satır. Kanıt hatasız-ama-veri-yok: bu ortamın coğrafi konumunun
Binance Futures WebSocket akışlarını engellediği, MempoolAgent/
BehavioralAgent için ZATEN bilinen kısıtlamayla (memory: Bosna Hersek'ten
futures WS veri vermiyor) AYNI imza. Bu modül SADECE saf sınıflandırma —
gerçek veri üretim sunucusunda birikince orada AYRICA doğrulanmalı, bu
ortamda test SENTETİK/MOCK veriyle yapılıyor (aynı MempoolAgent/
BehavioralAgent kısıtı, açıkça belgelendi).

Kasıtlı olarak SADECE gözlem — `services/orchestrator.py` bu çıktıyı
`ctx.market.features`'a ekliyor (Faz 436/order_flow_relationship İLE
AYNI desen), hiçbir agent'ın skoruna GİRMİYOR."""

DEFAULT_MIN_TOTAL_USD = 10_000.0   # bu eşiğin altında "yeterli veri yok"
DEFAULT_DOMINANCE_RATIO = 2.0      # bir taraf diğerinin en az 2 katı olmalı

_CATEGORIES = ("long_liquidation_dominant", "short_liquidation_dominant", "balanced", "no_data")


def compute_liquidation_pressure_signal(
    pressure: dict,
    min_total_usd: float = DEFAULT_MIN_TOTAL_USD,
    dominance_ratio: float = DEFAULT_DOMINANCE_RATIO,
) -> dict:
    """pressure: `fetch_liquidation_pressure()`'ın döndürdüğü şekilde
    ({'long_liquidated_usd', 'short_liquidated_usd', ...}). Kasıtlı
    olarak YÖN/skor kararı VERMİYOR — sadece hangi tarafın zorunlu
    kapanışa daha çok maruz kaldığını raporluyor (bu bilginin ne anlama
    geldiği — kapitülasyon mu, squeeze'in sonu mu — henüz kanıtlanmadı,
    ajan katmanının işi değil). Toplam notional min_total_usd'nin
    altındaysa "no_data" (icat edilmiş bir kategori asla üretilmez)."""
    long_usd = pressure.get("long_liquidated_usd") or 0.0
    short_usd = pressure.get("short_liquidated_usd") or 0.0
    total_usd = long_usd + short_usd

    if total_usd < min_total_usd:
        category = "no_data"
    elif long_usd >= short_usd * dominance_ratio:
        category = "long_liquidation_dominant"
    elif short_usd >= long_usd * dominance_ratio:
        category = "short_liquidation_dominant"
    else:
        category = "balanced"

    return {
        "category": category,
        "long_liquidated_usd": round(long_usd, 2),
        "short_liquidated_usd": round(short_usd, 2),
        "total_liquidated_usd": round(total_usd, 2),
        "long_short_ratio": round(long_usd / short_usd, 4) if short_usd > 0 else None,
    }
