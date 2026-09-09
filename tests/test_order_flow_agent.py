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


def test_bullish_low_regime_shadows_the_entire_domain():
    """Faz 412 — kullanıcı isteği: order_flow'un bullish_low rejiminde
    net zararlı olduğu bulundu (ablation: -193$/işlem beklenti; yönlü
    IC: p=0,014) — TEK bir feature değil, TÜM domain (aggressive_buy_
    ratio + open_interest_confirm) bu rejimde skora sıfır etki yapmalı,
    ama feature_ic'in izleyebilmesi için feature_contributions'ta
    gölge olarak kalmalı (pattern_agent.py::_regime_gated ile AYNI
    disiplin)."""
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext(
        aggressive_buy_ratio=0.7, open_interest_trend="rising", market_regime="bullish_low",
    ))
    assert opinion.direction == "WAIT"
    assert opinion.confidence == 0.0
    assert opinion.feature_contributions["aggressive_buy_ratio"] == 1.0
    assert opinion.feature_contributions["open_interest_confirm"] == 0.3


def test_other_regimes_keep_order_flow_active():
    agent = OrderFlowAgent()
    for regime in ("bullish_normal", "bearish_low", "unknown"):
        opinion = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, market_regime=regime))
        assert opinion.direction == "LONG"


def test_wide_spread_dampens_confidence_and_warns():
    agent = OrderFlowAgent()
    tight = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, spread_bps=2.0))
    wide = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, spread_bps=25.0))
    assert wide.confidence < tight.confidence
    assert any("geniş spread" in c.lower() for c in wide.caveats)


def test_balanced_book_waits():
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext())
    assert opinion.direction == "WAIT"


def test_funding_rate_no_longer_contributes_to_the_score():
    """Faz 411 (2026-09-04) — kullanıcı isteği: rejime göre ayrıştırılmış
    Feature IC denetiminde funding_rate HİÇBİR rejim segmentinde anlamlı
    çıkmadı (overall p=0.97, n=211 — zaten çok zayıf) — Faz 247-249'un
    kontrarian sinyal varsayımı gerçek veriyle doğrulanamadı, tamamen
    kaldırıldı."""
    agent = OrderFlowAgent()
    with_positive = agent.analyze(OrderFlowContext(funding_rate=0.001))
    with_negative = agent.analyze(OrderFlowContext(funding_rate=-0.001))
    assert with_positive.direction == with_negative.direction == "WAIT"
    assert "funding_rate" not in with_positive.feature_contributions
    assert "funding_rate" not in with_negative.feature_contributions


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
    without_oi = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, open_interest_trend="unknown"))
    with_rising_oi = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, open_interest_trend="rising"))
    assert with_rising_oi.confidence > without_oi.confidence
    assert any("open interest" in e.lower() for e in with_rising_oi.evidence)


def test_falling_open_interest_dampens_confidence_and_warns():
    agent = OrderFlowAgent()
    stable = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, open_interest_trend="stable"))
    falling = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, open_interest_trend="falling"))
    assert falling.confidence < stable.confidence
    assert any("open interest) azalıyor" in c.lower() for c in falling.caveats)


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
    opinion = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, open_interest_trend="rising"))
    implied_score = sum(opinion.feature_contributions.values())
    assert abs(abs(implied_score) - opinion.confidence * 3.5) < 5e-3


def test_feature_contributions_are_empty_when_no_signal_fires():
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext())  # tüm varsayılanlar -> hiçbir dal tetiklenmez
    assert opinion.feature_contributions == {}


def test_feature_contributions_names_the_active_signals():
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext(
        aggressive_buy_ratio=0.7, spread_bps=2.0, open_interest_trend="rising",
    ))
    assert opinion.feature_contributions["aggressive_buy_ratio"] > 0
    assert opinion.feature_contributions["open_interest_confirm"] > 0


def test_feature_contributions_reflect_the_wide_spread_discount():
    """Geniş spread indirimi (scale_all(0.5)) O ANA KADAR birikmiş
    katkılara uygulanmalı — sonradan eklenen open_interest katkıları
    bundan ETKİLENMEMELİ (orijinal `score *= 0.5`'in tam sıralamasıyla
    birebir aynı)."""
    agent = OrderFlowAgent()
    tight = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, spread_bps=2.0))
    wide = agent.analyze(OrderFlowContext(aggressive_buy_ratio=0.7, spread_bps=25.0))
    assert abs(wide.feature_contributions["aggressive_buy_ratio"] - tight.feature_contributions["aggressive_buy_ratio"] * 0.5) < 1e-6


