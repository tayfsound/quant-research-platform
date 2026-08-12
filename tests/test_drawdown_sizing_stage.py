"""Faz 268-sonrası: DrawdownSizingStage — matematik ayrı test ediliyor
(test_drawdown_sizing.py); burada SADECE stage'in final_size'ı gerçekten
çarptığını doğruluyoruz (test_predictive_risk_stage.py ile aynı desen)."""
from unittest.mock import patch

from contracts.context import CognitiveCycleContext
from engines.cognitive_pipeline import DrawdownSizingStage


def _ctx(final_size: float, consecutive_losses: int) -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = final_size
    ctx.risk.consecutive_losses = consecutive_losses
    return ctx


def _settings(start_after: str = "3", full_reduction_at: str = "10"):
    return patch(
        "database.repositories.app_settings_repository.AppSettingsRepository.get",
        side_effect=lambda key: {
            "drawdown_sizing_start_after_losses": start_after,
            "drawdown_sizing_full_reduction_at_losses": full_reduction_at,
        }[key],
    )


def test_does_nothing_when_final_size_is_zero():
    ctx = _ctx(final_size=0.0, consecutive_losses=50)
    result = DrawdownSizingStage().execute(ctx)
    assert result.decision.final_size == 0.0


def test_keeps_full_size_below_start_threshold():
    with _settings():
        ctx = _ctx(final_size=2.0, consecutive_losses=1)
        result = DrawdownSizingStage().execute(ctx)
    assert result.decision.final_size == 2.0
    entry = next(i for i in result.cognition.relevant_knowledge if i["type"] == "drawdown_sizing")
    assert entry["data"]["exposure_multiplier"] == 1.0


def test_shrinks_size_after_a_real_losing_streak():
    with _settings():
        ctx = _ctx(final_size=2.0, consecutive_losses=8)
        result = DrawdownSizingStage().execute(ctx)
    assert result.decision.final_size < 2.0
    entry = next(i for i in result.cognition.relevant_knowledge if i["type"] == "drawdown_sizing")
    assert entry["data"]["exposure_multiplier"] < 1.0
    assert entry["data"]["consecutive_losses"] == 8


def test_never_increases_final_size():
    with _settings():
        ctx = _ctx(final_size=2.0, consecutive_losses=100)
        result = DrawdownSizingStage().execute(ctx)
    assert result.decision.final_size <= 2.0
