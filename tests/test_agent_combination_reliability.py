"""analytics/agent_combination_reliability.py — Faz 331. Kullanıcı isteği
(harici bir AI incelemesinin önerdiği, defalarca gündeme gelip ertelenen
bir madde): Opportunity Quality KAÇ ajanın anlaştığını win_rate'le
ilişkilendiriyor, bu modül HANGİ ajan GRUPLARININ (2/3/4'lü) birlikte
anlaştığını ilişkilendiriyor."""
from datetime import UTC, datetime, timedelta

from analytics.agent_combination_reliability import (
    agreeing_domains_for_decision,
    compute_combination_reliability,
)
from contracts.agent import AgentDomain, AgentOpinion


def _opinion_dict(domain: AgentDomain, direction: str, confidence: float = 0.8) -> dict:
    o = AgentOpinion(domain=domain, direction=direction, confidence=confidence)
    o.recalculate()
    return o.model_dump(mode="json")


def test_agreeing_domains_returns_none_for_wait_direction():
    contributions = [_opinion_dict(AgentDomain.TECHNICAL, "LONG")]
    assert agreeing_domains_for_decision(contributions, "WAIT") is None
    assert agreeing_domains_for_decision(contributions, "") is None


def test_agreeing_domains_returns_none_when_no_real_opinions():
    assert agreeing_domains_for_decision([{"type": "market_snapshot", "data": {}}], "LONG") is None


def test_agreeing_domains_only_includes_domains_matching_final_direction():
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG"),
        _opinion_dict(AgentDomain.MACRO, "LONG"),
        _opinion_dict(AgentDomain.QUANT, "SHORT"),
        _opinion_dict(AgentDomain.PATTERN, "WAIT"),
    ]
    result = agreeing_domains_for_decision(contributions, "LONG")
    assert result == frozenset({"technical", "macro"})


def test_combination_reliability_empty_input_is_fail_closed():
    result = compute_combination_reliability([])
    assert result == {"pairs": [], "baseline_win_rate": None, "baseline_sample_size": 0}


def test_combination_reliability_excludes_groups_below_min_group_size():
    records = [
        {"agreeing_domains": frozenset({"technical", "macro"}), "win": True}
        for _ in range(5)
    ] + [
        {"agreeing_domains": frozenset({"quant"}), "win": False}
        for _ in range(50)
    ]
    result = compute_combination_reliability(records, combination_sizes=(2,), min_group_size=20)
    group_keys = {tuple(p["domains"]) for p in result["pairs"]}
    assert ("macro", "technical") not in group_keys  # sadece 5 örnek, eşiğin altında


def test_combination_reliability_finds_a_strong_real_pair():
    """technical+macro ikilisi birlikte anlaştığında %95 kazanma, geri
    kalan (tek başına quant anlaştığında) %20 kazanma — ikilinin genel
    ortalamadan (baseline) belirgin şekilde yüksek çıkması ve FDR'ı
    geçmesi bekleniyor."""
    records = []
    for i in range(40):
        records.append({
            "agreeing_domains": frozenset({"technical", "macro"}),
            "win": i < 38,  # 38/40 = %95
        })
    for i in range(40):
        records.append({
            "agreeing_domains": frozenset({"quant"}),
            "win": i < 8,  # 8/40 = %20
        })

    result = compute_combination_reliability(records, combination_sizes=(2,), min_group_size=20)
    assert result["baseline_sample_size"] == 80
    assert abs(result["baseline_win_rate"] - 0.575) < 1e-6  # (38+8)/80

    top = result["pairs"][0]
    assert set(top["domains"]) == {"technical", "macro"}
    assert top["combination_size"] == 2
    assert top["sample_size"] == 40
    assert abs(top["win_rate"] - 0.95) < 1e-6
    assert top["win_rate_delta_vs_baseline"] > 0
    assert top["fdr_significant"] is True


