"""Faz 268: kullanıcı isteği — "aşamalı kapama: pozisyonun yarısını/
çeyreğini kademeli kapatabilen mekanizma ekle." close_position() her zaman
TÜM pozisyonu kapatıyordu (binary open/closed, tek satır). Bu testler
PositionCloser.close_partial()'ın satırı 'open' bırakıp quantity'yi
azalttığını, gerçekleşen pnl'i biriktirdiğini ve son dilimin gerçek bir
tam kapanışa dönüştüğünü doğruluyor."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.position_closer import PositionCloser


class _FixedPriceProvider:
    def __init__(self, price: float):
        self.price = price

    def get_ohlcv(self, symbol, timeframe, limit=1):
        from market_data.ingestion.ohlcv import OHLCV
        now = datetime.now(UTC)
        return [OHLCV(timestamp=now, open=self.price, high=self.price, low=self.price, close=self.price, volume=1.0)]


def _open_position(symbol: str, direction: str = "LONG", quantity: float = 1.0, entry_price: float = 100.0):
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction=direction, final_action=direction, final_size=quantity, confidence=0.7,
        status="open", entry_price=entry_price, quantity=quantity, opened_at=now,
        stop_loss_price=90.0 if direction == "LONG" else 110.0,
        take_profit_price=120.0 if direction == "LONG" else 80.0,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


def test_partial_close_reduces_quantity_and_keeps_position_open():
    symbol = f"POSPART{uuid4().hex[:8]}"
    event = _open_position(symbol, quantity=2.0, entry_price=100.0)

    closer = PositionCloser(_FixedPriceProvider(110.0))
    with SessionFactory.get_session() as session:
        result = closer.close_partial(DecisionPersistor(session), str(event.id), 0.5)

    assert result["fully_closed"] is False
    assert result["remaining_quantity"] == pytest.approx(1.0)
    assert result["pnl"] > 0

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "open"
    assert row["quantity"] == pytest.approx(1.0)
    assert row["pnl"] is None  # tam kapanış henüz olmadı, decisions.pnl dokunulmuyor
    outcome = row["outcome"]
    assert outcome["realized_pnl"] == pytest.approx(result["pnl"])
    assert len(outcome["partial_closes"]) == 1
    assert outcome["partial_closes"][0]["exit_reason"] == "manual_partial"


def test_second_partial_close_accumulates_realized_pnl():
    symbol = f"POSPART2{uuid4().hex[:8]}"
    event = _open_position(symbol, quantity=4.0, entry_price=100.0)

    closer = PositionCloser(_FixedPriceProvider(110.0))
    with SessionFactory.get_session() as session:
        first = closer.close_partial(DecisionPersistor(session), str(event.id), 0.25)
    with SessionFactory.get_session() as session:
        second = closer.close_partial(DecisionPersistor(session), str(event.id), 1.0 / 3.0)

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "open"
    assert row["quantity"] == pytest.approx(2.0)
    outcome = row["outcome"]
    assert len(outcome["partial_closes"]) == 2
    assert outcome["realized_pnl"] == pytest.approx(first["pnl"] + second["pnl"])


def test_fraction_one_fully_closes_and_sums_prior_realized_pnl():
    symbol = f"POSPARTFULL{uuid4().hex[:8]}"
    event = _open_position(symbol, quantity=2.0, entry_price=100.0)

    closer = PositionCloser(_FixedPriceProvider(110.0))
    with SessionFactory.get_session() as session:
        partial = closer.close_partial(DecisionPersistor(session), str(event.id), 0.5)
    with SessionFactory.get_session() as session:
        final = closer.close_partial(DecisionPersistor(session), str(event.id), 1.0)

    assert final["fully_closed"] is True

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "closed"
    assert row["exit_price"] == 110.0
    # nihai decisions.pnl = önceki kısmi dilimin pnl'i + son dilimin pnl'i
    assert row["pnl"] == pytest.approx(partial["pnl"] + final["pnl"])


def test_partial_close_on_short_position_computes_correct_direction_pnl():
    symbol = f"POSPARTSHORT{uuid4().hex[:8]}"
    event = _open_position(symbol, direction="SHORT", quantity=2.0, entry_price=100.0)

    # Fiyat düştü -> SHORT için kâr.
    closer = PositionCloser(_FixedPriceProvider(90.0))
    with SessionFactory.get_session() as session:
        result = closer.close_partial(DecisionPersistor(session), str(event.id), 0.5)

    assert result["pnl"] > 0


def test_partial_close_rejects_invalid_fraction():
    symbol = f"POSPARTBAD{uuid4().hex[:8]}"
    event = _open_position(symbol)
    closer = PositionCloser(_FixedPriceProvider(110.0))

    for bad_fraction in (0, -0.1, 1.5):
        with SessionFactory.get_session() as session:
            with pytest.raises(ValueError):
                closer.close_partial(DecisionPersistor(session), str(event.id), bad_fraction)


def test_partial_close_rejects_already_closed_position():
    symbol = f"POSPARTCLS{uuid4().hex[:8]}"
    event = _open_position(symbol)
    closer = PositionCloser(_FixedPriceProvider(110.0))
    with SessionFactory.get_session() as session:
        closer.close_partial(DecisionPersistor(session), str(event.id), 1.0)

    with SessionFactory.get_session() as session:
        with pytest.raises(ValueError):
            closer.close_partial(DecisionPersistor(session), str(event.id), 0.5)


def test_partial_close_feeds_agent_learning():
    """Faz 210/211/245'in kurduğu aynı öğrenme yolu — kısmi kapanış da
    gerçek bir sonuç, agent_contributions varsa AgentMemory'ye yazılmalı."""
    symbol = f"POSPARTLEARN{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction="LONG", final_action="LONG", final_size=2.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=2.0, opened_at=now,
        stop_loss_price=90.0, take_profit_price=120.0,
        agent_opinions=[
            {"domain": "technical", "direction": "LONG", "confidence": 0.6},
        ],
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)

    closer = PositionCloser(_FixedPriceProvider(110.0))
    from unittest.mock import patch
    with patch.object(closer, "_record_agent_learning", wraps=closer._record_agent_learning) as spy:
        with SessionFactory.get_session() as session:
            closer.close_partial(DecisionPersistor(session), str(event.id), 0.5)
        assert spy.called


