"""Çoklu Ufuk Yön Etiketleme — Faz 444 (2026-09-07). Bkz.
/Users/emreturkes/.claude/plans/velvety-whistling-parasol.md.

Bağlam: GPT'nin 4 numaralı önceliği — "Bir sinyal 15dk'da DOWN, 1sa'te
UP, 4sa'te UP olabilir. Bunu tek bir LONG/SHORT etiketiyle sıkıştırırsan
model cevabı olmayan bir soru öğreniyor." Bu modül `analytics.forward_
direction.label_forward_direction()`'ı YENİDEN İCAT ETMİYOR — AYNI saf
fonksiyonu üç farklı ufuk fiyatıyla çağırıp sonuçları TEK bir kararda
karşılaştırıyor.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir canlı kararı etkilemiyor."""
from analytics.forward_direction import label_forward_direction

HORIZONS = ("15m", "1h", "4h")


def label_multi_horizon(
    entry_price: float | None,
    prices_by_horizon: dict[str, float | None],
    threshold_pct: float = 0.0005,
) -> dict:
    """prices_by_horizon: {'15m': fiyat|None, '1h': fiyat|None, '4h':
    fiyat|None} — her biri o ufukta GERÇEKLEŞEN piyasa fiyatı (trade'in
    kendi stop/target'ından bağımsız). Her ufuk için AYRI AYRI
    label_forward_direction() çağrılıyor (fail-closed None, veri
    eksikse). `directional_horizons`: NEUTRAL/None olmayan (yani UP ya
    da DOWN diyen) ufukların etiketleri — `all_agree` SADECE bunlar
    arasında değerlendiriliyor (en az 2 yönlü ufuk gerekir, aksi halde
    None — "katılmıyorlar" demek için en az iki gerçek görüş gerekir)."""
    labels = {
        h: label_forward_direction(entry_price, prices_by_horizon.get(h), threshold_pct)
        for h in HORIZONS
    }
    directional = {h: v for h, v in labels.items() if v in ("UP", "DOWN")}

    all_agree = None
    if len(directional) >= 2:
        all_agree = len(set(directional.values())) == 1

    return {
        "labels": labels,
        "all_agree": all_agree,
        "disagreement": (all_agree is False),
    }


def compute_disagreement_rate(records: list[dict], threshold_pct: float = 0.0005) -> dict | None:
    """records: her biri {'entry_price', 'price_15m', 'price_1h',
    'price_4h'} olan GERÇEK kapanmış kararlar. En az 2 ufkun yön
    verebildiği kayıtlar arasında, ufukların GERÇEKTEN anlaştığı/
    anlaşmadığı yüzdeyi + örnek uyuşmazlıkları döner. <10 karşılaştırılabilir
    kayıtla fail-closed None."""
    comparable = []
    for r in records:
        prices = {"15m": r.get("price_15m"), "1h": r.get("price_1h"), "4h": r.get("price_4h")}
        result = label_multi_horizon(r.get("entry_price"), prices, threshold_pct)
        if result["all_agree"] is not None:
            comparable.append((r, result))

    if len(comparable) < 10:
        return None

    disagreements = [(r, res) for r, res in comparable if res["disagreement"]]

    return {
        "n_comparable": len(comparable),
        "n_disagreements": len(disagreements),
        "disagreement_rate": round(len(disagreements) / len(comparable), 4),
        "example_disagreements": [
            {"symbol": r.get("symbol"), "labels": res["labels"]}
            for r, res in disagreements[:5]
        ],
    }
