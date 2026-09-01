"""Faz 402 — Market State Confidence Eğimi'nin council_orchestrator.py::
deliberate()'deki uygulanması. tests/test_council_orchestrator.py'deki
MoE Regime Router testleriyle AYNI desen (aynı `_BULLISH_TECHNICAL`/
`_unbenched_annotate` yaklaşımı, izole kopya)."""
from agents.registry import AgentRegistry
from contracts.agent import AgentDomain
from contracts.macro import MacroContext
from contracts.technical import TechnicalContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.council_orchestrator import CouncilOrchestrator

_BULLISH_TECHNICAL = TechnicalContext(
    trend="bullish", momentum="strengthening", market_structure="higher_highs", volume_confirmation=True
)
_BEARISH_MACRO = MacroContext(inflation_trend="rising", liquidity_condition="tight", central_bank_bias="hawkish")

_REVERSING_LONG_FEATURES = {
    "long_term_trend_regime": "bull_trend", "volatility_regime": "normal",
    "regime_changepoint_detected": True, "hurst_exponent": 0.8,
}
_NOT_REVERSING_FEATURES = {
    "long_term_trend_regime": "bull_trend", "volatility_regime": "normal",
    "regime_changepoint_detected": False, "hurst_exponent": 0.8,
}


def _unbenched_annotate(opinions, symbol=None, regime=None):
    return [{"source_reliability": 0.8, "benched": False} for _ in opinions]


def _set_tilt_enabled(value: str) -> str:
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        original = repo.get("market_state_tilt_enabled")
        repo.set("market_state_tilt_enabled", value, updated_by="test")
    return original


def _restore_tilt_enabled(original: str) -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("market_state_tilt_enabled", original, updated_by="test")


def test_disabled_by_default_is_a_complete_noop(monkeypatch):
    original = _set_tilt_enabled("false")
    try:
        registry = AgentRegistry.create_default()
        orchestrator = CouncilOrchestrator(registry)
        monkeypatch.setattr(orchestrator.reliability_annotator, "annotate", _unbenched_annotate)

        _, opinions = orchestrator.deliberate(
            {AgentDomain.TECHNICAL: _BULLISH_TECHNICAL, AgentDomain.MACRO: _BEARISH_MACRO},
            market_features=_REVERSING_LONG_FEATURES,
        )
        assert not any("Market State" in c for o in opinions for c in o.caveats)
    finally:
        _restore_tilt_enabled(original)


def test_enabled_and_reversing_boosts_agreeing_and_discounts_opposing(monkeypatch):
    original = _set_tilt_enabled("true")
    try:
        registry = AgentRegistry.create_default()
        orchestrator = CouncilOrchestrator(registry)
        monkeypatch.setattr(orchestrator.reliability_annotator, "annotate", _unbenched_annotate)

        _, baseline_opinions = orchestrator.deliberate(
            {AgentDomain.TECHNICAL: _BULLISH_TECHNICAL, AgentDomain.MACRO: _BEARISH_MACRO},
        )
        technical_baseline = next(o for o in baseline_opinions if o.domain == AgentDomain.TECHNICAL)
        macro_baseline = next(o for o in baseline_opinions if o.domain == AgentDomain.MACRO)

        _, tilted_opinions = orchestrator.deliberate(
            {AgentDomain.TECHNICAL: _BULLISH_TECHNICAL, AgentDomain.MACRO: _BEARISH_MACRO},
            market_features=_REVERSING_LONG_FEATURES,  # -> LONG, reversing=True
        )
        technical_tilted = next(o for o in tilted_opinions if o.domain == AgentDomain.TECHNICAL)
        macro_tilted = next(o for o in tilted_opinions if o.domain == AgentDomain.MACRO)

        # TECHNICAL bullish -> LONG oyu -> Market State (LONG) ile AYNI yön -> yükseltilir.
        assert technical_tilted.performance_weight > technical_baseline.performance_weight
        # MACRO hawkish/tight -> SHORT oyu -> Market State'e TERS -> düşürülür.
        assert macro_tilted.performance_weight < macro_baseline.performance_weight
        assert any("Market State" in c for c in technical_tilted.caveats)
        assert any(adj["step"] == "market_state_tilt" for adj in technical_tilted.weight_adjustments)
    finally:
        _restore_tilt_enabled(original)


def test_enabled_but_not_reversing_is_a_noop(monkeypatch):
    original = _set_tilt_enabled("true")
    try:
        registry = AgentRegistry.create_default()
        orchestrator = CouncilOrchestrator(registry)
        monkeypatch.setattr(orchestrator.reliability_annotator, "annotate", _unbenched_annotate)

        _, opinions = orchestrator.deliberate(
            {AgentDomain.TECHNICAL: _BULLISH_TECHNICAL}, market_features=_NOT_REVERSING_FEATURES,
        )
        assert not any("Market State" in c for o in opinions for c in o.caveats)
    finally:
        _restore_tilt_enabled(original)


def test_enabled_but_no_market_features_is_a_noop_not_a_crash(monkeypatch):
    original = _set_tilt_enabled("true")
    try:
        registry = AgentRegistry.create_default()
        orchestrator = CouncilOrchestrator(registry)
        monkeypatch.setattr(orchestrator.reliability_annotator, "annotate", _unbenched_annotate)

        _, opinions = orchestrator.deliberate({AgentDomain.TECHNICAL: _BULLISH_TECHNICAL})
        assert not any("Market State" in c for o in opinions for c in o.caveats)
    finally:
        _restore_tilt_enabled(original)


def test_agent_weight_never_fully_silenced():
    """MAX_TILT=%30 -- moe_regime_router.py'nin AYNI garantisi, hiçbir
    ajan asla tamamen susturulmaz."""
    from analytics.market_state_tilt import compute_market_state_tilt

    result = compute_market_state_tilt({"direction": "LONG", "confidence": 1.0, "reversing": True})
    assert result["opposing_weight"] >= 0.7
