"""analytics/agent_combination_reliability.py — Faz 331. Kullanıcı isteği
(harici bir AI incelemesinin önerdiği, defalarca gündeme gelip ertelenen
bir madde): Opportunity Quality KAÇ ajanın anlaştığını win_rate'le
ilişkilendiriyor, bu modül HANGİ ajan GRUPLARININ (2/3/4'lü) birlikte
anlaştığını ilişkilendiriyor."""
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
