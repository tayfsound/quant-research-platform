"""Order Flow Agent testleri."""
from agents.order_flow_agent import OrderFlowAgent
from contracts.order_flow import OrderFlowContext


def test_bid_heavy_imbalance_generates_long():
    agent = OrderFlowAgent()
    ctx = OrderFlowContext(bid_ask_imbalance=0.5, aggressive_buy_ratio=0.7, spread_bps=2.0)
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0


def test_ask_heavy_imbalance_generates_short():
    agent = OrderFlowAgent()
    ctx = OrderFlowContext(bid_ask_imbalance=-0.5, aggressive_buy_ratio=0.3, spread_bps=2.0)
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"


def test_wide_spread_dampens_confidence_and_warns():
    agent = OrderFlowAgent()
    tight = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, spread_bps=2.0))
    wide = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, spread_bps=25.0))
    assert wide.confidence < tight.confidence
    assert any("wide spread" in c.lower() for c in wide.caveats)


def test_balanced_book_waits():
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext())
    assert opinion.direction == "WAIT"


def test_high_positive_funding_rate_pushes_short_as_contrarian_signal():
    """Faz 247-249: kalabalık long pozisyonlanma (yüksek pozitif funding)
    bir onay değil, kontrarian bir uyarı — market_data/sentiment/
    positioning_provider.py'nin AYNI felsefesi."""
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext(funding_rate=0.001))
    assert opinion.direction == "SHORT"
    assert any("funding rate" in e.lower() for e in opinion.evidence)


def test_high_negative_funding_rate_pushes_long_as_contrarian_signal():
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext(funding_rate=-0.001))
    assert opinion.direction == "LONG"


def test_normal_funding_rate_has_no_effect():
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext(funding_rate=0.0001))
    assert opinion.direction == "WAIT"


def test_missing_funding_rate_has_no_effect():
    """funding_rate=None (vadeli kontratı olmayan sembol) — fail-closed,
    hiçbir skor değişikliği olmamalı."""
    agent = OrderFlowAgent()
    with_none = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, funding_rate=None))
    without_field = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5))
    assert with_none.confidence == without_field.confidence


def test_rising_open_interest_amplifies_an_existing_directional_score():
    agent = OrderFlowAgent()
    without_oi = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, open_interest_trend="unknown"))
    with_rising_oi = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, open_interest_trend="rising"))
    assert with_rising_oi.confidence > without_oi.confidence
    assert any("open interest" in e.lower() for e in with_rising_oi.evidence)


def test_falling_open_interest_dampens_confidence_and_warns():
    agent = OrderFlowAgent()
    stable = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, open_interest_trend="stable"))
    falling = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, open_interest_trend="falling"))
    assert falling.confidence < stable.confidence
    assert any("open interest falling" in c.lower() for c in falling.caveats)


def test_rising_open_interest_with_no_direction_does_not_create_one():
    """score=0 iken (WAIT) OI rising bile tek başına bir yön yaratmamalı —
    sadece MEVCUT bir yönü teyit ediyor, kendi başına yön belirlemiyor."""
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext(open_interest_trend="rising"))
    assert opinion.direction == "WAIT"


def test_feature_contributions_sum_to_the_implied_raw_score():
    """Faz 268-sonrası: Feature Importance — bkz. agents/quant_agent.py ve
    agents/technical_agent.py'deki aynı desen. feature_contributions her
    zaman GERÇEK score'a (confidence = min(|score|/3.5, 0.8)) eşit
    toplanmalı."""
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, funding_rate=-0.001))
    implied_score = sum(opinion.feature_contributions.values())
    assert abs(abs(implied_score) - opinion.confidence * 3.5) < 1e-6


def test_feature_contributions_are_empty_when_no_signal_fires():
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext())  # tüm varsayılanlar -> hiçbir dal tetiklenmez
    assert opinion.feature_contributions == {}


def test_feature_contributions_names_the_active_signals():
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext(
        bid_ask_imbalance=0.5, aggressive_buy_ratio=0.7, spread_bps=2.0,
        funding_rate=-0.001, open_interest_trend="rising",
    ))
    assert opinion.feature_contributions["bid_ask_imbalance"] > 0
    assert opinion.feature_contributions["aggressive_buy_ratio"] > 0
    assert opinion.feature_contributions["funding_rate"] > 0
    assert opinion.feature_contributions["open_interest_confirm"] > 0


def test_feature_contributions_reflect_the_wide_spread_discount():
    """Geniş spread indirimi (scale_all(0.5)) O ANA KADAR birikmiş
    katkılara uygulanmalı — sonradan eklenen funding_rate/open_interest
    katkıları bundan ETKİLENMEMELİ (orijinal `score *= 0.5`'in tam
    sıralamasıyla birebir aynı)."""
    agent = OrderFlowAgent()
    tight = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, spread_bps=2.0))
    wide = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, spread_bps=25.0))
    assert abs(wide.feature_contributions["bid_ask_imbalance"] - tight.feature_contributions["bid_ask_imbalance"] * 0.5) < 1e-6
