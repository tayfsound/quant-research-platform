"""Faz 407 — services/market_world_model_gatherer.py::_attach_paths_stability()
bootstrap simülasyonunun ana özet skalerlerine geçmiş snapshot'lardan
stabilite ekliyor."""
from services.market_world_model_gatherer import _attach_paths_stability


def test_none_paths_is_a_safe_no_op():
    """Fail-closed: paths None ise (yetersiz getiri) crash etmemeli."""
    _attach_paths_stability(None, past_snapshots=[{"result": {"paths": {"mean_cumulative_return": 0.1}}}])


def test_attaches_none_when_no_past_snapshots_exist():
    paths = {"mean_cumulative_return": 0.05, "p5_cumulative_return": -0.02, "worst_max_drawdown": -0.1}
    _attach_paths_stability(paths, past_snapshots=[])
    assert all(v is None for v in paths["stability"].values())


def test_attaches_real_stability_from_past_snapshots():
    paths = {"mean_cumulative_return": 0.06, "p5_cumulative_return": -0.02, "worst_max_drawdown": -0.1}
    past_snapshots = [
        {"result": {"paths": {"mean_cumulative_return": 0.04, "p5_cumulative_return": -0.03, "worst_max_drawdown": -0.12}}},
        {"result": {"paths": {"mean_cumulative_return": 0.05, "p5_cumulative_return": -0.025, "worst_max_drawdown": -0.11}}},
    ]
    _attach_paths_stability(paths, past_snapshots)

    stability = paths["stability"]["mean_cumulative_return"]
    assert stability["n"] == 3
    assert abs(stability["mean"] - 0.05) < 1e-9
