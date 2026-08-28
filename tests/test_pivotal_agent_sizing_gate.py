"""analytics/pivotal_agent_sizing_gate.py — kullanıcı bulgusu (Grok
raporu doğrulaması): technical ajanı pivot olduğunda kazanma oranı %25.4
(n=63), order_flow/macro pivot olunca TAM TERSİNE çok güçlü. Bu modül
HİÇBİR domaini hardcode etmiyor — ablation raporundan okuyor."""
from analytics.pivotal_agent_sizing_gate import (
    MIN_MULTIPLIER,
    identify_risky_pivotal_domains,
    pivotal_domain_size_multiplier,
)


def test_identifies_a_domain_below_baseline_with_enough_samples():
    by_domain = {"technical": {"caused_trade_win_rate": 0.254, "caused_trade_count": 63}}
    result = identify_risky_pivotal_domains(by_domain, baseline_win_rate=0.74)
    assert result == {"technical": 0.254}


def test_excludes_a_domain_above_baseline():
    by_domain = {"order_flow": {"caused_trade_win_rate": 0.98, "caused_trade_count": 50}}
    result = identify_risky_pivotal_domains(by_domain, baseline_win_rate=0.74)
    assert result == {}


def test_excludes_a_domain_with_too_few_samples():
    by_domain = {"technical": {"caused_trade_win_rate": 0.1, "caused_trade_count": 3}}
    result = identify_risky_pivotal_domains(by_domain, baseline_win_rate=0.74, min_samples=10)
    assert result == {}


def test_excludes_a_domain_that_never_caused_a_trade():
    by_domain = {"quant": {"caused_trade_win_rate": None, "caused_trade_count": 0}}
    result = identify_risky_pivotal_domains(by_domain, baseline_win_rate=0.74)
    assert result == {}


def test_multiplier_scales_proportionally_to_the_gap():
    """0.5/0.74 tabanı geçmiyor (floor 0.4'ün üstünde) — oran doğrudan
    uygulanmalı. Gerçek technical olayı (%25.4/%74 ≈ 0.343) ise floor'un
    ALTINDA kaldığı için ayrı testte (below_floor) doğrulanıyor."""
    result = pivotal_domain_size_multiplier(0.5, 0.74)
    assert abs(result - (0.5 / 0.74)) < 1e-6


def test_multiplier_never_drops_below_floor():
    assert pivotal_domain_size_multiplier(0.01, 0.74) == MIN_MULTIPLIER


def test_multiplier_never_exceeds_one():
    assert pivotal_domain_size_multiplier(0.98, 0.74) == 1.0


def test_multiplier_full_size_when_baseline_is_zero():
    assert pivotal_domain_size_multiplier(0.5, 0.0) == 1.0
