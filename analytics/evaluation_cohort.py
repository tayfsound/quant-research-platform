"""Faz 400 (2026-09-01) — Canonical Evaluation Cohort, Faz 0.

Dış mimari raporunun (2026-08-21) bulduğu, bu turda kod üzerinden yeniden
doğrulanan gerçek sorun: `analytics/`/`services/*_gatherer.py` altındaki
~20 modülün HEPSİ `DecisionPersistor.list_closed_trades()`'i (aynı,
kanonik kaynak) çağırıyor ama farklı `limit` (500/600/2000/3000/5000/
100000/sınırsız) ve farklı dışlama katmanlarıyla (`exclude_experiment_
bucket='pump_fade_v1'`, bazılarında ek bir `_is_production_ai_council`
filtresi). Bu matematiksel olarak açıklanabilir (her modülün kendi
istatistiksel ihtiyacı farklı) ama dashboard/rapor okuyan kullanıcı için
riskli — iki farklı N'i "aynı anki sistemin aynı ölçümü" sanabilir.

Bu modül farklılıkları ORTADAN KALDIRMIYOR (her modülün kendi limit/
filtre seçimi kasıtlı ve kalıyor) — sadece HERHANGİ bir raporun/gatherer'ın
"bu sayı hangi pencereden geldi" sorusuna her zaman AYNI şekilde
cevap vermesini sağlıyor, tek bir paylaşılan yardımcı fonksiyonla."""
from datetime import datetime


def describe_evaluation_window(
    trades: list[dict],
    *,
    limit: int | None,
    exclude_experiment_buckets: list[str] | None = None,
    production_ai_council_filtered: bool = False,
) -> dict:
    """`trades`: `DecisionPersistor.list_closed_trades()`'in (ya da onun
    üzerine ek post-filtre uygulanmış bir listenin) döndürdüğü ham satırlar
    — bu fonksiyon hiçbir DB sorgusu yapmıyor, sadece çağıranın ZATEN
    uyguladığı seçim kriterlerini ve elde edilen GERÇEK sonucu tek tip bir
    blokta özetliyor. `closed_at` alanı olmayan/None olan satırlar en-eski/
    en-yeni hesabında yok sayılır (fail-closed — icat edilmiş bir tarih
    asla üretilmez)."""
    closed_ats = [t.get("closed_at") for t in trades if t.get("closed_at") is not None]

    def _iso(dt) -> str | None:
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt.isoformat()
        return str(dt)

    return {
        "n_trades": len(trades),
        "limit": limit,
        "exclude_experiment_buckets": list(exclude_experiment_buckets or []),
        "production_ai_council_filtered": production_ai_council_filtered,
        "earliest_closed_at": _iso(min(closed_ats)) if closed_ats else None,
        "latest_closed_at": _iso(max(closed_ats)) if closed_ats else None,
    }
