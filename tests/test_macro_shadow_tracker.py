"""Shadow Mode (Macro-Only karşılaştırma) testleri — bkz. services/
macro_shadow_tracker.py. Kullanıcıyla üzerinde anlaşılan çerçeve: council'i
hiç etkilemeyen, SADECE macro'nun kendi yönüne göre sanal pozisyon açıp
kapatan izole bir gölge takipçi."""
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from contracts.agent import AgentDomain, AgentOpinion
from contracts.shadow_position import ShadowPosition
from database.repositories.shadow_position_repository import ShadowPositionRepository
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services import macro_shadow_tracker


def _daily_bar(low: float, high: float, close: float) -> OHLCV:
    return OHLCV(timestamp=datetime.now(UTC), open=close, high=high, low=low, close=close, volume=1.0)


def _ctx_with_macro_opinion(direction: str, confidence: float = 0.7):
    opinions = [
        AgentOpinion(domain=AgentDomain.MACRO, direction=direction, confidence=confidence),
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="WAIT", confidence=0.5),
    ]
    ctx = SimpleNamespace()
    ctx.__dict__["_last_opinions"] = opinions
    return ctx


class _FakeProvider:
    def __init__(self, daily_bars=None, live_price=None):
        self._daily_bars = daily_bars or []
        self._live_price = live_price

    def get_ohlcv(self, symbol, timeframe, limit=100):
        if timeframe == "1d":
            return self._daily_bars
        return [_daily_bar(self._live_price, self._live_price, self._live_price)] if self._live_price else []


def test_repository_open_has_open_and_close_roundtrip():
    symbol = f"SHADOWRT{uuid4().hex[:6]}"
    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        assert repo.has_open_position("macro", symbol) is False

        position = ShadowPosition(
            source="macro", symbol=symbol, direction="LONG", confidence=0.7,
            entry_price=100.0, stop_loss_price=95.0, take_profit_price=110.0,
        )
        repo.open_position(position)
        assert repo.has_open_position("macro", symbol) is True

        pnl_pct = repo.close_position(position.id, exit_price=105.0, exit_reason="take_profit", closed_at=datetime.now(UTC))
        assert pnl_pct == 0.05
        assert repo.has_open_position("macro", symbol) is False


def test_repository_comparison_summary_reflects_real_win_rate_and_drawdown():
    source = f"macrotest{uuid4().hex[:6]}"
    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)

        # Kazanan, sonra kaybeden -> win_rate %50, cumulative sıfıra yakın.
        for direction, entry, exit_price, reason in [
            ("LONG", 100.0, 110.0, "take_profit"),
            ("LONG", 100.0, 95.0, "stop_loss"),
        ]:
            position = ShadowPosition(
                source=source, symbol=f"SYM{uuid4().hex[:6]}", direction=direction,
                entry_price=entry, stop_loss_price=95.0, take_profit_price=110.0,
            )
            repo.open_position(position)
            repo.close_position(position.id, exit_price=exit_price, exit_reason=reason, closed_at=datetime.now(UTC))

        summary = repo.comparison_summary(source=source, min_sample_size=100)
        assert summary["closed_count"] == 2
        assert summary["win_rate"] == 0.5
        assert summary["sample_size_sufficient"] is False  # 2 < 100


def test_process_symbol_opinion_opens_shadow_position_when_macro_is_directional():
    symbol = f"SHADOWOPEN{uuid4().hex[:6]}"
    ctx = _ctx_with_macro_opinion("LONG", confidence=0.8)
    daily_bars = [_daily_bar(95 + i * 0.1, 105 + i * 0.1, 100 + i * 0.1) for i in range(30)]

    macro_shadow_tracker.process_symbol_opinion(
        symbol, ctx, entry_price=100.0, data_provider=_FakeProvider(daily_bars=daily_bars)
    )

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        assert repo.has_open_position("macro", symbol) is True


def test_process_symbol_opinion_does_nothing_when_macro_says_wait():
    symbol = f"SHADOWWAIT{uuid4().hex[:6]}"
    ctx = _ctx_with_macro_opinion("WAIT")

    macro_shadow_tracker.process_symbol_opinion(symbol, ctx, entry_price=100.0)

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        assert repo.has_open_position("macro", symbol) is False


def test_process_symbol_opinion_does_not_open_second_position_for_same_symbol():
    symbol = f"SHADOWDUP{uuid4().hex[:6]}"
    ctx = _ctx_with_macro_opinion("SHORT", confidence=0.75)
    daily_bars = [_daily_bar(95 + i * 0.1, 105 + i * 0.1, 100 + i * 0.1) for i in range(30)]
    provider = _FakeProvider(daily_bars=daily_bars)

    macro_shadow_tracker.process_symbol_opinion(symbol, ctx, entry_price=100.0, data_provider=provider)
    macro_shadow_tracker.process_symbol_opinion(symbol, ctx, entry_price=101.0, data_provider=provider)

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        open_positions = [p for p in repo.list_open(source="macro") if p.symbol == symbol]
        assert len(open_positions) == 1


def test_close_due_positions_closes_when_take_profit_hit():
    symbol = f"SHADOWCLOSE{uuid4().hex[:6]}"
    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        position = ShadowPosition(
            source="macro", symbol=symbol, direction="LONG",
            entry_price=100.0, stop_loss_price=90.0, take_profit_price=110.0,
        )
        repo.open_position(position)

    from unittest.mock import patch
    with patch("market_data.ingestion.data_provider.RoutingProvider") as MockProvider:
        MockProvider.return_value = _FakeProvider(live_price=115.0)
        closed = macro_shadow_tracker.close_due_positions()

    matching = [c for c in closed if c["symbol"] == symbol]
    assert len(matching) == 1
    assert matching[0]["exit_reason"] == "take_profit"

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        assert repo.has_open_position("macro", symbol) is False
