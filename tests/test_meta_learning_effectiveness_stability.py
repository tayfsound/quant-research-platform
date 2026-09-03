"""Faz 407 — services/meta_learning_effectiveness_gatherer.py::_attach_
trend_stability(). Bu, Ölçüm Stabilitesi projesinin kapsadığı 17
modülün SONUNCUSU — tamamı aynı mekanik desenle bağlandı."""
from services.meta_learning_effectiveness_gatherer import _attach_trend_stability


def test_none_trend_is_a_safe_no_op():
    """Fail-closed: <MIN_ROUNDS turla trend None döner, crash etmemeli."""
    _attach_trend_stability(None, past_snapshots=[{"result": {"trend": {"spearman_correlation": 0.5}}}])


def test_attaches_none_when_no_past_snapshots_exist():
    trend = {"spearman_correlation": 0.6, "avg_sharpe_improvement": 0.1, "trend": "improving"}
    _attach_trend_stability(trend, past_snapshots=[])
    assert trend["stability"]["spearman_correlation"] is None
    assert trend["stability"]["avg_sharpe_improvement"] is None


def test_attaches_real_stability_from_past_snapshots():
    trend = {"spearman_correlation": 0.55, "avg_sharpe_improvement": 0.12, "trend": "improving"}
    past_snapshots = [
        {"result": {"trend": {"spearman_correlation": 0.40, "avg_sharpe_improvement": 0.08}}},
        {"result": {"trend": {"spearman_correlation": 0.50, "avg_sharpe_improvement": 0.10}}},
    ]
    _attach_trend_stability(trend, past_snapshots)

    stability = trend["stability"]["spearman_correlation"]
    assert stability["n"] == 3
    assert abs(stability["mean"] - 0.4833333333) < 1e-6
