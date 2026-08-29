"""Feature Relationship (redundancy matrix + koşullu IC) testleri — Faz 368."""
from analytics.feature_ic import compute_feature_ic
from analytics.feature_relationship import (
    compute_conditional_ic,
    compute_feature_redundancy,
    compute_multivariable_residualized_ic,
    compute_redundancy_clusters,
)


def _trade(entry: float, exit: float, feature_contributions: dict[str, float], domain: str = "technical") -> dict:
    return {
        "entry_price": entry,
        "exit_price": exit,
        "agent_contributions": [
            {"agent_id": "x", "domain": domain, "feature_contributions": feature_contributions},
        ],
    }


def test_two_perfectly_redundant_features_get_correlation_near_one():
    """trend/ema_alignment gibi: her trade'de BİRLİKTE, BİREBİR aynı
    örüntüyle ateşleniyorlar — bu turda gerçek veride bulunan r=1.000
    çakışmasının senteziği."""
    trades = [
        _trade(100.0, 101.0, {"trend": 1.0 + i * 0.01, "ema_alignment": 1.0 + i * 0.01})
        for i in range(25)
    ]
    result = compute_feature_redundancy(trades, min_sample_size=20)
    assert "ema_alignment|trend" in result
    assert result["ema_alignment|trend"]["correlation"] > 0.999
    assert result["ema_alignment|trend"]["sample_size"] == 25


def test_two_independent_features_get_low_correlation():
    trades = []
    for i in range(30):
        a = 1.0 + i * 0.01
        b = 1.0 if i % 2 == 0 else -1.0  # a ile ilişkisiz, kendi içinde değişken
        trades.append(_trade(100.0, 101.0, {"a_signal": a, "b_signal": b}))
    result = compute_feature_redundancy(trades, min_sample_size=20)
    assert abs(result["a_signal|b_signal"]["correlation"]) < 0.3


def test_pair_key_is_alphabetically_sorted_regardless_of_dict_order():
    trades = [
        _trade(100.0, 101.0, {"zeta": 1.0 + i * 0.01, "alpha": 1.0 + i * 0.01})
        for i in range(25)
    ]
    result = compute_feature_redundancy(trades, min_sample_size=20)
    assert "alpha|zeta" in result
    assert "zeta|alpha" not in result


def test_insufficient_sample_size_pair_is_excluded_fail_closed():
    trades = [_trade(100.0, 101.0, {"a": 1.0, "b": 1.0 + i}) for i in range(5)]
    result = compute_feature_redundancy(trades, min_sample_size=20)
    assert result == {}


def test_zero_variance_feature_pair_is_excluded():
    trades = [_trade(100.0, 101.0, {"a": 1.0, "b": 1.0 + i}) for i in range(30)]
    result = compute_feature_redundancy(trades, min_sample_size=20)
    assert "a|b" not in result


def test_features_that_never_co_occur_in_the_same_trade_are_not_paired():
    trades = [_trade(100.0, 101.0, {"only_a": 1.0 + i}) for i in range(15)]
    trades += [_trade(100.0, 101.0, {"only_b": 1.0 + i}) for i in range(15)]
    result = compute_feature_redundancy(trades, min_sample_size=20)
    assert result == {}


def test_conditional_ic_collapses_to_near_zero_for_a_fully_redundant_pair():
    """Bu turda gerçek veride bulunan örüntünün matematiksel kanıtı: a ve
    b BİREBİR aynı bilgiyi taşıyorsa (r_ab≈1), a'nın b'ye göre koşullu
    IC'si tanımsız/None olmalı (payda sıfıra yaklaşır) — icat edilmiş bir
    sayı ASLA dönmemeli."""
    trades = [
        _trade(100.0, 101.0 + i * 0.1, {"trend": 1.0 + i * 0.01, "ema_alignment": 1.0 + i * 0.01})
        for i in range(25)
    ]
    feature_ic = compute_feature_ic(trades, min_sample_size=20)
    redundancy = compute_feature_redundancy(trades, min_sample_size=20)
    result = compute_conditional_ic(trades, redundancy, feature_ic)

    assert result["trend"]["conditional_ic_given"]["ema_alignment"] is None
    assert result["ema_alignment"]["conditional_ic_given"]["trend"] is None
    assert result["trend"]["raw_ic"] == feature_ic["trend"]["ic"]


