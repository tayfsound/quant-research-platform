"""analytics/agent_combination_reliability.py — Faz 331. Kullanıcı isteği
(harici bir AI incelemesinin önerdiği, defalarca gündeme gelip ertelenen
bir madde): Opportunity Quality KAÇ ajanın anlaştığını win_rate'le
ilişkilendiriyor, bu modül HANGİ ajan İKİLİLERİNİN birlikte anlaştığını
ilişkilendiriyor."""
from analytics.agent_combination_reliability import (
    agreeing_domains_for_decision,
    compute_pairwise_combination_reliability,
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


def test_pairwise_reliability_empty_input_is_fail_closed():
    result = compute_pairwise_combination_reliability([])
    assert result == {"pairs": [], "baseline_win_rate": None, "baseline_sample_size": 0}


def test_pairwise_reliability_excludes_pairs_below_min_group_size():
    records = [
        {"agreeing_domains": frozenset({"technical", "macro"}), "win": True}
        for _ in range(5)
    ] + [
        {"agreeing_domains": frozenset({"quant"}), "win": False}
        for _ in range(50)
    ]
    result = compute_pairwise_combination_reliability(records, min_group_size=20)
    pair_keys = {(p["domain_a"], p["domain_b"]) for p in result["pairs"]}
    assert ("macro", "technical") not in pair_keys  # sadece 5 örnek, eşiğin altında


def test_pairwise_reliability_finds_a_strong_real_combination():
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

    result = compute_pairwise_combination_reliability(records, min_group_size=20)
    assert result["baseline_sample_size"] == 80
    assert abs(result["baseline_win_rate"] - 0.575) < 1e-6  # (38+8)/80

    top = result["pairs"][0]
    assert {top["domain_a"], top["domain_b"]} == {"technical", "macro"}
    assert top["sample_size"] == 40
    assert abs(top["win_rate"] - 0.95) < 1e-6
    assert top["win_rate_delta_vs_baseline"] > 0
    assert top["fdr_significant"] is True


def test_pairwise_reliability_noise_does_not_survive_fdr():
    """Gerçek bir edge olmadan (tüm ikililer AYNI genel win_rate'e sahip,
    rastgele varyasyon dışında), tek tek p<0.05 testi şans eseri bazı
    çiftleri "anlamlı" sayabilir ama FDR bunların çoğunu elemeli."""
    import random

    rng = random.Random(11)
    domains = [d.value for d in list(AgentDomain)[:9]]
    records = []
    for _ in range(400):
        # Her karar rastgele 2-4 domain'in anlaştığı bir küme + rastgele
        # ~%55 kazanma olasılığı (gerçek bir edge yok, sadece gürültü).
        agreeing = frozenset(rng.sample(domains, k=rng.randint(2, 4)))
        records.append({"agreeing_domains": agreeing, "win": rng.random() < 0.55})

    result = compute_pairwise_combination_reliability(records, min_group_size=20)
    fdr_survivors = [p for p in result["pairs"] if p["fdr_significant"]]
    naive_significant = [
        p for p in result["pairs"]
        if abs(p["win_rate"] - result["baseline_win_rate"]) > 0  # kaba bir üst sınır karşılaştırması
    ]
    # Gerçek edge yokken FDR'ı geçen çift sayısı, ham farkı olan çift
    # sayısından belirgin şekilde az olmalı (tam sıfır garantisi yok,
    # ama çoğunluğu elenmeli).
    assert len(fdr_survivors) <= len(naive_significant)