def test_combination_reliability_surfaces_larger_groups_once_enough_data_exists():
    """Kullanıcı isteği (2026-08-28): "örneklem arttıkça kombinasyon boyutu
    (A,B → A,B,C → A,B,C,D) organik olarak büyüyemez mi?" Burada 4 ajan
    (onchain/order_flow/pattern/quant) 30 işlemde HEP BİRLİKTE anlaşıyor —
    varsayılan combination_sizes=(2,3,4) ile 4'lü grubun KENDİSİ de (tek
    başına, min_group_size=20'yi geçtiği için) tabloda görünmeli, ayrı bir
    'mod' değişikliği gerekmeden."""
    records = [
        {"agreeing_domains": frozenset({"onchain", "order_flow", "pattern", "quant"}), "win": i < 27}
        for i in range(30)  # 27/30 = %90
    ]
    result = compute_combination_reliability(records, min_group_size=20)

    quad = next(p for p in result["pairs"] if p["combination_size"] == 4)
    assert set(quad["domains"]) == {"onchain", "order_flow", "pattern", "quant"}
    assert quad["sample_size"] == 30
    assert abs(quad["win_rate"] - 0.9) < 1e-6

    triple_sizes = {p["combination_size"] for p in result["pairs"]}
    assert {2, 3, 4} <= triple_sizes  # 2'li/3'lü alt-gruplar da AYNI 30 işlemden kendiliğinden çıkmalı


def test_combination_reliability_reports_shared_trade_overlap_between_related_groups():
    """Kullanıcı bulgusu (2026-08-28): onchain'in 5 gerçek çifti dashboard'da
    BİREBİR aynı %100.0/+29.4 puanı veriyordu — 5 bağımsız bulgu mu, aynı
    işlemlerin tekrar sayımı mı belli değildi. Burada 3 ajan (onchain/
    order_flow/pattern) AYNI 25 işlemde hep birlikte anlaşıyor — her ikili
    (onchain-order_flow, onchain-pattern, order_flow-pattern) VE bunları
    kapsayan 3'lü grup TAM AYNI işlem kümesini paylaşmalı (overlap=1.0).
    Ayrı/örtüşmeyen bir çift (macro-relative_strength, farklı 25 işlem)
    ise overlap=0.0 olmalı."""
    shared_records = [
        {"agreeing_domains": frozenset({"onchain", "order_flow", "pattern"}), "win": True}
        for _ in range(25)
    ]
    independent_records = [
        {"agreeing_domains": frozenset({"macro", "relative_strength"}), "win": i < 10}
        for i in range(25)
    ]
    result = compute_combination_reliability(shared_records + independent_records, min_group_size=20)

    onchain_order_flow = next(
        p for p in result["pairs"]
        if p["combination_size"] == 2 and set(p["domains"]) == {"onchain", "order_flow"}
    )
    assert onchain_order_flow["max_shared_trade_overlap_pct"] == 1.0
    assert onchain_order_flow["max_shared_trade_overlap_with"] is not None
    assert set(onchain_order_flow["max_shared_trade_overlap_with"]) & {"onchain", "order_flow"}

    macro_rs = next(
        p for p in result["pairs"]
        if p["combination_size"] == 2 and set(p["domains"]) == {"macro", "relative_strength"}
    )
    assert macro_rs["max_shared_trade_overlap_pct"] == 0.0
    assert macro_rs["max_shared_trade_overlap_with"] is None


def test_combination_reliability_noise_does_not_survive_fdr():
    """Gerçek bir edge olmadan (tüm gruplar AYNI genel win_rate'e sahip,
    rastgele varyasyon dışında), tek tek p<0.05 testi şans eseri bazı
    grupları "anlamlı" sayabilir ama FDR bunların çoğunu elemeli."""
    import random

    rng = random.Random(11)
    domains = [d.value for d in list(AgentDomain)[:9]]
    records = []
    for _ in range(400):
        # Her karar rastgele 2-4 domain'in anlaştığı bir küme + rastgele
        # ~%55 kazanma olasılığı (gerçek bir edge yok, sadece gürültü).
        agreeing = frozenset(rng.sample(domains, k=rng.randint(2, 4)))
        records.append({"agreeing_domains": agreeing, "win": rng.random() < 0.55})

    result = compute_combination_reliability(records, min_group_size=20)
    fdr_survivors = [p for p in result["pairs"] if p["fdr_significant"]]
    naive_significant = [
        p for p in result["pairs"]
        if abs(p["win_rate"] - result["baseline_win_rate"]) > 0  # kaba bir üst sınır karşılaştırması
    ]
    # Gerçek edge yokken FDR'ı geçen grup sayısı, ham farkı olan grup
    # sayısından belirgin şekilde az olmalı (tam sıfır garantisi yok,
    # ama çoğunluğu elenmeli).
    assert len(fdr_survivors) <= len(naive_significant)