def test_conditional_ic_recovers_the_true_partial_correlation_formula():
    """Formülü elle seçilmiş, KAPALI-form doğrulanabilir bir senaryoyla
    kanıtla: r_ab, r_ay, r_by biliniyorken partial = (r_ay - r_ab*r_by) /
    sqrt((1-r_ab^2)(1-r_by^2)) — scipy'ye bağımlı olmadan elle hesaplanan
    beklenen değerle karşılaştırılıyor."""
    redundancy = {"a|b": {"correlation": 0.75, "sample_size": 50}}
    feature_ic = {
        "a": {"ic": 0.5, "p_value": 0.01, "sample_size": 50, "agent_domain": "technical"},
        "b": {"ic": 0.3, "p_value": 0.01, "sample_size": 50, "agent_domain": "technical"},
    }
    result = compute_conditional_ic([], redundancy, feature_ic)

    r_ab, r_ay, r_by = 0.75, 0.5, 0.3
    expected_a_given_b = round((r_ay - r_ab * r_by) / ((1 - r_ab**2) * (1 - r_by**2)) ** 0.5, 4)
    expected_b_given_a = round((r_by - r_ab * r_ay) / ((1 - r_ab**2) * (1 - r_ay**2)) ** 0.5, 4)

    assert result["a"]["conditional_ic_given"]["b"] == expected_a_given_b
    assert result["b"]["conditional_ic_given"]["a"] == expected_b_given_a


def test_conditional_ic_skips_pairs_below_the_redundancy_threshold():
    redundancy = {"a|b": {"correlation": 0.4, "sample_size": 50}}
    feature_ic = {
        "a": {"ic": 0.5, "p_value": 0.01, "sample_size": 50, "agent_domain": "technical"},
        "b": {"ic": 0.3, "p_value": 0.01, "sample_size": 50, "agent_domain": "technical"},
    }
    result = compute_conditional_ic([], redundancy, feature_ic, redundancy_threshold=0.7)
    assert result == {}


def test_conditional_ic_fails_closed_when_the_formula_produces_an_out_of_range_value():
    """Gerçek prod veriyle doğrulama sırasında bulunan gerçek bir bulgu:
    r_ab TAM 1.0 değil ama ona çok yakınken (ör. 0.99) payda neredeyse
    sıfıra iner ve kapalı-form formül [-1,1] dışında bir "korelasyon"
    üretebilir (gerçek veride +3.75 gibi). Bir kısmi korelasyon KATSAYISI
    tanım gereği HER ZAMAN [-1,1] içindedir — dışına çıkan sonuç gerçek
    bir bulgu değil, sayısal kararsızlığın kanıtıdır ve None'a düşmeli."""
    redundancy = {"a|b": {"correlation": 0.99, "sample_size": 50}}
    feature_ic = {
        "a": {"ic": 0.9, "p_value": 0.01, "sample_size": 50, "agent_domain": "technical"},
        "b": {"ic": -0.9, "p_value": 0.01, "sample_size": 50, "agent_domain": "technical"},
    }
    result = compute_conditional_ic([], redundancy, feature_ic)
    assert result["a"]["conditional_ic_given"]["b"] is None
    assert result["b"]["conditional_ic_given"]["a"] is None


def test_conditional_ic_skips_a_pair_missing_from_feature_ic():
    """redundancy'de bir çift olabilir ama IC hesaplanamamış (ör. min_
    sample_size altında) bir feature içerebilir — sessizce atlanmalı."""
    redundancy = {"a|no_ic": {"correlation": 0.9, "sample_size": 50}}
    feature_ic = {"a": {"ic": 0.5, "p_value": 0.01, "sample_size": 50, "agent_domain": "technical"}}
    result = compute_conditional_ic([], redundancy, feature_ic)
    assert result == {}


def test_redundancy_clusters_finds_true_cliques_not_transitive_chains():
    """Gerçek bulgu (2026-08-29): a-b ve b-c yüksek ama a-c hiç ölçülmemiş
    (ya da düşük) — bunlar "hepsi birbiriyle mutually redundant" (klik)
    DEĞİL, sadece b üzerinden zincirlenmiş. Bron-Kerbosch bunu doğru
    ayırmalı: {a,b} ve {b,c} AYRI maksimal klikler, {a,b,c} TEK bir küme
    olarak ASLA dönmemeli. d-e-f ÜÇÜNÜN DE birbiriyle yüksek olduğu
    (gerçek klik) durumda ise {d,e,f} TEK küme olarak dönmeli. g-h eşiğin
    altında (0.3) — hiçbir kümeye girmemeli."""
    redundancy = {
        "a|b": {"correlation": 0.9, "sample_size": 50},
        "b|c": {"correlation": 0.85, "sample_size": 50},
        # a-c KASITLI OLARAK yok/düşük — {a,b,c} gerçek bir klik değil.
        "d|e": {"correlation": 0.9, "sample_size": 50},
        "d|f": {"correlation": 0.85, "sample_size": 50},
        "e|f": {"correlation": 0.8, "sample_size": 50},  # üçü de mutually yüksek -> gerçek klik
        "g|h": {"correlation": 0.3, "sample_size": 50},
    }
    clusters = compute_redundancy_clusters(redundancy, redundancy_threshold=0.7)
    cluster_sets = [set(c) for c in clusters]

    assert {"a", "b"} in cluster_sets
    assert {"b", "c"} in cluster_sets
    assert {"a", "b", "c"} not in cluster_sets  # zincir, klik değil

    assert {"d", "e", "f"} in cluster_sets  # gerçek mutually-redundant klik

    assert not any({"g", "h"} <= s for s in cluster_sets)


