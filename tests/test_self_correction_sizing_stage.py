"""Faz 368: SelfCorrectionSizingStage — matematik ayrı test ediliyor
(test_self_correction_sizing_gate.py); burada SADECE stage'in final_size'ı
gerçekten çarptığını doğruluyoruz (test_drawdown_sizing_stage.py ile
AYNI desen)."""
from unittest.mock import patch

from contracts.context import CognitiveCycleContext
from engines.cognitive_pipeline import SelfCorrectionSizingStage


def _ctx(final_size: float, direction: str = "LONG") -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = final_size
    ctx.decision.proposed_direction = direction
    return ctx


def _stored(segments: dict | None):
    return patch(
        "analytics.self_correction_sizing_repository.SelfCorrectionSizingRepository.get_latest",
        return_value={"segments": segments} if segments is not None else None,
    )


def test_does_nothing_when_final_size_is_zero():
    with _stored({"direction=LONG": {"hypothesis_still_valid": False, "significant_change": True, "original_win_rate": 0.9, "recent_win_rate": 0.5}}):
        ctx = _ctx(final_size=0.0)
        result = SelfCorrectionSizingStage().execute(ctx)
    assert result.decision.final_size == 0.0


def test_does_nothing_when_no_snapshot_saved_yet():
    with _stored(None):
        ctx = _ctx(final_size=2.0)
        result = SelfCorrectionSizingStage().execute(ctx)
    assert result.decision.final_size == 2.0


def test_keeps_full_size_when_hypothesis_still_valid():
    with _stored({"direction=LONG": {"hypothesis_still_valid": True, "significant_change": True, "original_win_rate": 0.9, "recent_win_rate": 0.5}}):
        ctx = _ctx(final_size=2.0)
        result = SelfCorrectionSizingStage().execute(ctx)
    assert result.decision.final_size == 2.0


def test_shrinks_size_on_a_real_collapsed_hypothesis():
    """Gerçek LONG olayı: 96.4% -> 71.5%."""
    with _stored({"direction=LONG": {"hypothesis_still_valid": False, "significant_change": True, "original_win_rate": 0.9642, "recent_win_rate": 0.7148}}):
        ctx = _ctx(final_size=2.0)
        result = SelfCorrectionSizingStage().execute(ctx)
    assert result.decision.final_size < 2.0
    entry = next(i for i in result.cognition.relevant_knowledge if i["type"] == "self_correction_sizing")
    assert entry["data"]["direction"] == "LONG"
    assert entry["data"]["exposure_multiplier"] < 1.0


def test_only_affects_the_matching_direction():
    """LONG çökmüş, ama bu karar SHORT — etkilenmemeli."""
    with _stored({"direction=LONG": {"hypothesis_still_valid": False, "significant_change": True, "original_win_rate": 0.9642, "recent_win_rate": 0.7148}}):
        ctx = _ctx(final_size=2.0, direction="SHORT")
        result = SelfCorrectionSizingStage().execute(ctx)
    assert result.decision.final_size == 2.0


def test_never_increases_final_size():
    with _stored({"direction=LONG": {"hypothesis_still_valid": False, "significant_change": True, "original_win_rate": 0.5, "recent_win_rate": 0.99}}):
        ctx = _ctx(final_size=2.0)
        result = SelfCorrectionSizingStage().execute(ctx)
    assert result.decision.final_size <= 2.0