def test_effective_sample_size_discounts_fully_overlapping_groups_to_near_zero():
    """Faz 373 — kullanıcı isteği: max_shared_trade_overlap_pct SADECE bir
    uyarı olarak duruyordu, "gerçekte kaç bağımsız kanıt var" sorusuna
    doğrudan cevap vermiyordu. Tam örtüşen (overlap=1.0) bir grup için
    effective_sample_size sıfıra yakın olmalı; hiç örtüşmeyen bir grup
    için ham sample_size'a eşit kalmalı."""
    shared_records = [
        {"agreeing_domains": frozenset({"onchain", "order_flow", "pattern"}), "win": True}
        for _ in range(25)
    ]
    independent_records = [
        {"agreeing_domains": frozenset({"macro", "relative_strength"}), "win": i < 10}
        for i in range(25)
    ]
    result = compute_combination_reliability(shared_records + independent_records, min_group_size=20)

    onchain_order_flow = next(
        p for p in result["pairs"]
        if p["combination_size"] == 2 and set(p["domains"]) == {"onchain", "order_flow"}
    )
    assert onchain_order_flow["effective_sample_size"] == 0.0  # 25 * (1 - 1.0)

    macro_rs = next(
        p for p in result["pairs"]
        if p["combination_size"] == 2 and set(p["domains"]) == {"macro", "relative_strength"}
    )
    assert macro_rs["effective_sample_size"] == 25.0  # 25 * (1 - 0.0)


def test_incremental_value_is_positive_when_full_group_beats_all_pairwise_subsets():
    """3'lü grup (technical+macro+quant) gerçekten YENİ bilgi katıyor —
    HERHANGİ bir ikili alt-kümesinden (kendi başına bırakıldığında hep
    %50) belirgin şekilde daha iyi. incremental_value pozitif olmalı."""
    records = [
        {"agreeing_domains": frozenset({"technical", "macro", "quant"}), "win": i < 24}
        for i in range(25)  # 24/25 = %96
    ]
    for pair in (("technical", "macro"), ("technical", "quant"), ("macro", "quant")):
        records += [
            {"agreeing_domains": frozenset(pair), "win": i < 10}
            for i in range(20)  # 10/20 = %50, SADECE bu ikili (üçlü değil)
        ]

    result = compute_combination_reliability(records, combination_sizes=(2, 3), min_group_size=20)
    triple = next(p for p in result["pairs"] if p["combination_size"] == 3)
    assert triple["incremental_value"] is not None
    assert triple["incremental_value"] > 0.15  # ~%20.4 bekleniyor


def test_incremental_value_is_none_when_no_comparable_subset_exists():
    """En küçük boyuttaki (varsayılan combination_sizes ile 2'li) bir grup
    için karşılaştırılabilir bir (N-1)-alt-küme yok — incremental_value
    None kalmalı, icat edilmiş bir sıfır değil."""
    records = [
        {"agreeing_domains": frozenset({"technical", "macro"}), "win": i < 18}
        for i in range(20)
    ]
    result = compute_combination_reliability(records, combination_sizes=(2,), min_group_size=20)
    pair = result["pairs"][0]
    assert pair["incremental_value"] is None


def test_oos_survival_true_when_edge_persists_into_unseen_late_half():
    """Faz 373 — strategy_hypothesis_scanner.py'nin walk-forward ruhu: erken
    yarıda görülen bir örüntü, embargo boşluklu GEÇ yarıda da (baseline'ın
    üstünde) tekrar ediyorsa oos_survival=True."""
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    group_records = []
    # Erken yarı: yüksek kazanma. Geç yarı: YİNE yüksek kazanma (tekrarlanıyor).
    for i in range(40):
        group_records.append({
            "agreeing_domains": frozenset({"technical", "macro"}),
            "win": i % 10 != 0,  # %90 kazanma, baştan sona tutarlı
            "closed_at": base_time + timedelta(hours=i),
        })
    baseline_records = [
        {"agreeing_domains": frozenset({"quant"}), "win": i < 10, "closed_at": base_time + timedelta(hours=i)}
        for i in range(40)  # %25 kazanma — genel ortalamayı düşük tutar
    ]

    result = compute_combination_reliability(group_records + baseline_records, combination_sizes=(2,), min_group_size=20)
    pair = next(p for p in result["pairs"] if set(p["domains"]) == {"technical", "macro"})
    assert pair["oos_survival"] is True


