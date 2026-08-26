"""analytics/agent_ablation.py — Faz 296. Kullanıcı isteği (2026-08-19):
mevcut auto-bench SADECE davranışsal/geriye dönük doğruluk ölçüyordu,
"bu ajanın oyu olmasaydı gerçekleşen kararlar farklı olur muydu" sorusuna
hiç cevap vermiyordu. Bu modül gerçek services/belief_engine.py::
synthesize'ı (pure, deterministik) hedef ajan sıfırlanmış halde yeniden
çalıştırıp GERÇEK bir leave-one-out rekonstrüksiyonu yapar."""
from analytics.agent_ablation import (
    compute_leave_one_out_counterfactual_direction,
    compute_leave_one_out_impact,
    reconstruct_opinions,
    summarize_ablation_by_domain,
)
from contracts.agent import AgentDomain, AgentOpinion


def _opinion_dict(domain: AgentDomain, direction: str, confidence: float) -> dict:
    o = AgentOpinion(domain=domain, direction=direction, confidence=confidence)
    o.recalculate()
    return o.model_dump(mode="json")


def test_reconstruct_opinions_skips_non_opinion_envelope_dicts():
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.8),
        {"type": "market_snapshot", "data": {}},
        {"type": "risk_evaluation", "data": {}},
    ]
    opinions = reconstruct_opinions(contributions)
    assert len(opinions) == 1
    assert opinions[0].domain == AgentDomain.TECHNICAL


def test_compute_leave_one_out_impact_returns_none_when_domain_never_voted():
    contributions = [_opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.8)]
    result = compute_leave_one_out_impact(contributions, "quant", "LONG")
    assert result is None


def test_compute_leave_one_out_impact_detects_caused_trade():
    """Tek bir ajan (technical) TEK yönlü sesken (diğerleri WAIT), onu
    çıkarmak hiçbir yönlü ağırlık bırakmamalı -> synthesize WAIT'e
    düşmeli -> "caused_trade" (bu ajan olmasaydı işlem hiç açılmazdı)."""
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.9),
        _opinion_dict(AgentDomain.TIME, "WAIT", 0.5),
        _opinion_dict(AgentDomain.EPISTEMOLOGY, "WAIT", 0.5),
    ]
    result = compute_leave_one_out_impact(contributions, "technical", "LONG")
    assert result == "caused_trade"


def test_compute_leave_one_out_impact_detects_not_pivotal_when_others_agree():
    """İki güçlü, AYNI yönde oy veren ajan varken birini çıkarmak sonucu
    değiştirmemeli -> "not_pivotal"."""
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.9),
        _opinion_dict(AgentDomain.MACRO, "LONG", 0.9),
    ]
    result = compute_leave_one_out_impact(contributions, "technical", "LONG")
    assert result == "not_pivotal"


def test_compute_leave_one_out_impact_detects_flipped_direction():
    """Baskın ajan (technical, yüksek confidence) LONG derken zayıf bir
    ajan (macro, düşük confidence) SHORT diyorsa; technical çıkarılınca
    kalan tek yönlü ses (macro/SHORT) kazanmalı -> gerçekleşenden
    (LONG) FARKLI bir yön -> "flipped_direction"."""
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.95),
        _opinion_dict(AgentDomain.MACRO, "SHORT", 0.6),
    ]
    result = compute_leave_one_out_impact(contributions, "technical", "LONG")
    assert result == "flipped_direction"


def test_compute_leave_one_out_counterfactual_direction_returns_the_new_direction_on_flip():
    """compute_leave_one_out_impact ile AYNI senaryo ("flipped_direction")
    — ama bu sefer gerçek karşı-olgusal YÖNÜ (SHORT) bekliyoruz, sadece
    kategori etiketini değil."""
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.95),
        _opinion_dict(AgentDomain.MACRO, "SHORT", 0.6),
    ]
    direction = compute_leave_one_out_counterfactual_direction(contributions, "technical", "LONG")
    assert direction == "SHORT"


def test_compute_leave_one_out_counterfactual_direction_none_when_not_pivotal():
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.9),
        _opinion_dict(AgentDomain.MACRO, "LONG", 0.9),
    ]
    direction = compute_leave_one_out_counterfactual_direction(contributions, "technical", "LONG")
    assert direction is None


def test_compute_leave_one_out_counterfactual_direction_none_when_caused_trade():
    """WAIT'e düşen bir karşı-olgusalda replay edilecek yönlü bir işlem
    yok -- None dönmeli, "WAIT" icat edilmemeli."""
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.9),
        _opinion_dict(AgentDomain.TIME, "WAIT", 0.5),
    ]
    direction = compute_leave_one_out_counterfactual_direction(contributions, "technical", "LONG")
    assert direction is None


def test_summarize_ablation_by_domain_aggregates_correctly():
    records = [
        {"domain": "technical", "impact": "caused_trade", "pnl": 10.0},
        {"domain": "technical", "impact": "caused_trade", "pnl": -3.0},
        {"domain": "technical", "impact": "flipped_direction", "pnl": 5.0},
        {"domain": "technical", "impact": "not_pivotal", "pnl": 1.0},
    ]
    summary = summarize_ablation_by_domain(records)
    stats = summary["technical"]
    assert stats["votes_cast"] == 4
    assert stats["caused_trade_count"] == 2
    assert stats["caused_trade_total_pnl"] == 7.0
    assert stats["flipped_direction_count"] == 1
    assert stats["not_pivotal_count"] == 1


def test_summarize_ablation_by_domain_win_rate_is_none_below_min_samples():
    """Faz 298 — kullanıcı isteği: minimum evidence gate. caused_trade_
    total_pnl (kesin bir tutar) her zaman raporlanır ama caused_trade_
    win_rate (bir ORAN) örneklem <10 iken yanıltıcı kesinlik verir —
    fail-closed None."""
    records = [{"domain": "pattern", "impact": "caused_trade", "pnl": 1.0} for _ in range(8)]
    summary = summarize_ablation_by_domain(records)
    stats = summary["pattern"]
    assert stats["caused_trade_count"] == 8
    assert stats["caused_trade_total_pnl"] == 8.0
    assert stats["caused_trade_win_rate"] is None
    assert stats["caused_trade_win_rate_ci"] is None


def test_summarize_ablation_by_domain_win_rate_reported_at_min_samples():
    records = (
        [{"domain": "macro", "impact": "caused_trade", "pnl": 1.0} for _ in range(7)]
        + [{"domain": "macro", "impact": "caused_trade", "pnl": -1.0} for _ in range(3)]
    )
    summary = summarize_ablation_by_domain(records)
    stats = summary["macro"]
    assert stats["caused_trade_count"] == 10
    assert stats["caused_trade_win_rate"] == 0.7
    # Faz 304 — n=10'de bile %70 nokta tahmini geniş bir bant içinde
    # belirsiz; Wilson aralığı bunu açık ediyor, gerçek oranı kapsamalı.
    ci = stats["caused_trade_win_rate_ci"]
    assert ci is not None
    assert ci["low"] <= 0.7 <= ci["high"]


def test_summarize_ablation_by_domain_win_rate_is_none_with_no_caused_trades():
    records = [{"domain": "macro", "impact": "not_pivotal", "pnl": 1.0}]
    summary = summarize_ablation_by_domain(records)
    assert summary["macro"]["caused_trade_win_rate"] is None
