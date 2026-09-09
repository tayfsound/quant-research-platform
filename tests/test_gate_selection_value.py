"""Faz 467 — analytics/gate_selection_value.py birim testleri."""
import math

from analytics.gate_selection_value import compute_gate_selection_effect


def _rec(gates, direction, label, day="2026-09-01", n=1):
    return [{
        "blocking_gates": list(gates), "direction": direction,
        "forward_label": label, "day": day,
    }] * n


def _grup(gates, day, isabet_n, isabet_disi_n):
    """LONG kararlar: UP = isabet, DOWN = isabetsiz."""
    return (_rec(gates, "LONG", "UP", day, isabet_n)
            + _rec(gates, "LONG", "DOWN", day, isabet_disi_n))


def test_detects_a_healthy_selective_gate():
    """Kapı işini yapıyorsa: geçirdikleri, engellediklerinden DAHA
    isabetli."""
    records = []
    for gun in ("2026-09-01", "2026-09-02", "2026-09-03"):
        records += _grup([], gun, 140, 60)            # gecenler: %70
        records += _grup(["risk_gate"], gun, 80, 120)  # engellenenler: %40

    r = compute_gate_selection_effect(records)
    g = r["gates"]["risk_gate"]

    assert g["verdict"] == "selective"
    assert math.isclose(g["selection_value"], 0.70 - 0.40, abs_tol=1e-6)
    assert r["anti_selective_gates"] == []


def test_detects_an_anti_selective_gate():
    """ASIL ARADIĞIMIZ DURUM: kapı, engellediği kararlar geçirdiklerinden
    DAHA İYİ olacak şekilde ters seçim yapıyor. 2026-09-09'da
    min_confidence_gate'te tam bu desen ölçüldü (geçen %45,6 vs
    engellenen %47,7)."""
    records = []
    for gun in ("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"):
        records += _grup([], gun, 90, 110)                        # gecenler %45
        records += _grup(["min_confidence_gate"], gun, 120, 80)   # engellenenler %60

    r = compute_gate_selection_effect(records)
    g = r["gates"]["min_confidence_gate"]

    assert g["verdict"] == "anti_selective"
    assert g["selection_value"] < -NEUTRAL()
    assert r["anti_selective_gates"] == ["min_confidence_gate"]
    assert r["proven_anti_selective_gates"] == ["min_confidence_gate"]


def NEUTRAL():
    from analytics.gate_selection_value import NEUTRAL_BAND
    return NEUTRAL_BAND


def test_inconsistent_gate_is_flagged_but_not_proven():
    """EN KRİTİK TEST — 2026-09-09'un dersi. min_confidence_gate
    havuzlanmış veride güçlü bir ters seçim gösterdi AMA günlük kırılımda
    5/8 (%62,5) çıktı, çıtamız %80. Bu yüzden kapıya DOKUNULMADI.

    Havuzda anti_selective görünen ama günlük tutarsız bir kapı
    `verdict`'te işaretlenmeli, `proven`'da ASLA True olmamalı."""
    records = []
    # 3 gun ters secim, 2 gun TERSI -> tutarlilik 3/5 = %60 < %80
    for gun in ("2026-09-01", "2026-09-02", "2026-09-03"):
        records += _grup([], gun, 80, 120)
        records += _grup(["kararsiz_kapi"], gun, 130, 70)
    for gun in ("2026-09-04", "2026-09-05"):
        records += _grup([], gun, 130, 70)
        records += _grup(["kararsiz_kapi"], gun, 80, 120)

    r = compute_gate_selection_effect(records)
    g = r["gates"]["kararsiz_kapi"]

    assert g["daily"]["consistency_ratio"] < 0.8
    assert g["daily"]["consistent"] is False
    assert g["proven"] is False
    assert r["proven_anti_selective_gates"] == []


def test_gate_with_too_few_blocks_is_unusable_not_dropped():
    """Az örnekli bir kapı sessizce kaybolmamalı; raporda `usable: false`
    ile görünmeli (gerçek veride pivot_distance_gate 3 kez tetiklendi)."""
    records = _grup([], "2026-09-01", 150, 150) + _grup([], "2026-09-02", 150, 150)
    records += _grup(["pivot_distance_gate"], "2026-09-01", 2, 1)

    r = compute_gate_selection_effect(records)
    g = r["gates"]["pivot_distance_gate"]

    assert g["usable"] is False
    assert g["selection_value"] is None
    assert g["proven"] is False


def test_a_decision_blocked_by_several_gates_counts_for_each():
    """Bir karar birden fazla kapıya takılabilir; her kapının kendi
    karşılaştırması bağımsız yapılmalı."""
    records = []
    for gun in ("2026-09-01", "2026-09-02", "2026-09-03"):
        records += _grup([], gun, 100, 100)
        records += _grup(["a_kapisi", "b_kapisi"], gun, 140, 60)

    r = compute_gate_selection_effect(records)

    assert r["gates"]["a_kapisi"]["blocked_n"] == 600
    assert r["gates"]["b_kapisi"]["blocked_n"] == 600
    assert (r["gates"]["a_kapisi"]["selection_value"]
            == r["gates"]["b_kapisi"]["selection_value"])


def test_short_direction_hit_is_inverted_correctly():
    """SHORT kararda isabet, fiyatın DÜŞMESİ demek — LONG'un aynadaki
    hâli. Yanlış kodlanırsa tüm kapı ölçümü ters çıkar."""
    records = _rec([], "SHORT", "DOWN", "2026-09-01", 300)
    records += _rec(["k"], "SHORT", "UP", "2026-09-01", 300)
    records += _rec([], "SHORT", "DOWN", "2026-09-02", 300)
    records += _rec(["k"], "SHORT", "UP", "2026-09-02", 300)
    records += _rec([], "SHORT", "DOWN", "2026-09-03", 300)
    records += _rec(["k"], "SHORT", "UP", "2026-09-03", 300)

    r = compute_gate_selection_effect(records)

    assert math.isclose(r["passed_hit_rate"], 1.0, abs_tol=1e-9)
    assert math.isclose(r["gates"]["k"]["blocked_hit_rate"], 0.0, abs_tol=1e-9)
    assert r["gates"]["k"]["verdict"] == "selective"


def test_fails_closed_without_enough_data():
    assert compute_gate_selection_effect(_grup([], "2026-09-01", 50, 50)) is None


def test_fails_closed_when_nothing_passes_all_gates():
    """Karşılaştırma grubu yoksa hiçbir kapı değerlendirilemez."""
    records = _grup(["k"], "2026-09-01", 200, 200)
    assert compute_gate_selection_effect(records) is None
