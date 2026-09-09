"""Faz 472 — analytics/direction_meta_label.py birim testleri."""
import math

from analytics.direction_meta_label import compute_direction_meta_label


def _rec(direction, label, regime, t):
    return {
        "council_direction": direction, "forward_label": label,
        "regime": regime, "timestamp": t,
    }


def _cell(direction, regime, correct_n, wrong_n, t0):
    """Bir hücrede `correct_n` doğru + `wrong_n` yanlış Council çağrısı."""
    dogru = "UP" if direction == "LONG" else "DOWN"
    yanlis = "DOWN" if direction == "LONG" else "UP"
    out = [_rec(direction, dogru, regime, t0 + i) for i in range(correct_n)]
    out += [_rec(direction, yanlis, regime, t0 + 500 + i) for i in range(wrong_n)]
    return out


def test_trustworthy_cell_survives_out_of_sample():
    """Council LONG/bullish_normal'da hem train hem holdout'ta tabanı
    geçiyor -> güvenilir kanıt."""
    records = []
    # train donemi (t 0..)
    records += _cell("LONG", "bullish_normal", 80, 20, 0)
    records += _cell("SHORT", "bearish_low", 50, 50, 1000)
    # holdout donemi (t 10000..) -- ayni desen surüyor
    records += _cell("LONG", "bullish_normal", 45, 15, 10000)
    records += _cell("SHORT", "bearish_low", 30, 30, 11000)

    r = compute_direction_meta_label(records, holdout_fraction=0.35)
    hucre = r["cells"]["LONG|bullish_normal"]

    assert hucre["usable"] is True
    assert hucre["survives_oos"] is True
    assert hucre["holdout_edge"] > 0
    assert "LONG|bullish_normal" in r["trustworthy_cells"]


def test_cell_that_flips_sign_out_of_sample_is_rejected():
    """EN KRİTİK TEST. Train'de güçlü, holdout'ta TERS bir hücre kanıt
    değil GÜRÜLTÜDÜR. Bugün defalarca gördük: rsi_percentile ham −0,175
    iken sembol-içi +0,000; dış raporun üç yıldız adayı düzeltilmiş
    hedefle çöktü."""
    records = []
    records += _cell("LONG", "bullish_low", 90, 10, 0)      # train: cok iyi
    records += _cell("SHORT", "bearish_normal", 50, 50, 1000)
    records += _cell("LONG", "bullish_low", 15, 45, 10000)  # holdout: TERS
    records += _cell("SHORT", "bearish_normal", 30, 30, 11000)

    r = compute_direction_meta_label(records, holdout_fraction=0.35)
    hucre = r["cells"]["LONG|bullish_low"]

    assert hucre["train_edge"] > 0
    assert hucre["holdout_edge"] < 0
    assert hucre["survives_oos"] is False
    assert "LONG|bullish_low" not in r["trustworthy_cells"]


def test_systematically_inverted_cell_is_reported_separately():
    """Council'in TUTARLI olarak ters olduğu hücre de BİLGİDİR — ama
    `trustworthy_cells`'e değil `inverted_cells`'e gider. İkisini
    karıştırmak, ters bir sinyali kanıt sanmak olurdu."""
    records = []
    records += _cell("SHORT", "bearish_low", 20, 80, 0)
    records += _cell("LONG", "bullish_normal", 50, 50, 1000)
    records += _cell("SHORT", "bearish_low", 12, 48, 10000)
    records += _cell("LONG", "bullish_normal", 30, 30, 11000)

    r = compute_direction_meta_label(records, holdout_fraction=0.35)
    hucre = r["cells"]["SHORT|bearish_low"]

    assert hucre["survives_oos"] is True
    assert hucre["holdout_edge"] < 0
    assert "SHORT|bearish_low" in r["inverted_cells"]
    assert "SHORT|bearish_low" not in r["trustworthy_cells"]


def test_baseline_comes_from_the_holdout_period_itself():
    """Faz 471'in dersi: piyasa zorlaştıysa hücrenin ham isabeti düşer
    ama fazlalığı korunabilir. Taban SABİT olsaydı, gerçek bir hücreyi
    yanlışlıkla "çöktü" diye eleyebilirdik.

    Burada holdout'ta HERKES kötüleşiyor (taban %70 -> %40) ama hücre
    tabanın 20 puan üstünde kalmaya devam ediyor."""
    records = []
    records += _cell("LONG", "bullish_normal", 90, 10, 0)     # %90
    records += _cell("SHORT", "bearish_low", 50, 50, 1000)    # %50 -> taban ~%70
    records += _cell("LONG", "bullish_normal", 36, 24, 10000)  # %60
    records += _cell("SHORT", "bearish_low", 12, 48, 11000)    # %20 -> taban ~%40

    r = compute_direction_meta_label(records, holdout_fraction=0.35)
    hucre = r["cells"]["LONG|bullish_normal"]

    # Ham isabet GERCEKTEN dustu...
    assert hucre["holdout_accuracy"] < hucre["train_accuracy"]
    # ...ama taban da dustugu icin fazlalik korundu.
    assert hucre["holdout_edge"] > 0.15
    assert hucre["survives_oos"] is True


def test_thin_cells_are_marked_unusable_not_dropped():
    records = []
    records += _cell("LONG", "bullish_normal", 80, 20, 0)
    records += _cell("SHORT", "bearish_high", 5, 5, 900)
    records += _cell("LONG", "bullish_normal", 45, 15, 10000)
    records += _cell("SHORT", "bearish_high", 3, 2, 10900)

    r = compute_direction_meta_label(records, holdout_fraction=0.35)

    assert r["cells"]["SHORT|bearish_high"]["usable"] is False
    assert r["cells"]["SHORT|bearish_high"]["survives_oos"] is False


def test_split_is_chronological_not_random():
    """Zaman tabanlı bölme ZORUNLU — rastgele bölme "keşiften sonra ne
    oldu" sorusunu cevaplayamaz. Girdi sırası karışsa bile sonuç AYNI
    olmalı."""
    records = []
    records += _cell("LONG", "bullish_normal", 80, 20, 0)
    records += _cell("SHORT", "bearish_low", 50, 50, 1000)
    records += _cell("LONG", "bullish_normal", 45, 15, 10000)
    records += _cell("SHORT", "bearish_low", 30, 30, 11000)

    duz = compute_direction_meta_label(list(records), holdout_fraction=0.35)
    karisik = compute_direction_meta_label(list(reversed(records)), holdout_fraction=0.35)

    assert math.isclose(duz["holdout_baseline"], karisik["holdout_baseline"], abs_tol=1e-9)
    assert (duz["cells"]["LONG|bullish_normal"]["holdout_edge"]
            == karisik["cells"]["LONG|bullish_normal"]["holdout_edge"])


def test_fails_closed_on_tiny_sample():
    assert compute_direction_meta_label(_cell("LONG", "bullish_normal", 10, 10, 0)) is None
