"""Feature Relationship (redundancy matrix + koşullu IC) testleri — Faz 368."""
from analytics.feature_ic import compute_feature_ic
from analytics.feature_relationship import compute_conditional_ic, compute_feature_redundancy


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