# --- Faz 464: kanitlanmis order_flow_relationship sinyalinin baglanmasi ---

def test_bullish_short_covering_votes_short_because_that_is_what_was_measured():
    """Faz 462/463'te GERÇEK veriyle ölçüldü (n=7.729): "bullish_short_
    covering" kategorisinde 1 saat sonra yükseliş olasılığı %36,9 -- tüm
    kategorilerin EN DÜŞÜĞÜ. Yani isminin aksine DÜŞÜŞ habercisi.

    Bu, Faz 460/463'ün genel ortalamaya-dönüş örüntüsüyle birebir aynı ve
    işaret ÖLÇÜMDEN geliyor, isimden değil."""
    agent = OrderFlowAgent()
    ctx = OrderFlowContext(
        aggressive_buy_ratio=0.5, spread_bps=2.0,
        order_flow_relationship_category="bullish_short_covering",
    )
    opinion = agent.analyze(ctx)

    assert opinion.feature_contributions["order_flow_relationship"] < 0


def test_bearish_long_capitulation_votes_long():
    """Ölçülen P(UP)=0,533 -- tüm kategorilerin EN YÜKSEĞİ."""
    agent = OrderFlowAgent()
    ctx = OrderFlowContext(
        aggressive_buy_ratio=0.5, spread_bps=2.0,
        order_flow_relationship_category="bearish_long_capitulation",
    )
    opinion = agent.analyze(ctx)

    assert opinion.feature_contributions["order_flow_relationship"] > 0


def test_unclear_category_contributes_nothing():
    """Ölçülen P(UP)=0,474, yani taban değerin kendisi -- bilgi taşımıyor.
    Uydurma bir yön verilmemeli."""
    agent = OrderFlowAgent()
    ctx = OrderFlowContext(
        aggressive_buy_ratio=0.5, spread_bps=2.0,
        order_flow_relationship_category="unclear",
    )
    opinion = agent.analyze(ctx)

    assert "order_flow_relationship" not in opinion.feature_contributions
    assert any("belirsiz" in c for c in opinion.caveats)


def test_missing_category_is_fail_closed():
    """Veri yoksa (None) hiçbir katkı üretilmemeli -- Faz 436'nın
    fail-closed ilkesi."""
    agent = OrderFlowAgent()
    ctx = OrderFlowContext(aggressive_buy_ratio=0.5, spread_bps=2.0)
    opinion = agent.analyze(ctx)

    assert "order_flow_relationship" not in opinion.feature_contributions


def test_relationship_is_shadowed_in_the_harmful_regime():
    """Faz 412'de order_flow domain'inin bullish_low'da zararlı olduğu
    bulunmuştu; yeni sinyal o kararı DELMEMELİ -- aynı rejimde o da
    gölgede kalmalı (skora sıfır etki, feature_ic izlemeye devam)."""
    agent = OrderFlowAgent()
    ctx = OrderFlowContext(
        aggressive_buy_ratio=0.5, spread_bps=2.0, market_regime="bullish_low",
        order_flow_relationship_category="bullish_short_covering",
    )
    opinion = agent.analyze(ctx)

    # feature_contributions'ta IZLENIYOR ama skora girmiyor.
    assert "order_flow_relationship" in opinion.feature_contributions
    assert opinion.direction == "WAIT"


def test_context_adapter_actually_passes_the_category_through():
    """REGRESYON KORUMASI. Faz 453'te TAM BU KUSUR bulunmuştu:
    `context_adapter.to_pattern()` hesaplanmış üç özelliği ajana hiç
    geçirmediği için `volume_profile_confirm` sinyali aylarca HİÇ
    tetiklenmemişti (n=0, sessizce ölü kod).

    Yeni bir özelliği bağlarken en kolay atlanan halka bu -- sözleşmeye
    alan eklemek ve ajanda skorlamak TEK BAŞINA yetmiyor, adapter'ın da
    taşıması gerekiyor."""
    from contracts.context import CognitiveCycleContext
    from services.context_adapter import ContextAdapter

    ctx = CognitiveCycleContext()
    ctx.market.symbol = ""  # gercek DB okumasini atla
    ctx.market.features = {"order_flow_relationship_category": "bearish_long_capitulation"}

    of_ctx = ContextAdapter().to_order_flow(ctx)
    assert of_ctx.order_flow_relationship_category == "bearish_long_capitulation"

    opinion = OrderFlowAgent().analyze(of_ctx)
    assert opinion.feature_contributions["order_flow_relationship"] > 0
