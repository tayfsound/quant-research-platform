"""Faz 471 — analytics/pattern_survival.py birim testleri."""
import math

from analytics.pattern_survival import compute_pattern_survival


def _rec(patterns, won, t, regime=None):
    return {"patterns": list(patterns), "won": won, "timestamp": t, "regime": regime}


def _chunk(index, pattern_wins, pattern_losses, other_wins, other_losses, regime=None):
    """Tek bir zaman penceresi: `p` örüntüsüne ait kayıtlar + popülasyonun
    geri kalanı. timestamp pencereler arası kronolojik sirayi korur."""
    out = []
    t0 = index * 1000
    for i in range(pattern_wins):
        out.append(_rec(["p"], True, t0 + i, regime))
    for i in range(pattern_losses):
        out.append(_rec(["p"], False, t0 + 100 + i, regime))
    for i in range(other_wins):
        out.append(_rec([], True, t0 + 200 + i, regime))
    for i in range(other_losses):
        out.append(_rec([], False, t0 + 300 + i, regime))
    return out


def test_surviving_pattern_keeps_its_excess():
    """Örüntü her pencerede tabanın ~20 puan üstünde kalıyor -> yaşıyor."""
    records = []
    for i in range(4):
        records += _chunk(i, pattern_wins=35, pattern_losses=15, other_wins=25, other_losses=25)

    r = compute_pattern_survival(records, chunk_size=100)
    p = r["patterns"]["p"]

    assert p["verdict"] == "surviving"
    assert math.isclose(p["discovery"]["excess"], 0.7 - 0.5, abs_tol=1e-6)
    assert p["consistent_chunks"] == p["total_subsequent_chunks"]
    assert r["surviving_patterns"] == ["p"]


def test_collapsed_pattern_is_detected():
    """Keşifte güçlü, sonrasında tabana (hatta altına) düşüyor -> çöktü.
    Dış raporun "89 -> 72 -> 59 -> 51" senaryosu."""
    records = _chunk(0, pattern_wins=45, pattern_losses=5, other_wins=25, other_losses=25)
    for i in (1, 2, 3):
        records += _chunk(i, pattern_wins=24, pattern_losses=26, other_wins=25, other_losses=25)

    r = compute_pattern_survival(records, chunk_size=100)
    p = r["patterns"]["p"]

    assert p["verdict"] == "collapsed"
    assert p["decay"] < 0
    assert r["collapsed_patterns"] == ["p"]


def test_raw_win_rate_drop_is_NOT_treated_as_decay_when_the_market_moved():
    """EN ÖNEMLİ TEST — dış raporun yöntemindeki kusurun düzeltmesi.

    Örüntünün ham WR'ı %90'dan %60'a düşüyor. Ham bakışla "eriyor"
    denirdi. Ama TABAN da %70'ten %40'a düşmüş — yani piyasa zorlaştı,
    örüntü fazlalığını (+20 puan) AYNEN korudu.

    Bugün bu tuzağa defalarca düştük (rsi_percentile ham −0,175 iken
    sembol-içi +0,000). Ham düşüşü çürüme sanmak, gerçek bir edge'i
    çöpe atmak olurdu."""
    records = _chunk(0, pattern_wins=45, pattern_losses=5, other_wins=35, other_losses=15)
    for i in (1, 2, 3):
        records += _chunk(i, pattern_wins=30, pattern_losses=20, other_wins=20, other_losses=30)

    r = compute_pattern_survival(records, chunk_size=100)
    p = r["patterns"]["p"]

    # Ham WR GERCEKTEN dustu...
    assert p["discovery"]["win_rate"] > p["subsequent"][0]["win_rate"]
    # ...ama taban da dustu, fazlalik korundu.
    assert p["verdict"] == "surviving"
    assert math.isclose(p["mean_subsequent_excess"], 0.20, abs_tol=0.02)


