"""Faz 188: trading_mode (test/live) + max_concurrent_positions/max_capital_pct
— RiskEngine'in gerçekten bu ayarları uyguladığını doğrular."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.risk import RiskLimitEntry
from engines.risk_engine import RiskEngine


def _ctx(direction="LONG", size=0.3):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "TESTSYM"
    ctx.decision.proposed_direction = direction
    ctx.decision.proposed_size = size
    return ctx


def test_test_mode_now_rejects_with_no_limits_just_like_live():
    """Faz 262 — kritik bulgu: eski davranış (test modu MISSING_LIMIT dahil
    HER kontrolü atlardı) kasa/eşzamanlılık limitlerinin test modunda hiç
    uygulanmamasına yol açtı — Faz 261'in geniş hedef/stop oranıyla
    birleşince pozisyonlar günlerce açık kalıp 1074'e kadar birikti, kasa
    yapılandırılmış %5 limitin 3 katını aştı. Kullanıcı kararı: test modu
    artık live'la AYNI kuralları uyguluyor."""
    ctx = _ctx()
    ctx.risk.trading_mode = "test"
    ctx.risk.limits = {}  # artık live'la aynı: MISSING_LIMIT ile reddedilir

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MISSING_LIMIT" for r in result.risk.evaluation.reasons)


def test_test_mode_rejects_when_concurrent_position_limit_reached():
    ctx = _ctx()
    ctx.risk.trading_mode = "test"
    ctx.risk.limits = {"max_position_size": RiskLimitEntry(value=10.0)}
    ctx.risk.open_position_count = 3
    ctx.risk.max_concurrent_positions = 3

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MAX_CONCURRENT_POSITIONS" for r in result.risk.evaluation.reasons)


def test_test_mode_rejects_when_capital_pct_limit_reached():
    ctx = _ctx()
    ctx.risk.trading_mode = "test"
    ctx.risk.limits = {"max_position_size": RiskLimitEntry(value=10.0)}
    ctx.risk.capital_used_pct = 0.6
    ctx.risk.max_capital_pct = 0.5

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MAX_CAPITAL_PCT" for r in result.risk.evaluation.reasons)


def test_test_mode_approves_when_within_all_limits():
    ctx = _ctx()
    ctx.risk.trading_mode = "test"
    ctx.risk.limits = {"max_position_size": RiskLimitEntry(value=10.0)}
    ctx.risk.open_position_count = 2
    ctx.risk.max_concurrent_positions = 3
    ctx.risk.capital_used_pct = 0.1
    ctx.risk.max_capital_pct = 0.5

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
    ctx.risk.limits = {"max_position_size": RiskLimitEntry(value=10.0)}

    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "approved"


def test_default_trading_mode_is_live_when_not_explicitly_set():
    """RiskContext'in kendi Pydantic varsayılanı 'live' olmalı — mevcut testler
    (services/risk_state.py çağırmadan ctx.risk'i elle kuran) hâlâ tam
    kontrol yolunu egzersiz etmeye devam etsin, sessizce 'test' moduna
    düşmesinler."""
    ctx = _ctx()
    assert ctx.risk.trading_mode == "live"
