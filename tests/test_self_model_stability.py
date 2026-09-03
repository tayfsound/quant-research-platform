"""Faz 407 — services/self_model_gatherer.py::_attach_inputs_stability()
ECE/DSR'a geçmiş snapshot'lardan stabilite ekliyor. Bu, Ölçüm
Stabilitesi projesinin (Faz 407) kapsadığı 11 modülün SONUNCUSU —
kalan hepsi aynı mekanik desenle bağlandı."""
from services.self_model_gatherer import _attach_inputs_stability


def test_attaches_none_when_no_past_snapshots_exist():
    snapshot = {"inputs": {"ece": 0.2, "recent_dsr": 1.5}}
    _attach_inputs_stability(snapshot, past_snapshots=[])
    assert snapshot["inputs_stability"]["ece"] is None
    assert snapshot["inputs_stability"]["recent_dsr"] is None


def test_attaches_real_stability_from_past_snapshots():
    snapshot = {"inputs": {"ece": 0.25, "recent_dsr": 1.2}}
    past_snapshots = [
        {"result": {"inputs": {"ece": 0.20, "recent_dsr": 1.0}}},
        {"result": {"inputs": {"ece": 0.22, "recent_dsr": 1.1}}},
    ]
    _attach_inputs_stability(snapshot, past_snapshots)

    stability = snapshot["inputs_stability"]["ece"]
    assert stability["n"] == 3
    assert abs(stability["mean"] - 0.2233333333) < 1e-6


def test_ignores_past_snapshots_missing_the_field():
    """Eski snapshot'larda bu alan hiç None olmayabilir (henüz eklenmemiş
    olabilir) — sadece gerçek (None olmayan) değerler seriye girer."""
    snapshot = {"inputs": {"ece": 0.25, "recent_dsr": None}}
    past_snapshots = [{"result": {"inputs": {"ece": None, "recent_dsr": None}}}]
    _attach_inputs_stability(snapshot, past_snapshots)
    assert snapshot["inputs_stability"]["ece"] is None
    assert snapshot["inputs_stability"]["recent_dsr"] is None
