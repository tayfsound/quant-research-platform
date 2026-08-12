"""Online Feature Selection (Information Coefficient) testleri."""
from analytics.feature_ic import compute_feature_ic


def _trade(entry: float, exit: float, feature_contributions: dict[str, float], domain: str = "technical") -> dict:
    return {
        "entry_price": entry,
        "exit_price": exit,
        "agent_contributions": [
            {"agent_id": "x", "domain": domain, "feature_contributions": feature_contributions},
        ],
    }


def test_a_feature_that_cleanly_predicts_the_direction_gets_a_strongly_positive_ic():
    """Katkı pozitifken fiyat GERÇEKTEN yükseliyor, negatifken GERÇEKTEN
    düşüyor — mükemmel bir öngörücü, IC +1'e çok yakın olmalı."""
    trades = []
    for i in range(25):
        trades.append(_trade(100.0, 101.0 + i * 0.1, {"good_signal": 1.0 + i * 0.01}))
        trades.append(_trade(100.0, 99.0 - i * 0.1, {"good_signal": -1.0 - i * 0.01}))

    result = compute_feature_ic(trades, min_sample_size=20)
    assert "good_signal" in result
    assert result["good_signal"]["ic"] > 0.9
    assert result["good_signal"]["sample_size"] == 50
    assert result["good_signal"]["agent_domain"] == "technical"


def test_a_feature_that_predicts_the_opposite_direction_gets_a_negative_ic():
    """Faz 258'in volume_confirmation bulgusuyla aynı desen: sinyal pozitif
    ateşlendiğinde fiyat aslında DÜŞÜYOR — negatif IC, "bu sinyal ters
    yönde" tespitini kanıtlıyor."""
    trades = []
    for i in range(25):
        trades.append(_trade(100.0, 99.0 - i * 0.1, {"backwards_signal": 1.0 + i * 0.01}))
        trades.append(_trade(100.0, 101.0 + i * 0.1, {"backwards_signal": -1.0 - i * 0.01}))

    result = compute_feature_ic(trades, min_sample_size=20)
    assert result["backwards_signal"]["ic"] < -0.9


def test_insufficient_sample_size_is_excluded_fail_closed():
    trades = [_trade(100.0, 101.0, {"rare_signal": 1.0}) for _ in range(5)]
    result = compute_feature_ic(trades, min_sample_size=20)
    assert "rare_signal" not in result


def test_a_feature_with_zero_variance_is_excluded():
    """Bir feature HER zaman aynı katkıyı üretmişse (gerçek çeşitlilik
    yok) Pearson tanımsız kalır — icat edilmiş bir IC asla dönmemeli."""
    trades = [_trade(100.0, 100.0 + i, {"constant_signal": 1.0}) for i in range(30)]
    result = compute_feature_ic(trades, min_sample_size=20)
    assert "constant_signal" not in result


def test_non_opinion_envelopes_are_not_mistaken_for_feature_contributions():
    """agent_contributions listesi risk_evaluation/market_snapshot gibi
    feature_contributions'sız zarflar da içerebiliyor (bkz. decision_
    persistor.py) — bunlar sessizce atlanmalı, hata fırlatmamalı."""
    trades = [
        {
            "entry_price": 100.0, "exit_price": 100.0 + i * 0.1,
            "agent_contributions": [
                {"type": "risk_evaluation", "data": {"verdict": "approved"}},
                {"type": "market_snapshot", "data": {"symbol": "BTCUSDT"}},
                {"agent_id": "x", "domain": "quant", "feature_contributions": {"zscore_mean_reversion": 1.0 + i * 0.01}},
            ],
        }
        for i in range(25)
    ]
    result = compute_feature_ic(trades, min_sample_size=20)
    assert "zscore_mean_reversion" in result
    assert result["zscore_mean_reversion"]["sample_size"] == 25


def test_trades_missing_price_data_are_skipped_without_crashing():
    trades = [
        {"entry_price": None, "exit_price": 100.0, "agent_contributions": []},
        {"entry_price": 100.0, "exit_price": None, "agent_contributions": []},
        {"entry_price": 0.0, "exit_price": 100.0, "agent_contributions": []},
    ]
    result = compute_feature_ic(trades, min_sample_size=1)
    assert result == {}
