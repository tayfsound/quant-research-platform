"""Faz 244-246: PredictiveRiskStage — Monte Carlo/CPPI matematiği ayrı
test ediliyor (test_predictive_risk_monte_carlo.py); burada SADECE
stage'in final_size'ı gerçekten çarptığını ve fail-closed davrandığını
doğruluyoruz (test_meta_stage_kelly_sizing.py ile aynı desen)."""
from contracts.context import CognitiveCycleContext
from engines.cognitive_pipeline import PredictiveRiskStage


def _ctx_with_regime(final_size: float = 1.0) -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = final_size
    ctx.market.features = {"trend": "bullish", "volatility_regime": "normal"}
    return ctx


def test_does_nothing_when_final_size_is_zero(monkeypatch):
    import risk.predictive.monte_carlo as mc_module

    monkeypatch.setattr(
        mc_module, "load_regime_conditioned_pnl_pct", lambda regime: (_ for _ in ()).throw(
            AssertionError("final_size=0 iken hiç çağrılmamalı"),
        ),
    )
    ctx = _ctx_with_regime(final_size=0.0)
    result = PredictiveRiskStage().execute(ctx)
    assert result.decision.final_size == 0.0


def test_does_nothing_when_regime_is_unknown():
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = 1.0
    ctx.market.features = {}  # trend yok -> "unknown"
    result = PredictiveRiskStage().execute(ctx)
    assert result.decision.final_size == 1.0
    assert not any(
        item.get("type") == "predictive_risk" for item in result.cognition.relevant_knowledge
    )


def test_keeps_full_size_when_insufficient_regime_data(monkeypatch):
    import risk.predictive.monte_carlo as mc_module

    monkeypatch.setattr(mc_module, "load_regime_conditioned_pnl_pct", lambda regime: [])

    ctx = _ctx_with_regime(final_size=2.0)
    result = PredictiveRiskStage().execute(ctx)

    assert result.decision.final_size == 2.0
    entry = next(i for i in result.cognition.relevant_knowledge if i["type"] == "predictive_risk")
    assert entry["data"]["exposure_multiplier"] == 1.0
    assert entry["data"]["sample_count"] == 0


def test_shrinks_final_size_when_breach_probability_is_high(monkeypatch):
    import risk.predictive.monte_carlo as mc_module

    monkeypatch.setattr(mc_module, "load_regime_conditioned_pnl_pct", lambda regime: [-0.25] * 30)

    ctx = _ctx_with_regime(final_size=2.0)
    result = PredictiveRiskStage().execute(ctx)

    assert result.decision.final_size < 2.0
    entry = next(i for i in result.cognition.relevant_knowledge if i["type"] == "predictive_risk")
    assert entry["data"]["exposure_multiplier"] < 1.0
    assert entry["data"]["breach_probability"] == 1.0


def test_never_increases_final_size(monkeypatch):
    import risk.predictive.monte_carlo as mc_module

    monkeypatch.setattr(mc_module, "load_regime_conditioned_pnl_pct", lambda regime: [0.05] * 30)

    ctx = _ctx_with_regime(final_size=2.0)
    result = PredictiveRiskStage().execute(ctx)

    assert result.decision.final_size <= 2.0
