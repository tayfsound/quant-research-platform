"""Faz 268-sonrası: perpetual pozisyon tutma maliyeti (funding rate).

Gerçek bulgu: FeeEngine sadece giriş/çıkış maker/taker ücretini
hesaplıyordu (Faz 223) — ama gerçek bir perpetual futures pozisyonu,
her 8 saatlik funding settlement'ında long/short taraflar arasında
gerçek bir nakit akışı yaşar (overnight carry yok ama funding var).
Pozisyon günler/haftalar açık kalabildiği için (Faz 215: vade dolunca
zorla kapatma yok) bu, giriş/çıkış ücretinden bile büyük bir maliyet
kalemine dönüşebilir.

market_data/ingestion/pipeline.py::ingest_order_book zaten her ~20sn'de
bir GERÇEK funding_rate'i order_book_snapshots'a yazıyor (Faz 247-249) —
bu modül icat edilmiş bir sabit ORAN kullanmıyor, pozisyonun GERÇEKTEN
açık kaldığı pencerede kaydedilmiş gerçek değerlerin ortalamasını kullanıyor."""
from datetime import datetime

SETTLEMENT_INTERVAL_HOURS = 8


def compute_funding_cost(
    symbol: str,
    direction: str,
    notional: float,
    opened_at: datetime,
    closed_at: datetime,
) -> float:
    """LONG, pozitif funding rate'te ÖDER (maliyet pozitif — pnl'den
    düşülür); SHORT alır (maliyet negatif — pnl'e eklenir) — gerçek
    perpetual futures mekaniğiyle aynı yön. Vadeli kontratı olmayan bir
    sembolde (gerçek funding_rate kaydı hiç yoksa) ya da pozisyon bir
    settlement'tan daha kısa açık kaldıysa 0.0 döner — fail-closed,
    icat edilmiş bir maliyet asla uygulanmaz."""
    hold_seconds = (closed_at - opened_at).total_seconds()
    if hold_seconds <= 0:
        return 0.0

    num_settlements = int(hold_seconds // (SETTLEMENT_INTERVAL_HOURS * 3600))
    if num_settlements == 0:
        return 0.0

    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(text("""
            SELECT funding_rate FROM order_book_snapshots
            WHERE symbol = :symbol AND time >= :opened_at AND time <= :closed_at
                AND funding_rate IS NOT NULL
        """), {"symbol": symbol, "opened_at": opened_at, "closed_at": closed_at}).fetchall()

    if not rows:
        return 0.0

    avg_funding_rate = sum(r[0] for r in rows) / len(rows)
    sign = 1.0 if direction.upper() == "LONG" else -1.0
    return notional * avg_funding_rate * num_settlements * sign