def test_regime_breakdown_reveals_what_the_pooled_number_hides():
    """KULLANICI İSTEĞİ (2026-09-09): "Ölçtüğümüz her şeyi rejime göre
    değerlendirmemiz lazım; hangi rejimde hangi verinin anlamlı olduğunu
    anlayamayız yoksa."

    Burada örüntü havuzlanmış olarak NÖTR görünüyor, ama aslında
    bullish_normal'da güçlü, bearish_low'da zararlı. Havuzlanmış tek bir
    sayı bu ikisini birbirine karıştırıp yok ediyor."""
    records = []
    for i in range(2):
        # bullish_normal: oruntu tabani 30 puan geciyor
        records += _chunk(i, 40, 10, 25, 25, regime="bullish_normal")
    for i in (2, 3):
        # bearish_low: oruntu tabanin 30 puan ALTINDA
        records += _chunk(i, 10, 40, 25, 25, regime="bearish_low")

    r = compute_pattern_survival(records, chunk_size=100)
    p = r["patterns"]["p"]

    assert p["by_regime"]["bullish_normal"]["excess"] > 0.2
    assert p["by_regime"]["bearish_low"]["excess"] < -0.2
    assert p["best_regime"] == "bullish_normal"
    assert p["worst_regime"] == "bearish_low"


def test_regime_baseline_is_the_regimes_own_rate():
    """Rejim fazlalığı, O REJİMİN kendi taban oranına göre. Aksi halde
    "bearish_low'da herkes kaybediyor" ile "bu örüntü bearish_low'da
    kaybediyor" birbirine karışırdı."""
    records = []
    for i in range(2):
        # bearish_low'da HERKES kotu (taban %20) ama oruntu tabanla AYNI
        records += _chunk(i, 10, 40, 10, 40, regime="bearish_low")
    for i in (2, 3):
        records += _chunk(i, 25, 25, 25, 25, regime="bullish_normal")

    r = compute_pattern_survival(records, chunk_size=100)
    p = r["patterns"]["p"]

    # Ham WR %20 -- kotu gorunuyor, AMA tabani gecmiyor da kalmiyor da.
    assert math.isclose(p["by_regime"]["bearish_low"]["win_rate"], 0.2, abs_tol=1e-6)
    assert math.isclose(p["by_regime"]["bearish_low"]["excess"], 0.0, abs_tol=1e-6)


def test_thin_regime_is_marked_unusable_not_dropped():
    records = []
    for i in range(3):
        records += _chunk(i, 30, 20, 25, 25, regime="bullish_normal")
    records += [_rec(["p"], True, 9999, "bearish_high")] * 5

    r = compute_pattern_survival(records, chunk_size=100)
    by_regime = r["patterns"]["p"]["by_regime"]

    assert by_regime["bearish_high"]["usable"] is False
    assert by_regime["bearish_high"]["excess"] is None


def test_pattern_seen_in_only_one_window_cannot_be_judged():
    """Tek pencerede görünen bir örüntü için "hayatta kaldı mı" sorusu
    tanımsız — fail-closed."""
    records = _chunk(0, 30, 20, 25, 25)
    for i in (1, 2):
        records += _chunk(i, 0, 0, 50, 50)

    r = compute_pattern_survival(records, chunk_size=100)
    assert r["patterns"]["p"]["verdict"] == "insufficient_history"
    assert r["patterns"]["p"]["usable"] is False


def test_fails_closed_without_two_full_chunks():
    records = _chunk(0, 30, 20, 25, 25)
    assert compute_pattern_survival(records, chunk_size=100) is None


def test_records_are_ordered_chronologically_not_by_input_order():
    """Hayatta kalma tanımı gereği zaman sıralıdır — girdinin sırası
    değişse bile sonuç AYNI olmalı."""
    records = []
    for i in range(3):
        records += _chunk(i, 35, 15, 25, 25)
    duz = compute_pattern_survival(list(records), chunk_size=100)
    karisik = compute_pattern_survival(list(reversed(records)), chunk_size=100)

    assert duz["patterns"]["p"]["discovery"] == karisik["patterns"]["p"]["discovery"]
    assert duz["patterns"]["p"]["verdict"] == karisik["patterns"]["p"]["verdict"]
