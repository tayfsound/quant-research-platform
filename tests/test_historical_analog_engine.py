"""FIL Faz D — analytics/historical_analog_engine.py. Aynı kalıp tests/
test_agent_combination_reliability.py'yi izliyor (üçüncü eksen olarak
market_regime eklendiği için)."""
from datetime import UTC, datetime, timedelta

from analytics.historical_analog_engine import (
    DIRECTION_LABELS,
    apply_confidence_shrinkage,
    compute_direction_analogs,
    compute_historical_analogs,
    compute_recency_decay,
)


def _record(domains, regime, direction, win, closed_at=None, reversing=False):
    return {
        "agreeing_domains": frozenset(domains),
        "market_regime": regime,
        "direction": direction,
        "win": win,
        "closed_at": closed_at,
        "reversing": reversing,
    }


def _direction_record(domains, regime, direction, forward_label, closed_at=None, reversing=False):
    return {
        "agreeing_domains": frozenset(domains),
        "market_regime": regime,
        "direction": direction,
        "forward_label": forward_label,
        "closed_at": closed_at,
        "reversing": reversing,
    }


def test_gate_eligible_requires_minimum_distinct_days():
    """Faz 422 (2026-09-06) — GPT'nin dış incelemesi + kullanıcı onayı:
    gate_eligible olan analogların TAMAMI distinct_days=2 çıkıyordu
    (ör. gerçek canlı veri: order_flow+technical/bullish_normal/LONG,
    win_rate=0,94, eff_n=27, sadece 2 farklı gün) —
    agent_combination_reliability_gate.py'nin ZATEN kullandığı
    min_distinct_days=5 eşiği burada yoktu. FDR+OOS+effective_sample_size
    hepsi geçse bile, sadece 2 (ya da her hâlükârda <5) farklı güne
    dayanan GÜÇLÜ görünen bir örüntü artık gate_eligible=False olmalı."""
    from datetime import UTC, datetime, timedelta

    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    # hours=i -> 40 kayit sadece ~1.67 gune yayiliyor (distinct_days<5).
    strong = [
        _record({"technical", "macro"}, "bullish_low", "LONG", i % 10 != 0, base_time + timedelta(hours=i))
        for i in range(40)
    ]
    baseline = [
        _record({"quant"}, "bullish_low", "LONG", i < 10, base_time + timedelta(hours=i))
        for i in range(40)
    ]
    result = compute_historical_analogs(strong + baseline, combination_sizes=(2,), min_group_size=20)
    analog = next(a for a in result["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog["fdr_significant"] is True
    assert analog["oos_survival"] is True
    assert analog["effective_sample_size"] >= 20
    assert analog["distinct_days"] < 5
    assert analog["gate_eligible"] is False


def test_empty_input_is_fail_closed():
    result = compute_historical_analogs([])
    assert result == {"analogs": [], "baseline_win_rate": None, "baseline_sample_size": 0}


def test_excludes_records_missing_market_regime_or_direction():
    records = [
        {"agreeing_domains": frozenset({"technical", "macro"}), "market_regime": None,
         "direction": "LONG", "win": True, "closed_at": None},
        {"agreeing_domains": frozenset({"technical", "macro"}), "market_regime": "bullish_low",
         "direction": None, "win": True, "closed_at": None},
    ]
    result = compute_historical_analogs(records)
    assert result == {"analogs": [], "baseline_win_rate": None, "baseline_sample_size": 0}


def test_excludes_groups_below_min_group_size():
    records = (
        [_record({"technical", "macro"}, "bullish_low", "LONG", True) for _ in range(5)]
        + [_record({"quant"}, "bullish_low", "LONG", False) for _ in range(50)]
    )
    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    keys = {(tuple(a["domains"]), a["market_regime"], a["direction"]) for a in result["analogs"]}
    assert (("macro", "technical"), "bullish_low", "LONG") not in keys


def test_finds_a_strong_real_analog_and_separates_by_regime():
    """AYNI domain ikilisi iki farklı rejimde çok farklı performans
    gösteriyor — üçüncü eksenin (market_regime) gerçekten ayırt edici
    olduğunu doğrular."""
    records = []
    for i in range(40):
        records.append(_record({"technical", "macro"}, "bullish_low", "LONG", i < 38))  # %95
    for i in range(40):
        records.append(_record({"technical", "macro"}, "bearish_high", "LONG", i < 8))  # %20

    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    bullish = next(a for a in result["analogs"] if a["market_regime"] == "bullish_low")
    bearish = next(a for a in result["analogs"] if a["market_regime"] == "bearish_high")
    assert bullish["win_rate"] == 0.95
    assert bearish["win_rate"] == 0.20
    assert bullish["sample_size"] == 40
    assert bearish["sample_size"] == 40


def test_direction_is_a_separate_grouping_axis():
    """AYNI domain ikilisi + AYNI rejim ama farklı yön — ayrı hücreler
    olarak raporlanmalı (kullanıcının P(LONG)/P(SHORT) ayrımı isteği)."""
    records = []
    for i in range(30):
        records.append(_record({"technical", "macro"}, "bullish_low", "LONG", i < 27))
    for i in range(30):
        records.append(_record({"technical", "macro"}, "bullish_low", "SHORT", i < 6))

    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    long_analog = next(a for a in result["analogs"] if a["direction"] == "LONG")
    short_analog = next(a for a in result["analogs"] if a["direction"] == "SHORT")
    assert long_analog["win_rate"] == 0.90
    assert short_analog["win_rate"] == 0.20


def test_reversing_is_a_separate_grouping_axis():
    """Faz 404 — dördüncü eksen: AYNI domain ikilisi + AYNI rejim + AYNI
    yön ama piyasa tersine dönüyor mu dönmüyor mu farklı — ayrı hücreler
    olarak raporlanmalı (direction'ın kendi ayrı-eksen testiyle AYNI
    desen)."""
    records = []
    for i in range(30):
        records.append(_record({"technical", "macro"}, "bullish_low", "LONG", i < 27, reversing=False))
    for i in range(30):
        records.append(_record({"technical", "macro"}, "bullish_low", "LONG", i < 6, reversing=True))

    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    calm = next(a for a in result["analogs"] if a["reversing"] is False)
    reversing = next(a for a in result["analogs"] if a["reversing"] is True)
    assert calm["win_rate"] == 0.90
    assert reversing["win_rate"] == 0.20


def test_records_with_missing_or_non_bool_reversing_are_excluded_fail_closed():
    """Faz 404 — reversing SADECE Faz 401'den (2026-09-01) sonraki
    kararlarda var; eski kararlarda hiç yok (None). İcat edilmiş bir
    reversing değeri asla varsayılmamalı — bu kayıtlar örneklemden
    tamamen dışlanır."""
    records = [
        {"agreeing_domains": frozenset({"technical", "macro"}), "market_regime": "bullish_low",
         "direction": "LONG", "win": True, "closed_at": None, "reversing": None},
        {"agreeing_domains": frozenset({"technical", "macro"}), "market_regime": "bullish_low",
         "direction": "LONG", "win": True, "closed_at": None},  # reversing hiç yok
    ]
    result = compute_historical_analogs(records)
    assert result == {"analogs": [], "baseline_win_rate": None, "baseline_sample_size": 0}


def test_gate_eligible_requires_fdr_and_oos_and_effective_sample_size_together():
    # Faz 422 — kullanıcı bulgusu: gate_eligible olan analogların TAMAMI
    # distinct_days=2 çıkıyordu (sadece 2 farklı gün). timedelta(days=i)
    # kullanılıyor (hours=i DEĞİL) — yeni min_distinct_days=5 şartını da
    # gerçekten test etsin diye, kayıtlar 40 FARKLI takvim gününe yayılıyor.
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    strong = [
        _record({"technical", "macro"}, "bullish_low", "LONG", i % 10 != 0, base_time + timedelta(days=i))
        for i in range(40)
    ]
    baseline = [
        _record({"quant"}, "bullish_low", "LONG", i < 10, base_time + timedelta(days=i))
        for i in range(40)
    ]
    result = compute_historical_analogs(strong + baseline, combination_sizes=(2,), min_group_size=20)
    analog = next(a for a in result["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog["fdr_significant"] is True
    assert analog["oos_survival"] is True
    assert analog["effective_sample_size"] >= 20
    assert analog["distinct_days"] >= 5
    assert analog["gate_eligible"] is True

    # closed_at yoksa (oos_survival=None) AYNI güçlü desen bile gate_eligible=False olmalı.
    strong_no_dates = [_record({"technical", "macro"}, "bullish_low", "LONG", i % 10 != 0) for i in range(40)]
    baseline_no_dates = [_record({"quant"}, "bullish_low", "LONG", i < 10) for i in range(40)]
    result2 = compute_historical_analogs(strong_no_dates + baseline_no_dates, combination_sizes=(2,), min_group_size=20)
    analog2 = next(a for a in result2["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog2["oos_survival"] is None
    assert analog2["gate_eligible"] is False


def test_noise_does_not_survive_fdr():
    """Rastgele/dengeli win-loss dağılımı (baseline'dan istatistiksel
    olarak ayırt edilemez) fdr_significant=False kalmalı."""
    records = [_record({"technical", "macro"}, "bullish_low", "LONG", i % 2 == 0) for i in range(40)]
    records += [_record({"quant"}, "bullish_low", "LONG", i % 2 == 0) for i in range(40)]
    result = compute_historical_analogs(records, combination_sizes=(2,), min_group_size=20)
    analog = next(a for a in result["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog["fdr_significant"] is False
    assert analog["gate_eligible"] is False


def test_conditioning_incremental_value_compares_against_domain_only_baseline():
    """Faz 427 — kullanıcı isteği: "incremental value" ölçümü. Aynı ajan
    kombinasyonu iki farklı rejimde TAM ZIT sonuç veriyorsa, her hücrenin
    win_rate'i domain-only (rejimden bağımsız, TÜM kayıtlar havuzlanmış)
    ortalamaya göre eşit ve zıt yönde bir conditioning_incremental_value
    üretmeli."""
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    good_regime = [
        _record({"technical", "macro"}, "bullish_low", "LONG", True, base_time + timedelta(days=i))
        for i in range(20)
    ]
    bad_regime = [
        _record({"technical", "macro"}, "bearish_low", "LONG", False, base_time + timedelta(days=i))
        for i in range(20)
    ]
    baseline = [_record({"quant"}, "bullish_low", "LONG", i % 2 == 0) for i in range(40)]
    result = compute_historical_analogs(
        good_regime + bad_regime + baseline, combination_sizes=(2,), min_group_size=20,
    )
    good = next(
        a for a in result["analogs"]
        if set(a["domains"]) == {"technical", "macro"} and a["market_regime"] == "bullish_low"
    )
    bad = next(
        a for a in result["analogs"]
        if set(a["domains"]) == {"technical", "macro"} and a["market_regime"] == "bearish_low"
    )
    # domain-only (rejimden bağımsız) havuz: 20 kazanan + 20 kaybeden -> %50.
    assert good["win_rate"] == 1.0
    assert bad["win_rate"] == 0.0
    assert good["conditioning_incremental_value"] == 0.5
    assert bad["conditioning_incremental_value"] == -0.5


def test_coverage_pct_reflects_share_of_total_valid_sample():
    """coverage_pct = hücrenin gerçek örneklem sayısı / TÜM geçerli
    kayıtların sayısı — yeni bir hesaplama değil, zaten var olan iki
    alandan türetilen şeffaflık amaçlı bir oran."""
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    strong = [
        _record({"technical", "macro"}, "bullish_low", "LONG", i % 10 != 0, base_time + timedelta(days=i))
        for i in range(20)
    ]
    baseline = [_record({"quant"}, "bullish_low", "LONG", i < 10) for i in range(80)]
    result = compute_historical_analogs(strong + baseline, combination_sizes=(2,), min_group_size=20)
    analog = next(a for a in result["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog["coverage_pct"] == round(20 / 100, 6)


def test_harmful_eligible_requires_fdr_and_negative_oos_and_effective_sample_size_together():
    """Faz 428 — kullanıcı isteği: "Negative Evidence" — gate_eligible'ın
    TAM SİMETRİK negatif hâli. Bir kombinasyon HİÇ kazanmıyorsa (baseline'ın
    çok altında, OOS'ta da AYNI kalıyorsa) harmful_eligible=True olmalı."""
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    harmful = [
        _record({"macro", "order_flow"}, "bearish_low", "SHORT", False, base_time + timedelta(days=i))
        for i in range(40)
    ]
    baseline = [
        _record({"quant"}, "bearish_low", "SHORT", i < 30, base_time + timedelta(days=i))
        for i in range(40)
    ]
    result = compute_historical_analogs(harmful + baseline, combination_sizes=(2,), min_group_size=20)
    analog = next(a for a in result["analogs"] if set(a["domains"]) == {"macro", "order_flow"})
    assert analog["win_rate"] == 0.0
    assert analog["win_rate_delta_vs_baseline"] <= -0.20
    assert analog["fdr_significant"] is True
    assert analog["oos_survival_negative"] is True
    assert analog["oos_survival"] is False
    assert analog["effective_sample_size"] >= 20
    assert analog["distinct_days"] >= 5
    assert analog["harmful_eligible"] is True
    # Aynı hücre asla gate_eligible (pozitif) OLAMAZ -- iki bayrak
    # birbirini dışlamalı.
    assert analog["gate_eligible"] is False


def test_harmful_eligible_is_false_for_a_neutral_or_positive_pattern():
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    strong = [
        _record({"technical", "macro"}, "bullish_low", "LONG", i % 10 != 0, base_time + timedelta(days=i))
        for i in range(40)
    ]
    baseline = [
        _record({"quant"}, "bullish_low", "LONG", i < 10, base_time + timedelta(days=i))
        for i in range(40)
    ]
    result = compute_historical_analogs(strong + baseline, combination_sizes=(2,), min_group_size=20)
    analog = next(a for a in result["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog["gate_eligible"] is True
    assert analog["harmful_eligible"] is False


def test_apply_confidence_shrinkage_never_decreases_below_strength_before():
    """Faz 433 — stage'in kendi 'SADECE YÜKSELTİR' ilkesiyle AYNI garanti,
    fonksiyon seviyesinde: raw_win_rate strength_before'ın altındaysa
    (yükseltmeyen bir eşleşme) hiç değişiklik yapılmamalı."""
    result = apply_confidence_shrinkage(
        raw_win_rate=0.5, effective_sample_size=100.0, strength_before=0.7,
    )
    assert result == 0.7


def test_apply_confidence_shrinkage_is_capped_at_max_uplift():
    result = apply_confidence_shrinkage(
        raw_win_rate=0.99, effective_sample_size=1000.0, strength_before=0.1,
    )
    assert abs(result - (0.1 + 0.3)) < 1e-9


def test_apply_confidence_shrinkage_weak_evidence_gets_less_uplift_than_strong():
    """AYNI ham win_rate/strength_before, sadece effective_sample_size
    farklı — daha güçlü kanıt daha büyük (ama hâlâ tavana kadar) bir
    uplift'e izin vermeli."""
    weak = apply_confidence_shrinkage(raw_win_rate=0.85, effective_sample_size=5.0, strength_before=0.4)
    strong = apply_confidence_shrinkage(raw_win_rate=0.85, effective_sample_size=200.0, strength_before=0.4)
    assert weak < strong
    assert weak > 0.4
    assert strong <= 0.4 + 0.3


def test_apply_confidence_shrinkage_matches_hand_computed_example():
    """eff_n=26, shrinkage_k=20 (varsayılan) -> weight=26/46≈0.5652,
    ham uplift=0.5652*(0.951-0.3521)≈0.3386 -> 0.3 tavanına takılır."""
    result = apply_confidence_shrinkage(
        raw_win_rate=0.951, effective_sample_size=26.0, strength_before=0.3521,
    )
    assert abs(result - 0.6521) < 1e-4


def _dated_group(wins: list[bool]) -> list[dict]:
    base = datetime(2026, 6, 1, tzinfo=UTC)
    return [{"win": w, "closed_at": base + timedelta(days=i)} for i, w in enumerate(wins)]


def test_compute_recency_decay_detects_a_declining_pattern():
    """Faz 434 — kullanıcı isteği: "Temporal Decay/Recency" (GPT'nin
    örneği: bir örüntü zamanla bozuluyor olabilir, aggregate sayı bunu
    gizler). Erken yarı %90, geç yarı %20 -> belirgin negatif decay."""
    wins = [i < 18 for i in range(20)] + [i < 4 for i in range(20)]  # 20 erken (%90) + 20 geç (%20)
    result = compute_recency_decay(_dated_group(wins))
    assert result["early_win_rate"] == 0.9
    assert result["late_win_rate"] == 0.2
    assert result["decay"] == -0.7
    assert result["early_n"] == 20
    assert result["late_n"] == 20


def test_compute_recency_decay_detects_an_improving_pattern():
    wins = [i < 4 for i in range(20)] + [i < 18 for i in range(20)]  # 20 erken (%20) + 20 geç (%90)
    result = compute_recency_decay(_dated_group(wins))
    assert result["decay"] == 0.7


def test_compute_recency_decay_is_none_when_either_half_is_too_small():
    """MIN_OOS_TEST_SIZE=8 — 10 kayıtlık bir grupta her iki yarı da
    bunun altında kalır, icat edilmiş bir eğim üretilmemeli."""
    wins = [True] * 10
    assert compute_recency_decay(_dated_group(wins)) is None


def test_compute_recency_decay_is_none_without_closed_at():
    records = [{"win": True, "closed_at": None} for _ in range(40)]
    assert compute_recency_decay(records) is None


def test_recency_decay_is_attached_to_historical_analog_candidates():
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    records = [
        _record({"technical", "macro"}, "bullish_low", "LONG", i < 18 if i < 20 else i < 24,
                base_time + timedelta(days=i))
        for i in range(40)
    ]
    baseline = [
        _record({"quant"}, "bullish_low", "LONG", i < 20, base_time + timedelta(days=i))
        for i in range(40)
    ]
    result = compute_historical_analogs(records + baseline, combination_sizes=(2,), min_group_size=20)
    analog = next(a for a in result["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert analog["recency_decay"] is not None


# Faz 445 (2026-09-07) — "Direction Analog": compute_historical_analogs()'u
# DEĞİŞTİRMİYOR, 'win'i (pnl>0) 'forward_label==hedef' ile değiştirip AYNI
# fonksiyonu üç kez (UP/DOWN/NEUTRAL) çağırıyor.
def test_direction_analogs_returns_exactly_the_three_labels():
    result = compute_direction_analogs([_direction_record({"technical", "macro"}, "bullish_low", "LONG", "UP")])
    assert set(result.keys()) == set(DIRECTION_LABELS)


def test_direction_analogs_finds_a_strong_up_pattern_and_the_same_cell_is_weak_for_down():
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    strong = [
        _direction_record({"technical", "macro"}, "bullish_low", "LONG",
                           "UP" if i % 10 != 0 else "DOWN", base_time + timedelta(days=i))
        for i in range(40)
    ]
    baseline = [
        _direction_record({"quant"}, "bullish_low", "LONG",
                           "UP" if i < 10 else "DOWN", base_time + timedelta(days=i))
        for i in range(40)
    ]
    result = compute_direction_analogs(strong + baseline, combination_sizes=(2,), min_group_size=20)

    up_analog = next(a for a in result["UP"]["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert up_analog["fdr_significant"] is True
    assert up_analog["oos_survival"] is True
    assert up_analog["distinct_days"] >= 5
    assert up_analog["gate_eligible"] is True
    assert up_analog["win_rate"] > 0.85  # P(UP | bu bağlam)

    # AYNI hücre, DOWN sorusuna karşı simetrik olarak ZAYIF olmalı --
    # icat edilmiş bir DOWN sinyali üretilmemeli.
    down_analog = next(a for a in result["DOWN"]["analogs"] if set(a["domains"]) == {"technical", "macro"})
    assert down_analog["win_rate"] < 0.15


def test_direction_analogs_excludes_records_without_a_valid_forward_label():
    records = [
        _direction_record({"technical", "macro"}, "bullish_low", "LONG", None),
        {**_direction_record({"technical", "macro"}, "bullish_low", "LONG", "UP"), "forward_label": "sideways"},
    ]
    result = compute_direction_analogs(records)
    for label in DIRECTION_LABELS:
        assert result[label]["baseline_sample_size"] == 0


def test_direction_analogs_baseline_reflects_unconditional_label_share():
    """baseline_win_rate, o etiketin GENEL (koşulsuz) payını yansıtmalı --
    P(UP) gibi -- Faz 441'in gerçek UP/DOWN/NEUTRAL dağılımıyla AYNI
    yorum: bir analog hücresinin win_rate'i bu tabana göre anlamlı olur."""
    records = (
        [_direction_record({"technical"}, "bullish_low", "LONG", "UP") for _ in range(6)]
        + [_direction_record({"technical"}, "bullish_low", "LONG", "DOWN") for _ in range(3)]
        + [_direction_record({"technical"}, "bullish_low", "LONG", "NEUTRAL") for _ in range(1)]
    )
    result = compute_direction_analogs(records)
    assert result["UP"]["baseline_win_rate"] == 0.6
    assert result["DOWN"]["baseline_win_rate"] == 0.3
    assert result["NEUTRAL"]["baseline_win_rate"] == 0.1
