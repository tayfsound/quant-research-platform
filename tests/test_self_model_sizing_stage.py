"""Faz 368: SelfModelSizingStage — matematik ayrı test ediliyor
(test_self_model_sizing_gate.py); burada SADECE stage'in final_size'ı
gerçekten çarptığını doğruluyoruz (test_drawdown_sizing_stage.py /
test_self_correction_sizing_stage.py ile AYNI desen)."""
from unittest.mock import patch

from contracts.context import CognitiveCycleContext
from engines.cognitive_pipeline import SelfModelSizingStage


def _ctx(final_size: float) -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = final_size
    return ctx


def _stored(overall_reliability: str | None):
    value = {"result": {"overall_reliability": overall_reliability}} if overall_reliability is not None else None
    return patch(
        "database.repositories.self_model_report_repository.SelfModelReportRepository.get_latest",
        return_value=value,
    )


def test_does_nothing_when_final_size_is_zero():
    with _stored("untrustworthy"):
        ctx = _ctx(final_size=0.0)
        result = SelfModelSizingStage().execute(ctx)
    assert result.decision.final_size == 0.0


def test_does_nothing_when_no_snapshot_saved_yet():
    with _stored(None):
        ctx = _ctx(final_size=2.0)
        result = SelfModelSizingStage().execute(ctx)
    assert result.decision.final_size == 2.0


def test_keeps_full_size_when_high():
    with _stored("high"):
        ctx = _ctx(final_size=2.0)
        result = SelfModelSizingStage().execute(ctx)
    assert result.decision.final_size == 2.0


def test_shrinks_size_when_degraded():
    with _stored("degraded"):
        ctx = _ctx(final_size=2.0)
        result = SelfModelSizingStage().execute(ctx)
    assert result.decision.final_size < 2.0
    entry = next(i for i in result.cognition.relevant_knowledge if i["type"] == "self_model_sizing")
    assert entry["data"]["overall_reliability"] == "degraded"


def test_shrinks_size_more_when_untrustworthy():
    with _stored("degraded"):
        degraded_size = SelfModelSizingStage().execute(_ctx(final_size=2.0)).decision.final_size
    with _stored("untrustworthy"):
        untrustworthy_size = SelfModelSizingStage().execute(_ctx(final_size=2.0)).decision.final_size
    assert untrustworthy_size < degraded_size


def test_never_increases_final_size():
    with _stored("untrustworthy"):
        ctx = _ctx(final_size=2.0)
        result = SelfModelSizingStage().execute(ctx)
    assert result.decision.final_size <= 2.0