def test_oos_survival_false_when_edge_reverses_in_late_half():
    """Erken yarıda güçlü, GEÇ yarıda baseline'a (ya da altına) dönen bir
    örüntü — "dar bir dönem artefaktı" ihtimali, oos_survival=False."""
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    group_records = []
    for i in range(20):
        group_records.append({
            "agreeing_domains": frozenset({"technical", "macro"}),
            "win": True,  # erken yarı: %100
            "closed_at": base_time + timedelta(hours=i),
        })
    for i in range(20):
        group_records.append({
            "agreeing_domains": frozenset({"technical", "macro"}),
            "win": i < 3,  # geç yarı: %15 — çöktü
            "closed_at": base_time + timedelta(hours=40 + i),
        })
    baseline_records = [
        {"agreeing_domains": frozenset({"quant"}), "win": i < 20, "closed_at": base_time + timedelta(hours=i)}
        for i in range(40)  # %50 baseline
    ]

    result = compute_combination_reliability(group_records + baseline_records, combination_sizes=(2,), min_group_size=20)
    pair = next(p for p in result["pairs"] if set(p["domains"]) == {"technical", "macro"})
    assert pair["oos_survival"] is False


def test_oos_survival_none_when_closed_at_missing():
    """closed_at hiç yoksa (zaman sırası kurulamaz) oos_survival None
    kalmalı — icat edilmiş bir True/False üretilmez."""
    records = [
        {"agreeing_domains": frozenset({"technical", "macro"}), "win": i < 18}
        for i in range(20)
    ]
    result = compute_combination_reliability(records, combination_sizes=(2,), min_group_size=20)
    pair = result["pairs"][0]
    assert pair["oos_survival"] is None


def test_gate_eligible_requires_fdr_and_oos_and_effective_sample_size_together():
    """gate_eligible SADECE üçü de (fdr_significant + oos_survival=True +
    effective_sample_size >= min_group_size) birlikte sağlandığında True."""
    base_time = datetime(2026, 8, 1, tzinfo=UTC)
    # Güçlü, tekrarlanan, tam örneklemli bir edge — gate_eligible=True beklenir.
    strong_records = [
        {
            "agreeing_domains": frozenset({"technical", "macro"}),
            "win": i % 10 != 0,
            "closed_at": base_time + timedelta(hours=i),
        }
        for i in range(40)
    ]
    baseline_records = [
        {"agreeing_domains": frozenset({"quant"}), "win": i < 10, "closed_at": base_time + timedelta(hours=i)}
        for i in range(40)
    ]
    result = compute_combination_reliability(strong_records + baseline_records, combination_sizes=(2,), min_group_size=20)
    pair = next(p for p in result["pairs"] if set(p["domains"]) == {"technical", "macro"})
    assert pair["fdr_significant"] is True
    assert pair["oos_survival"] is True
    assert pair["effective_sample_size"] >= 20
    assert pair["gate_eligible"] is True

    # closed_at olmayan (oos_survival=None) AYNI güçlü desen — gate_eligible=False olmalı.
    strong_no_dates = [
        {"agreeing_domains": frozenset({"technical", "macro"}), "win": i % 10 != 0}
        for i in range(40)
    ]
    baseline_no_dates = [{"agreeing_domains": frozenset({"quant"}), "win": i < 10} for i in range(40)]
    result2 = compute_combination_reliability(strong_no_dates + baseline_no_dates, combination_sizes=(2,), min_group_size=20)
    pair2 = next(p for p in result2["pairs"] if set(p["domains"]) == {"technical", "macro"})
    assert pair2["oos_survival"] is None
    assert pair2["gate_eligible"] is False