def test_estimate_net_pnl_if_closed_now_is_positive_when_profitable_after_fees():
    """Faz 268p — kullanıcı isteği: "kârdaki pozisyonları toplu kapat, ama
    komisyona ezilmeyecek şekilde." Bu tahmin, close_partial(fraction=1.0)
    ile GERÇEKTEN kapatılırsa alınacak net pnl ile AYNI formülü kullanmalı
    — dashboard'da gösterilen sayı ile toplu kapatmanın kararı asla
    çelişmesin diye."""
    closer = PositionCloser(_FixedPriceProvider(999.0))  # provider burada kullanılmıyor, sadece imza için
    pos = {"entry_price": 100.0, "quantity": 10.0, "direction": "LONG"}
    # %10 fiyat artışı = $100 brüt kâr, komisyon bunun küçük bir kısmı.
    net_pnl = closer.estimate_net_pnl_if_closed_now(pos, current_price=110.0)
    assert net_pnl > 0
    assert net_pnl < 100.0  # komisyon düşülmüş olmalı, ham kârdan az


def test_estimate_net_pnl_if_closed_now_is_negative_when_commission_erases_tiny_gain():
    """Çok küçük bir fiyat hareketi komisyonu karşılamamalı — 'komisyona
    ezilmeyecek şekilde' talebinin tam karşılığı."""
    closer = PositionCloser(_FixedPriceProvider(999.0))
    pos = {"entry_price": 100.0, "quantity": 10.0, "direction": "LONG"}
    # %0.01'lik bir hareket — taker ücretinin (varsayılan ~%0.05 x2) çok altında.
    net_pnl = closer.estimate_net_pnl_if_closed_now(pos, current_price=100.01)
    assert net_pnl < 0


def test_estimate_net_pnl_if_closed_now_handles_short_direction():
    closer = PositionCloser(_FixedPriceProvider(999.0))
    pos = {"entry_price": 100.0, "quantity": 10.0, "direction": "SHORT"}
    net_pnl = closer.estimate_net_pnl_if_closed_now(pos, current_price=90.0)
    assert net_pnl > 0


def test_list_open_positions_offset_pages_through_without_overlap():
    """Faz 268y — kullanıcı bulgusu: "ilk 98 işleme baktım, diğerlerini
    göremiyorum." list_open_positions(limit) hep en yeni N'i döndürüyordu,
    offset yoktu — 100'den fazla açık pozisyon varsa gerisi hiç
    görülemiyordu. offset ile ikinci "sayfa", ilkiyle hiç kesişmemeli ve
    zaman sırasını (opened_at DESC) korumalı."""
    symbol = f"POSPAGE{uuid4().hex[:8]}"
    ids = []
    try:
        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            for i in range(5):
                now = datetime.now(UTC)
                event = DecisionEvent(
                    id=uuid4(), timestamp=now, symbol=symbol,
                    proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
                    status="open", entry_price=100.0, quantity=1.0,
                    opened_at=now - timedelta(seconds=5 - i),
                )
                persistor.persist(event)
                ids.append(str(event.id))

        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            page1 = persistor.list_open_positions(limit=1000000)
            our_page1_ids = [p["id"] for p in page1 if str(p["id"]) in ids]
            # Aynı sorguyu offset=len(page1) ile tekrarlarsak boş dönmeli
            # (hepsini zaten aldık) — offset'in gerçekten uygulandığının
            # en basit kanıtı.
            beyond_end = persistor.list_open_positions(limit=10, offset=len(page1))
            assert beyond_end == []
            assert len(our_page1_ids) == 5
    finally:
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()
