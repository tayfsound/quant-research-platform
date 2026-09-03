"""Faz 407 — services/tp_sl_confluence_gatherer.py::_attach_pct_stability()
her yüzde alanına geçmiş snapshot'lardan stabilite ekliyor. Bu modülün
kendi docstring'i (Faz 343) bu yüzdelerin piyasa rejimiyle doğal olarak
değiştiğini zaten belgeliyor — stabilite bunu SADECE gözlemlenebilir
kılıyor."""
from services.tp_sl_confluence_gatherer import _attach_pct_stability


def test_attaches_none_when_no_past_snapshots_exist():
    result = {"pct_long_stop_near_confluence": 0.3, "pct_long_target_near_confluence": 0.1,
              "pct_short_stop_near_confluence": 0.2, "pct_short_target_near_confluence": 0.0}
    _attach_pct_stability(result, past_snapshots=[])
    assert all(v is None for v in result["stability"].values())


def test_attaches_real_stability_from_past_snapshots():
    result = {"pct_long_stop_near_confluence": 0.4, "pct_long_target_near_confluence": 0.1,
              "pct_short_stop_near_confluence": 0.2, "pct_short_target_near_confluence": 0.0}
    past_snapshots = [
        {"result": {"pct_long_stop_near_confluence": 0.2, "pct_long_target_near_confluence": 0.05,
                     "pct_short_stop_near_confluence": 0.1, "pct_short_target_near_confluence": 0.0}},
        {"result": {"pct_long_stop_near_confluence": 0.3, "pct_long_target_near_confluence": 0.08,
                     "pct_short_stop_near_confluence": 0.15, "pct_short_target_near_confluence": 0.0}},
    ]
    _attach_pct_stability(result, past_snapshots)

    stability = result["stability"]["pct_long_stop_near_confluence"]
    assert stability["n"] == 3
    assert abs(stability["mean"] - 0.3) < 1e-9
