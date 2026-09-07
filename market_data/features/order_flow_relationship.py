"""OI + Funding + Price BİRLİKTE İlişkisi — Faz 436 (kullanıcı önceliği
①, 2026-09-07). Bkz. /Users/emreturkes/.claude/plans/velvety-whistling-
parasol.md.

Bağlam: `agents/order_flow_agent.py`'de `funding_rate` Faz 411'de TEK
BAŞINA gürültü bulunup kaldırılmıştı; `open_interest_trend` sadece kaba
3 kategori (rising/falling/stable), fiyat yönüyle HİÇ birlikte
değerlendirilmiyor. Kullanıcının iddiası: price↑/OI↑/funding↑ (yeni
para uzun pozisyona giriyor, pahalıya da olsa) ile price↑/OI↓ (kısa
pozisyonlar kapanıyor, "short covering" — yeni bir yükseliş bahsi
DEĞİL) AYNI "bullish momentum" değil. Bu modül bu üçlüyü BİRLİKTE
sınıflandırıyor — ne funding_rate ne open_interest tek başına kanıtlanmış
DEĞİLDİ, bu üçlünün birlikte anlamlı olup olmadığı HENÜZ TEST EDİLMEDİ.

Kasıtlı olarak SADECE gözlem — `services/orchestrator.py` bu çıktıyı
`ctx.market.features`'a ekliyor (her kararın `market_snapshot`
katkısında otomatik görünür hale geliyor), hiçbir agent'ın skoruna
GİRMİYOR. Haftalar sonra gerçek IC/win-rate kanıtı birikince wire etme
kararı AYRI bir onay turu (agent_combination_reliability.py'nin FDR+
OOS+min_distinct_days iskeletiyle, tıpkı wyckoff_event/Market State
gibi)."""

DEFAULT_PRICE_CHANGE_THRESHOLD = 0.001   # %0.1 — anlamlı fiyat hareketi tabanı
DEFAULT_OI_CHANGE_THRESHOLD = 0.02       # open_interest_trend ile AYNI eşik (pipeline.py)

_CATEGORIES = (
    "bullish_new_longs", "bullish_short_covering",
    "bearish_new_shorts", "bearish_long_capitulation", "unclear",
)


def _mid_price(snapshot: dict) -> float | None:
    bid = snapshot.get("best_bid")
    ask = snapshot.get("best_ask")
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return None
    return (bid + ask) / 2.0


def compute_order_flow_relationship(
    snapshots: list[dict],
    price_change_threshold: float = DEFAULT_PRICE_CHANGE_THRESHOLD,
    oi_change_threshold: float = DEFAULT_OI_CHANGE_THRESHOLD,
) -> dict | None:
    """snapshots: `market_data_repository.py::get_recent_order_book_
    snapshots()`'ın döndürdüğü şekilde (`time` alanlı, herhangi bir
    sırada) satırlar — HERHANGİ bir sırada olabilir, burada zaman
    sırasına göre (en eskiden en yeniye) yeniden sıralanır. En az 2
    gerçek (fiyat hesaplanabilir) kayıt gerekir, aksi halde fail-closed
    None — icat edilmiş bir sınıflandırma asla üretilmez. Vadeli
    kontratı olmayan bir sembolde (open_interest/funding_rate hep None)
    "unclear" döner — bug değil, gerçek bilgi eksikliği."""
    dated = sorted(
        (s for s in snapshots if s.get("time") is not None),
        key=lambda s: s["time"],
    )
    if len(dated) < 2:
        return None

    earliest, latest = dated[0], dated[-1]
    price_earliest = _mid_price(earliest)
    price_latest = _mid_price(latest)
    if price_earliest is None or price_latest is None or price_earliest == 0:
        return None

    price_change_pct = (price_latest - price_earliest) / price_earliest

    oi_earliest = earliest.get("open_interest")
    oi_latest = latest.get("open_interest")
    oi_change_pct = None
    if oi_earliest is not None and oi_latest is not None and oi_earliest != 0:
        oi_change_pct = (oi_latest - oi_earliest) / oi_earliest

    funding_rate = latest.get("funding_rate")

    category = "unclear"
    if oi_change_pct is not None:
        price_up = price_change_pct > price_change_threshold
        price_down = price_change_pct < -price_change_threshold
        oi_up = oi_change_pct > oi_change_threshold
        oi_down = oi_change_pct < -oi_change_threshold
        if price_up and oi_up:
            category = "bullish_new_longs"
        elif price_up and oi_down:
            category = "bullish_short_covering"
        elif price_down and oi_up:
            category = "bearish_new_shorts"
        elif price_down and oi_down:
            category = "bearish_long_capitulation"

    return {
        "category": category,
        "price_change_pct": round(price_change_pct, 6),
        "oi_change_pct": round(oi_change_pct, 6) if oi_change_pct is not None else None,
        "funding_rate": funding_rate,
        "n_snapshots": len(dated),
        "window_start": earliest["time"].isoformat() if hasattr(earliest["time"], "isoformat") else earliest["time"],
        "window_end": latest["time"].isoformat() if hasattr(latest["time"], "isoformat") else latest["time"],
    }
