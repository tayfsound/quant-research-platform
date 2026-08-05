"""Faz 187: gerçek pozisyon yaşam döngüsü — açılış (DecisionRecorder)
ve kapanış (PositionCloser), backtest tarzı anlık ForwardOutcome'dan ayrı."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.data_provider import MockProvider
from services.position_closer import PositionCloser


def test_risk_approved_directional_decision_opens_a_real_position_with_entry_price_and_no_pnl_yet():
    """DecisionRecorder seviyesinde, doğrudan: gerçek Council'in (boş ctx.market
    ile hep WAIT üretmesi — ayrı, bilinen bir davranış) değişkenliğine bağlı
    kalmadan, risk-onaylı yönlü bir karar geldiğinde DecisionPersistor'ın
    gerçekten 'open' bir pozisyon satırı yazdığını doğrular."""
    from unittest.mock import patch

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from contracts.context import CognitiveCycleContext
        from services.decision_recorder import DecisionRecorder

        symbol = f"POSLIFE{uuid4().hex[:8]}"
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.decision.proposed_direction = "LONG"
        ctx.decision.final_size = 0.3
        ctx.decision.filled_price = 27123.45
        ctx.risk.evaluation.verdict = "approved"

        DecisionRecorder().record(ctx)

    with SessionFactory.get_session() as session:
        rows = DecisionPersistor(session).list_open_positions(limit=200)
    matches = [r for r in rows if r["symbol"] == symbol]

    assert matches
    pos = matches[0]
    assert pos["status"] == "open"
    assert pos["entry_price"] == 27123.45
    assert pos["quantity"] == 0.3
    assert pos["opened_at"] is not None
    assert pos["pnl"] is None
    assert pos["exit_price"] is None


def test_wait_decision_never_opens_a_position():
    from unittest.mock import patch

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from contracts.context import CognitiveCycleContext
        from services.decision_recorder import DecisionRecorder

        symbol = f"POSNOTRADE{uuid4().hex[:8]}"
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.decision.proposed_direction = "WAIT"
        ctx.decision.final_size = 0.0
        ctx.risk.evaluation.verdict = "approved"

        DecisionRecorder().record(ctx)

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(ctx.cycle_id))

    assert row["status"] == "no_trade"
    assert row["entry_price"] is None
    assert row["opened_at"] is None


def test_risk_rejected_directional_decision_never_opens_a_position():
    from unittest.mock import patch

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from contracts.context import CognitiveCycleContext
        from services.decision_recorder import DecisionRecorder

        symbol = f"POSREJECTED{uuid4().hex[:8]}"
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.decision.proposed_direction = "LONG"
        ctx.decision.final_size = 0.3
        ctx.decision.filled_price = 100.0
        ctx.risk.evaluation.verdict = "rejected"

        DecisionRecorder().record(ctx)

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(ctx.cycle_id))

    assert row["status"] == "no_trade"
    assert row["entry_price"] is None


def test_position_closer_closes_only_positions_past_hold_duration_with_real_exit_price():
    symbol = f"POSCLOSE{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        from contracts.decision_event import DecisionEvent

        old_event = DecisionEvent(
            id=uuid4(),
            timestamp=now - timedelta(minutes=20),
            symbol=symbol,
            proposed_direction="LONG",
            final_action="LONG",
            final_size=1.0,
            confidence=0.7,
            status="open",
            entry_price=100.0,
            quantity=2.0,
            opened_at=now - timedelta(minutes=20),
        )
        fresh_event = DecisionEvent(
            id=uuid4(),
            timestamp=now,
            symbol=symbol,
            proposed_direction="LONG",
            final_action="LONG",
            final_size=1.0,
            confidence=0.7,
            status="open",
            entry_price=100.0,
            quantity=2.0,
            opened_at=now,
        )
        repo = DecisionPersistor(session)
        repo.persist(old_event)
        repo.persist(fresh_event)

    closer = PositionCloser(MockProvider(seed=1), hold_seconds=600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    closed_ids = {c["decision_id"] for c in closed}
    assert str(old_event.id) in closed_ids
    assert str(fresh_event.id) not in closed_ids

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(old_event.id))
    assert row["status"] == "closed"
    assert row["exit_price"] is not None
    assert row["pnl"] is not None
    assert row["closed_at"] is not None

    with SessionFactory.get_session() as session:
        still_open = DecisionPersistor(session).get_by_id(str(fresh_event.id))
    assert still_open["status"] == "open"


class _FixedPriceProvider:
    """Faz 192 testleri için: MockProvider'ın rastgele yürüyüşü yerine
    kontrollü bir güncel fiyat döndürür."""
    def __init__(self, price: float):
        self.price = price

    def get_ohlcv(self, symbol, timeframe, limit=1):
        from market_data.ingestion.ohlcv import OHLCV
        now = datetime.now(UTC)
        return [OHLCV(timestamp=now, open=self.price, high=self.price, low=self.price, close=self.price, volume=1.0)]


def test_position_closer_closes_immediately_on_take_profit_before_hold_expires():
    from contracts.decision_event import DecisionEvent

    symbol = f"POSTPHIT{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=90.0, take_profit_price=110.0,
        )
        DecisionPersistor(session).persist(event)

    # hold_seconds çok uzun (1 saat) — sadece TP'nin vadeyi beklemeden
    # kapattığını kanıtlamak için.
    closer = PositionCloser(_FixedPriceProvider(111.0), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    closed_ids = {c["decision_id"]: c for c in closed}
    assert str(event.id) in closed_ids
    assert closed_ids[str(event.id)]["exit_reason"] == "take_profit"

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "closed"
    assert row["exit_price"] == 111.0
    assert row["pnl"] > 0


def test_position_closer_closes_immediately_on_stop_loss_before_hold_expires():
    from contracts.decision_event import DecisionEvent

    symbol = f"POSSLHIT{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="SHORT", final_action="SHORT", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=110.0, take_profit_price=80.0,
        )
        DecisionPersistor(session).persist(event)

    closer = PositionCloser(_FixedPriceProvider(112.0), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    closed_ids = {c["decision_id"]: c for c in closed}
    assert str(event.id) in closed_ids
    assert closed_ids[str(event.id)]["exit_reason"] == "stop_loss"

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["pnl"] < 0


def test_position_closer_does_not_close_when_price_between_stop_and_target_and_hold_not_expired():
    from contracts.decision_event import DecisionEvent

    symbol = f"POSNOTRIGGER{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=90.0, take_profit_price=110.0,
        )
        DecisionPersistor(session).persist(event)

    closer = PositionCloser(_FixedPriceProvider(103.0), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    assert str(event.id) not in {c["decision_id"] for c in closed}

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "open"
