"""Faz 362-devam — kullanıcı isteği: "kör gidiyorum, geriye dönüp inceleme
yapamıyorum" (Transactions kapanmış işlemler tablosu 100 kayıtla sınırlıydı,
offset yoktu). list_closed_trades artık list_open_positions (Faz 268y) ile
AYNI offset desteğine sahip."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory


def _persist_closed(symbol: str, closed_at: datetime) -> str:
    # closed_at sadece close_position()'ın UPDATE'iyle yazılıyor -- persist()
    # bunu hiç kabul etmiyor (bkz. regime_reversal_guardian testlerindeki
    # AYNI iki-adımlı desen: önce "open" persist et, sonra kapat).
    event = DecisionEvent(
        id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
        final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
        opened_at=closed_at - timedelta(minutes=10),
    )
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        persistor.persist(event)
        persistor.close_position(
            decision_id=str(event.id), exit_price=105.0, pnl=5.0, closed_at=closed_at,
            outcome={"exit_reason": "take_profit", "pnl": 5.0},
        )
    return str(event.id)


def test_offset_skips_the_most_recent_n_and_returns_the_next_page():
    """Paylaşılan test DB'sinde başka satırlar (leftover state, bkz. proje
    hafızası) sıralamaya karışabiliyor — bu yüzden "en yeni N satır benim"
    varsaymak yerine, KENDİ satırlarımın global sırasını önce (büyük bir
    limit'le) tespit edip, tam O offset'ten sorgulayınca aynı sırayla
    geldiğini doğruluyoruz. Bu, offset semantiğini gerçekten test ediyor
    (leftover veriye karşı kırılgan değil)."""
    symbol = f"PGTEST{uuid4().hex[:8]}"
    base = datetime.now(UTC) + timedelta(days=36500)  # ~100 yil sonra -- pratikte cakisma imkansiz
    try:
        ids = [_persist_closed(symbol, base - timedelta(minutes=i)) for i in range(5)]
        # ids[0] en yeni (closed_at=base), ids[4] en eski

        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            # Kendi satirlarimin GLOBAL sirasini (rank) tespit et.
            full = persistor.list_closed_trades(limit=1000, offset=0)
        full_ids = [str(r["id"]) for r in full]
        my_ranks = [full_ids.index(i) for i in ids]
        assert my_ranks == sorted(my_ranks), "beklenmeyen sira -- closed_at DESC ihlali"

        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            first_page = persistor.list_closed_trades(limit=2, offset=my_ranks[0])
            second_page = persistor.list_closed_trades(limit=2, offset=my_ranks[2])

        assert [str(r["id"]) for r in first_page] == ids[:2]
        assert [str(r["id"]) for r in second_page] == ids[2:4]
    finally:
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM decisions WHERE symbol = :s"), {"s": symbol})
            session.commit()
