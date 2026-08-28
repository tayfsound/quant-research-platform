"""Faz 368: SymbolPerformanceSizingStage — matematik ayrı test ediliyor
(test_symbol_performance_sizing_gate.py); burada stage'in final_size'ı
gerçekten çarptığını doğruluyoruz (test_self_correction_sizing_stage.py
ile AYNI desen)."""
from unittest.mock import patch

from contracts.context import CognitiveCycleContext
from engines.cognitive_pipeline import SymbolPerformanceSizingStage


def _ctx(final_size: float, symbol: str = "ATOMUSDT", direction: str = "LONG") -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = final_size
    ctx.decision.proposed_direction = direction
    ctx.market.symbol = symbol
    return ctx


def _mocks(by_symbol_direction: dict | None, baseline: str = "0.74"):
    stored = {"by_symbol_direction": by_symbol_direction} if by_symbol_direction is not None else None
    repo_patch = patch(
        "analytics.symbol_performance_sizing_repository.SymbolPerformanceSizingRepository.get_latest",
        return_value=stored,
    )
    settings_patch = patch(
        "database.repositories.app_settings_repository.AppSettingsRepository.get",
        return_value=baseline,
    )
    return repo_patch, settings_patch


def test_does_nothing_when_final_size_is_zero():
    repo_p, settings_p = _mocks({"ATOMUSDT_LONG": {"win_rate": 0.3171, "sample_size": 41}})
    with repo_p, settings_p:
        ctx = _ctx(final_size=0.0)
        result = SymbolPerformanceSizingStage().execute(ctx)
    assert result.decision.final_size == 0.0


def test_does_nothing_when_no_snapshot_saved_yet():
    repo_p, settings_p = _mocks(None)
    with repo_p, settings_p:
        ctx = _ctx(final_size=2.0)
        result = SymbolPerformanceSizingStage().execute(ctx)
    assert result.decision.final_size == 2.0


def test_shrinks_on_a_real_toxic_symbol_direction():
    """Gerçek olay: ATOMUSDT_LONG n=41, win_rate=%31.7."""
    repo_p, settings_p = _mocks({"ATOMUSDT_LONG": {"win_rate": 0.3171, "sample_size": 41}})
    with repo_p, settings_p:
        ctx = _ctx(final_size=2.0)
        result = SymbolPerformanceSizingStage().execute(ctx)
    assert result.decision.final_size < 2.0
    entry = next(i for i in result.cognition.relevant_knowledge if i["type"] == "symbol_performance_sizing")
    assert entry["data"]["symbol_direction"] == "ATOMUSDT_LONG"


def test_only_affects_the_matching_symbol_direction():
    """ATOMUSDT_LONG kötü ama bu karar ATOMUSDT_SHORT — etkilenmemeli."""
    repo_p, settings_p = _mocks({"ATOMUSDT_LONG": {"win_rate": 0.3171, "sample_size": 41}})
    with repo_p, settings_p:
        ctx = _ctx(final_size=2.0, direction="SHORT")
        result = SymbolPerformanceSizingStage().execute(ctx)
    assert result.decision.final_size == 2.0


def test_keeps_full_size_for_a_healthy_symbol():
    repo_p, settings_p = _mocks({"ATOMUSDT_LONG": {"win_rate": 0.9, "sample_size": 41}})
    with repo_p, settings_p:
        ctx = _ctx(final_size=2.0)
        result = SymbolPerformanceSizingStage().execute(ctx)
    assert result.decision.final_size == 2.0


def test_never_increases_final_size():
    repo_p, settings_p = _mocks({"ATOMUSDT_LONG": {"win_rate": 0.01, "sample_size": 41}})
    with repo_p, settings_p:
        ctx = _ctx(final_size=2.0)
        result = SymbolPerformanceSizingStage().execute(ctx)
    assert result.decision.final_size <= 2.0