def test_redundancy_clusters_empty_when_nothing_passes_threshold():
    redundancy = {"a|b": {"correlation": 0.2, "sample_size": 50}}
    assert compute_redundancy_clusters(redundancy, redundancy_threshold=0.7) == []


def test_residualized_ic_shows_near_duplicate_carries_no_extra_info():
    """dup1/dup2 neredeyse birebir aynı (gerçek veride bulunan r=1.000
    örüntüsünün sentezi). 'real' ise dup1/dup2'den TAMAMEN bağımsız AMA
    getiriyle gerçekten ilişkili. Beklenen: dup1'in residualized_ic'i
    ~0'a yakın (dup2 zaten neredeyse tamamını açıklıyor), real'inki ise
    ham korelasyonuna yakın kalmalı (dup1/dup2 real'i hiç açıklamıyor)."""
    import numpy as np

    rng = np.random.default_rng(7)
    n = 60
    dup1 = rng.normal(size=n)
    dup2 = dup1 + rng.normal(scale=0.001, size=n)  # neredeyse birebir aynı
    real = rng.normal(size=n)  # dup1/dup2'den bağımsız

    raw_return = dup1 * 0.001 + real * 0.02  # her ikisi de getiriye gerçekten katkılı

    trades = []
    for i in range(n):
        entry = 100.0
        exit_price = entry * (1 + raw_return[i])
        trades.append(_trade(entry, exit_price, {
            "dup1": float(dup1[i]), "dup2": float(dup2[i]), "real": float(real[i]),
        }))

    cluster = [frozenset({"dup1", "dup2", "real"})]
    result = compute_multivariable_residualized_ic(trades, cluster, min_sample_size=20)

    assert "dup1" in result and "real" in result
    assert abs(result["dup1"]["residualized_ic"]) < 0.3  # dup2 zaten açıklıyor
    assert abs(result["real"]["residualized_ic"]) > 0.5  # gerçekten bağımsız katkı


def test_residualized_ic_skips_clusters_above_max_size():
    cluster = [frozenset({"a", "b", "c", "d", "e"})]  # MAX_CLUSTER_SIZE=4'ü aşıyor
    trades = [_trade(100.0, 101.0, {"a": i, "b": i, "c": i, "d": i, "e": i}) for i in range(30)]
    assert compute_multivariable_residualized_ic(trades, cluster) == {}


def test_residualized_ic_skips_when_insufficient_common_sample():
    cluster = [frozenset({"a", "b", "c"})]
    trades = [_trade(100.0, 101.0, {"a": i, "b": i * 2, "c": i * 3}) for i in range(5)]  # min_sample_size'ın altında
    assert compute_multivariable_residualized_ic(trades, cluster, min_sample_size=20) == {}


def test_residualized_ic_skips_rank_deficient_design_matrix():
    """Kümedeki tahmin ediciler (target HARİÇ) birbirinin doğrusal katıysa
    (ör. p2 = 2*p1 tam olarak) tasarım matrisi ranksız — icat edilmiş bir
    sonuç yerine dürüstçe atlanmalı."""
    import numpy as np

    rng = np.random.default_rng(3)
    n = 30
    target = rng.normal(size=n)
    p1 = rng.normal(size=n)
    p2 = p1 * 2.0  # p1 ile TAM doğrusal bağımlı -> [p1, p2, intercept] ranksız

    trades = [
        _trade(100.0, 100.0 * (1 + 0.01 * target[i]), {"target": float(target[i]), "p1": float(p1[i]), "p2": float(p2[i])})
        for i in range(n)
    ]
    cluster = [frozenset({"target", "p1", "p2"})]
    result = compute_multivariable_residualized_ic(trades, cluster, min_sample_size=20)
    assert "target" not in result
