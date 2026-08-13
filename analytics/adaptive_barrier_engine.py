"""Adaptive Barrier Engine — Faz 494-518 (Cognitive Core 2.0 / M3).

analytics/mae_mfe.py::compute_optimal_barrier() GEÇMİŞ trade'lerden koşul
kovası başına EN İYİ (sl_pct, tp_pct) çiftini hesaplıyor — ama bu sonuç
statik bir rapor, YENİ bir kararın hangi kovaya düştüğünü bulup ondan
öneri okumak için bir mekanizma yoktu. Bu modül o köprüyü kuruyor: GERÇEK
zamanlı bir karar bağlamı (rejim/volatilite/yön/güven) verildiğinde,
ÖNCEDEN hesaplanmış barrier tablosundan (compute_optimal_barrier'ın
çıktısı) eşleşen kovayı bulup SL/TP önerisini döner.

Kasıtlı olarak SADECE öneri motoru — hiçbir gerçek pozisyonun SL/TP'sini
burada otomatik DEĞİŞTİRMİYOR, mevcut karar hattına WIRE edilmemiş.
Canlıya alınması ayrı, gerçek OOS doğrulama + insan onayı gerektiren bir
karar (proje kuralı: 'yeni karmaşıklık kendi edge'ini kanıtlamalı')."""
from analytics.mae_mfe import _confidence_bucket


def _build_lookup_key(context: dict, group_by: tuple[str, ...]) -> str:
    """compute_optimal_barrier()'ın kendi etiket üretim mantığıyla (aynı
    group_by ile çağrıldığında) BİREBİR aynı formatı üretir — aksi halde
    lookup hiçbir zaman eşleşmez."""
    parts = []
    for field in group_by:
        if field == "confidence":
            parts.append(_confidence_bucket(context.get("confidence") or 0.0))
        else:
            parts.append(str(context.get(field, "unknown")))
    return "|".join(f"{field}={value}" for field, value in zip(group_by, parts))


def recommend_barrier(
    context: dict,
    barrier_table: dict,
    group_by: tuple[str, ...] = ("direction", "regime", "volatility_regime"),
) -> dict | None:
    """context: GÜNCEL bir kararın koşulları (ör. {"direction": "LONG",
    "regime": "bull_trend", "volatility_regime": "high", "confidence": 0.72}).
    barrier_table: compute_optimal_barrier()'ın ÖNCEDEN, AYNI group_by ile
    hesaplanmış çıktısı. Eşleşen kova yoksa (yeterli geçmiş veri
    birikmemiş bir koşul kombinasyonu) fail-closed None döner — icat
    edilmiş bir SL/TP önerisi asla üretilmez."""
    key = _build_lookup_key(context, group_by)
    return barrier_table.get(key)
