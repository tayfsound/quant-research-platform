"""Shadow Mode: Benched Ajan İtirazı testleri — bkz. services/
benched_agent_shadow_tracker.py. Kullanıcı isteği: "Benched ajan itirazını
gölge pozisyon testi." macro_shadow_tracker testleriyle AYNI desen —
council'i hiç etkilemeyen, izole bir gölge takipçi."""
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from contracts.agent import AgentDomain, AgentOpinion
from database.repositories.shadow_position_repository import ShadowPositionRepository
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services import benched_agent_shadow_tracker

_BENCHED_CAVEAT = "Devre dışı (benched): technical ajanının gerçek son isabet oranı düşük."


def _daily_bar(low: float, high: float, close: float) -> OHLCV:
    return OHLCV(timestamp=datetime.now(UTC), open=close, high=high, low=low, close=close, volume=1.0)


def _benched_opinion(domain: AgentDomain, direction: str, confidence: float = 0.7) -> AgentOpinion:
    op = AgentOpinion(domain=domain, direction=direction, confidence=confidence)
    op.caveats.append(_BENCHED_CAVEAT)
    op.performance_weight = 0.0
    return op


def _ctx(final_direction: str, opinions: list[AgentOpinion]):
    ctx = SimpleNamespace()
    ctx.decision = SimpleNamespace(proposed_direction=final_direction, final_action=final_direction)
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


def _wide_daily_bars():
    return [_daily_bar(95 + i * 0.1, 105 + i * 0.1, 100 + i * 0.1) for i in range(30)]


def test_opens_shadow_position_for_a_benched_agent_that_dissents_from_final_direction():
    symbol = f"BENCHOPEN{uuid4().hex[:6]}"
    ctx = _ctx("WAIT", [_benched_opinion(AgentDomain.TECHNICAL, "SHORT", confidence=0.8)])

    benched_agent_shadow_tracker.process_symbol_opinions(
        symbol, ctx, entry_price=100.0, data_provider=_FakeProvider(daily_bars=_wide_daily_bars())
    )

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        assert repo.has_open_position("benched_technical", symbol) is True


def test_does_nothing_when_benched_agent_agrees_with_final_direction():
    """İtiraz yoksa (benched ajan zaten final kararla AYNI yönde) gölge
    pozisyon açılmamalı — burada ölçülen şey SADECE itiraz."""
    symbol = f"BENCHAGREE{uuid4().hex[:6]}"
    ctx = _ctx("LONG", [_benched_opinion(AgentDomain.TECHNICAL, "LONG", confidence=0.8)])

    benched_agent_shadow_tracker.process_symbol_opinions(
        symbol, ctx, entry_price=100.0, data_provider=_FakeProvider(daily_bars=_wide_daily_bars())
    )

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        assert repo.has_open_position("benched_technical", symbol) is False


def test_does_nothing_when_dissenting_agent_is_not_actually_benched():
    """Normal (benched OLMAYAN) bir itiraz zaten MetaStage'in kendi WAIT
    kapısına giriyor — burası SADECE benched itirazları ölçmeli."""
    symbol = f"BENCHNOTBENCHED{uuid4().hex[:6]}"
    normal_dissent = AgentOpinion(domain=AgentDomain.TECHNICAL, direction="SHORT", confidence=0.8)
    ctx = _ctx("LONG", [normal_dissent])

    benched_agent_shadow_tracker.process_symbol_opinions(
        symbol, ctx, entry_price=100.0, data_provider=_FakeProvider(daily_bars=_wide_daily_bars())
    )

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        assert repo.has_open_position("benched_technical", symbol) is False


def test_tracks_multiple_dissenting_benched_domains_separately():
    symbol = f"BENCHMULTI{uuid4().hex[:6]}"
    ctx = _ctx("WAIT", [
        _benched_opinion(AgentDomain.TECHNICAL, "SHORT", confidence=0.8),
        _benched_opinion(AgentDomain.PATTERN, "LONG", confidence=0.6),
    ])

    benched_agent_shadow_tracker.process_symbol_opinions(
        symbol, ctx, entry_price=100.0, data_provider=_FakeProvider(daily_bars=_wide_daily_bars())
    )

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        assert repo.has_open_position("benched_technical", symbol) is True
        assert repo.has_open_position("benched_pattern", symbol) is True


def test_does_not_open_a_second_position_for_the_same_symbol_and_domain():
    symbol = f"BENCHDUP{uuid4().hex[:6]}"
    ctx = _ctx("WAIT", [_benched_opinion(AgentDomain.TECHNICAL, "SHORT", confidence=0.8)])
    provider = _FakeProvider(daily_bars=_wide_daily_bars())

    benched_agent_shadow_tracker.process_symbol_opinions(symbol, ctx, entry_price=100.0, data_provider=provider)
    benched_agent_shadow_tracker.process_symbol_opinions(symbol, ctx, entry_price=101.0, data_provider=provider)

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        open_positions = [p for p in repo.list_open(source="benched_technical") if p.symbol == symbol]
        assert len(open_positions) == 1


def test_close_due_positions_closes_a_benched_shadow_position_on_take_profit():
    from contracts.shadow_position import ShadowPosition

    symbol = f"BENCHCLOSE{uuid4().hex[:6]}"
    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        position = ShadowPosition(
            source="benched_technical", symbol=symbol, direction="LONG",
            entry_price=100.0, stop_loss_price=90.0, take_profit_price=110.0,
        )
        repo.open_position(position)

    from unittest.mock import patch
    with patch("market_data.ingestion.data_provider.RoutingProvider") as MockProvider:
        MockProvider.return_value = _FakeProvider(live_price=115.0)
        closed = benched_agent_shadow_tracker.close_due_positions()

    matching = [c for c in closed if c["symbol"] == symbol]
    assert len(matching) == 1
    assert matching[0]["exit_reason"] == "take_profit"
    assert matching[0]["source"] == "benched_technical"

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        assert repo.has_open_position("benched_technical", symbol) is False


def test_list_active_sources_returns_only_benched_sources():
    symbol = f"BENCHSRC{uuid4().hex[:6]}"
    ctx = _ctx("WAIT", [_benched_opinion(AgentDomain.QUANT, "SHORT", confidence=0.8)])
    benched_agent_shadow_tracker.process_symbol_opinions(
        symbol, ctx, entry_price=100.0, data_provider=_FakeProvider(daily_bars=_wide_daily_bars())
    )

    sources = benched_agent_shadow_tracker.list_active_sources()
    assert "benched_quant" in sources
    assert all(s.startswith("benched_") for s in sources)
