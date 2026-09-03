"""Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman içindeki
stabilitesini de ölçelim." risk/cross_symbol_correlation.py::describe_
correlation_pairs() ve services/market_state_gatherer.py::_attach_
correlation_stability()'nin gerçek bulguyu (BTC-ETH std=0.042 vs
NVDA-AMD std=0.181) doğru şekilde ürettiğini doğruluyor."""
import numpy as np

from risk.cross_symbol_correlation import describe_correlation_pairs
from services.market_state_gatherer import _attach_correlation_stability


def test_describe_correlation_pairs_filters_below_min_threshold():
    """BTC-AAPL benzeri, hiçbir zaman eşiğe yaklaşmayan gürültü çiftleri
    dışarıda bırakılmalı — stabilitesini takip etmenin değeri yok."""
    rng = np.random.default_rng(42)
    a = list(rng.normal(0, 0.02, 60))
    returns = {
        "A": a,
        "B": a,  # A ile özdeş -> corr=1.0
        "C": list(rng.normal(0, 0.02, 60)),  # bağımsız rastgele -> gerçekten düşük |corr|
    }
    assert abs(np.corrcoef(returns["A"], returns["C"])[0, 1]) < 0.5  # test verisinin kendi varsayımını doğrula

    pairs = describe_correlation_pairs(returns, min_abs_correlation=0.5)
    pair_names = {p["pair"] for p in pairs}
    assert "A|B" in pair_names
    assert not any("C" in name for name in pair_names)


def test_describe_correlation_pairs_returns_real_correlation_value():
    returns = {"A": [0.01, -0.02, 0.03, -0.01, 0.02], "B": [0.01, -0.02, 0.03, -0.01, 0.02]}
    pairs = describe_correlation_pairs(returns, min_abs_correlation=0.5)
    assert len(pairs) == 1
    assert abs(pairs[0]["correlation"] - 1.0) < 1e-6
    assert pairs[0]["pair"] == "A|B"


def test_attach_correlation_stability_matches_real_finding_shape():
    """Gerçek bulgu: BTC-ETH std=0.042 (istikrarlı) vs NVDA-AMD std=0.181
    (~4.3 kat daha gürültülü) — bu test o farkı sentetik ama gerçekçi
    bir geçmişle doğruluyor."""
    stable_pairs = [{"pair": "BTCUSDT|ETHUSDT", "correlation": 0.853}]
    stable_history = [
        {"result": {"pairs": [{"pair": "BTCUSDT|ETHUSDT", "correlation": c}]}}
        for c in [0.80, 0.81, 0.79, 0.82]
    ]
    _attach_correlation_stability(stable_pairs, stable_history)

    noisy_pairs = [{"pair": "NVDAUSDT|AMDUSDT", "correlation": 0.75}]
    noisy_history = [
        {"result": {"pairs": [{"pair": "NVDAUSDT|AMDUSDT", "correlation": c}]}}
        for c in [0.09, 0.86, 0.15, 0.60]
    ]
    _attach_correlation_stability(noisy_pairs, noisy_history)

    assert stable_pairs[0]["correlation_stability"]["std"] < noisy_pairs[0]["correlation_stability"]["std"]


def test_attach_correlation_stability_is_none_on_first_run():
    pairs = [{"pair": "BTCUSDT|ETHUSDT", "correlation": 0.85}]
    _attach_correlation_stability(pairs, past_snapshots=[])
    assert pairs[0]["correlation_stability"] is None


def test_attach_correlation_stability_only_matches_the_same_pair():
    pairs = [{"pair": "BTCUSDT|ETHUSDT", "correlation": 0.85}]
    past_snapshots = [{"result": {"pairs": [{"pair": "XAUTUSDT|XAGUSDT", "correlation": 0.90}]}}]
    _attach_correlation_stability(pairs, past_snapshots)
    assert pairs[0]["correlation_stability"] is None
