"""Faz 188: trading_mode (test/live) + max_concurrent_positions/max_capital_pct
— RiskEngine'in gerçekten bu ayarları uyguladığını doğrular."""
from engines.risk_engine import RiskEngine
from contracts.context import CognitiveCycleContext
from contracts.contexts.risk import RiskLimitEntry


def _ctx(direction="LONG", size=0.3):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "TESTSYM"
    ctx.decision.proposed_direction = direction
    ctx.decision.proposed_size = size
    return ctx


def test_test_mode_approves_even_with_no_limits_configured_at_all():
    ctx = _ctx()
    ctx.risk.trading_mode = "test"
    ctx.risk.limits = {}  # live modda MISSING_LIMIT ile reddedilirdi

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "approved"


def test_live_mode_rejects_when_concurrent_position_limit_reached():
    ctx = _ctx()
    ctx.risk.trading_mode = "live"
    ctx.risk.limits = {"max_position_size": RiskLimitEntry(value=10.0)}
    ctx.risk.open_position_count = 3
    ctx.risk.max_concurrent_positions = 3

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MAX_CONCURRENT_POSITIONS" for r in result.risk.evaluation.reasons)


def test_live_mode_approves_when_under_concurrent_position_limit():
    ctx = _ctx()
    ctx.risk.trading_mode = "live"
    ctx.risk.limits = {"max_position_size": RiskLimitEntry(value=10.0)}
    ctx.risk.open_position_count = 2
    ctx.risk.max_concurrent_positions = 3

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "approved"


def test_live_mode_rejects_when_capital_pct_limit_reached():
    ctx = _ctx()
    ctx.risk.trading_mode = "live"
    ctx.risk.limits = {"max_position_size": RiskLimitEntry(value=10.0)}
    ctx.risk.capital_used_pct = 0.6
    ctx.risk.max_capital_pct = 0.5

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MAX_CAPITAL_PCT" for r in result.risk.evaluation.reasons)


def test_ai_stopped_rejects_even_in_test_mode():
    ctx = _ctx()
    ctx.risk.trading_mode = "test"
    ctx.risk.ai_enabled = False

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "AI_STOPPED" for r in result.risk.evaluation.reasons)


def test_cooldown_rejects_even_in_test_mode():
    ctx = _ctx()
    ctx.risk.trading_mode = "test"
    ctx.risk.seconds_since_last_trade = 5.0
    ctx.risk.min_seconds_between_trades = 60

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "COOLDOWN_ACTIVE" for r in result.risk.evaluation.reasons)


def test_cooldown_passes_once_enough_time_has_elapsed():
    ctx = _ctx()
    ctx.risk.trading_mode = "test"
    ctx.risk.seconds_since_last_trade = 120.0
    ctx.risk.min_seconds_between_trades = 60

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "approved"


def test_default_trading_mode_is_live_when_not_explicitly_set():
    """RiskContext'in kendi Pydantic varsayılanı 'live' olmalı — mevcut testler
    (services/risk_state.py çağırmadan ctx.risk'i elle kuran) hâlâ tam
    kontrol yolunu egzersiz etmeye devam etsin, sessizce 'test' moduna
    düşmesinler."""
    ctx = _ctx()
    assert ctx.risk.trading_mode == "live"
