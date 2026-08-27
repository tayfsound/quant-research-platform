"""Backlog #49 (Faz 365) — Binance Futures'ın gerçek, ücretsiz zorunlu-
kapanış (forceOrder) akışından likidasyon baskısı sorgu katmanı.

`binance_liquidation_listener.py` (ayrı, kalıcı süreç) ham olayları
`liquidation_events` tablosuna yazar; bu modül SADECE okuma/toplama
yapar — `market_data/onchain/onchain_provider.py`'nin fetch_* deseniyle
AYNI: saf, gerçek veriden hesaplanan fonksiyonlar, hiçbir yön/skor
kararı vermiyor (o karar, henüz yazılmamış ajan katmanının işi)."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from database.session_factory import SessionFactory


def fetch_liquidation_pressure(symbol: str, window_minutes: int = 60) -> dict:
    """Verilen sembolde son `window_minutes` içinde LONG/SHORT tarafında
    likide edilen toplam notional ($) — gerçek veri yoksa (henüz hiç
    olay birikmemişse) ikisi de 0.0, icat edilmiş bir varsayım YOK."""
    since = datetime.now(UTC) - timedelta(minutes=window_minutes)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                """
                SELECT liquidated_side, COALESCE(SUM(notional_usd), 0.0), COUNT(*)
                FROM liquidation_events
                WHERE symbol = :symbol AND time >= :since
                GROUP BY liquidated_side
                """
            ),
            {"symbol": symbol.upper(), "since": since},
        ).fetchall()

    long_notional = 0.0
    short_notional = 0.0
    long_count = 0
    short_count = 0
    for side, notional, count in rows:
        if side == "LONG":
            long_notional = float(notional)
            long_count = int(count)
        elif side == "SHORT":
            short_notional = float(notional)
            short_count = int(count)

    return {
        "symbol": symbol.upper(),
        "window_minutes": window_minutes,
        "long_liquidated_usd": round(long_notional, 2),
        "long_liquidation_count": long_count,
        "short_liquidated_usd": round(short_notional, 2),
        "short_liquidation_count": short_count,
    }


def total_event_count() -> int:
    """Ham satır sayısı — dinleyici sürecinin gerçekten veri biriktirip
    biriktirmediğini doğrulamak için (testler/manuel kontrol)."""
    with SessionFactory.get_session() as session:
        return session.execute(text("SELECT COUNT(*) FROM liquidation_events")).scalar_one()
