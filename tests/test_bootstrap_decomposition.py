"""Faz 478 — risk simülatörünün yön/rejim decomposition'ı.

Kullanıcı fikri (2026-09-09): "Şu an aggregate sonuç '1999 işlemin
tamamında ne oluyor?' diyor. Senin asıl problemin ise 'hangi koşullarda
işlem motoru bozuluyor?'"
"""
from analytics.market_world_model import compute_bootstrap_decomposition


def _recs(n, ret, direction="LONG", regime=None, volatility=None):
    return [
        {"ret": ret, "direction": direction, "regime": regime, "volatility": volatility}
        for _ in range(n)
    ]


def test_decomposition_exposes_a_losing_direction_that_the_aggregate_hides():
    """ASIL AMAÇ. Havuzlanmış sonuç ~0 görünürken LONG kârlı, SHORT
    zararlı olabiliyor — kullanıcının verdiği örneğin ta kendisi."""
    records = _recs(120, +0.004, "LONG") + _recs(120, -0.004, "SHORT")

    r = compute_bootstrap_decomposition(records, block_size=5, path_length=20)

    assert r["slices"]["overall"]["usable"] is True
    assert r["slices"]["LONG"]["mean_cumulative_return"] > 0
    assert r["slices"]["SHORT"]["mean_cumulative_return"] < 0
    # Havuzlanmis sonuc ikisinin ORTASINDA -- tek basina yaniltici.
    assert (r["slices"]["SHORT"]["mean_cumulative_return"]
            < r["slices"]["overall"]["mean_cumulative_return"]
            < r["slices"]["LONG"]["mean_cumulative_return"])
    assert r["worst_slice"] == "SHORT"
    assert r["best_slice"] == "LONG"


def test_regime_slices_are_simulated_independently():
    """Faz 471'in dersi: her dilim KENDİ getirileriyle simüle edilmeli.
    Havuzlanmış sonuçtan pay biçmek, rejimler arası zorluk farkını
    sonuca sızdırırdı."""
    records = _recs(100, +0.005, "LONG", regime="bullish_normal")
    records += _recs(100, -0.006, "LONG", regime="bearish_low")

    r = compute_bootstrap_decomposition(records, block_size=5, path_length=20)

    assert r["slices"]["bullish_normal"]["mean_cumulative_return"] > 0
    assert r["slices"]["bearish_low"]["mean_cumulative_return"] < 0
    assert r["worst_slice"] == "bearish_low"


def test_volatility_slices_are_prefixed_to_avoid_name_collisions():
    """`low`/`normal`/`high` rejim adlarıyla çakışabilir; volatilite
    dilimleri `vol_` önekiyle ayrılıyor."""
    records = _recs(80, +0.003, "LONG", volatility="low")
    records += _recs(80, -0.003, "LONG", volatility="high")

    r = compute_bootstrap_decomposition(records, block_size=5, path_length=20)

    assert "vol_low" in r["slices"]
    assert "vol_high" in r["slices"]
    assert r["slices"]["vol_low"]["mean_cumulative_return"] > 0


def test_thin_slice_is_marked_unusable_not_silently_dropped():
    """"Ölçemedik" ile "etkisi yok" karıştırılmamalı."""
    records = _recs(150, +0.004, "LONG") + _recs(5, -0.02, "SHORT")

    r = compute_bootstrap_decomposition(records, block_size=5, path_length=20)

    assert r["slices"]["SHORT"]["usable"] is False
    assert r["slices"]["SHORT"]["n"] == 5
    assert r["slices"]["SHORT"]["paths"] is None
    # Kullanilamaz dilim en-kotu secimine KATILMAMALI.
    assert r["worst_slice"] != "SHORT"


def test_fails_closed_on_tiny_input():
    assert compute_bootstrap_decomposition(_recs(10, 0.001), block_size=5, path_length=20) is None


def test_non_numeric_returns_are_excluded():
    records = [{"ret": None, "direction": "LONG"} for _ in range(200)]
    assert compute_bootstrap_decomposition(records, block_size=5, path_length=20) is None


def test_slices_carry_tail_risk_not_just_the_mean():
    """Kullanıcının MAE/MFE incelemesindeki uyarı burada da geçerli:
    tek bir nokta tahmini yetmez, kuyruk da görünmeli."""
    records = _recs(200, -0.003, "SHORT")
    r = compute_bootstrap_decomposition(records, block_size=5, path_length=20)
    dilim = r["slices"]["SHORT"]

    for alan in ("p5_cumulative_return", "p95_cumulative_return",
                 "cvar_5_cumulative_return", "mean_max_drawdown"):
        assert dilim[alan] is not None
