"""Faz 368: PivotalAgentSizingStage — matematik ayrı test ediliyor
(test_pivotal_agent_sizing_gate.py); burada stage'in GERÇEKTEN pivot olan
(agent_ablation.py::synthesize_with_domain_excluded ile canlı test
edilen) domain'i bulup final_size'ı çarptığını doğruluyoruz."""
from unittest.mock import patch

from contracts.agent import AgentDomain, AgentOpinion
from contracts.context import CognitiveCycleContext
from engines.cognitive_pipeline import PivotalAgentSizingStage


def _opinion(domain: AgentDomain, direction: str, confidence: float) -> AgentOpinion:
    o = AgentOpinion(domain=domain, direction=direction, confidence=confidence)
    o.recalculate()
    return o


def _ctx(final_size: float, direction: str = "LONG") -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = final_size
    ctx.decision.proposed_direction = direction
    return ctx


def _mocks(by_domain: dict, baseline: str = "0.74"):
    ablation_patch = patch(
        "database.repositories.agent_ablation_report_repository.AgentAblationReportRepository.get_latest",
        return_value={"result": {"by_domain": by_domain}},
    )
    settings_patch = patch(
        "database.repositories.app_settings_repository.AppSettingsRepository.get",
        return_value=baseline,
    )
    return ablation_patch, settings_patch


def test_does_nothing_when_final_size_is_zero():
    ablation_p, settings_p = _mocks({"technical": {"caused_trade_win_rate": 0.254, "caused_trade_count": 63}})
    opinions = [_opinion(AgentDomain.TECHNICAL, "LONG", 0.9), _opinion(AgentDomain.TIME, "WAIT", 0.5)]
    with ablation_p, settings_p:
        ctx = _ctx(final_size=0.0)
        result = PivotalAgentSizingStage().execute(ctx, opinions)
    assert result.decision.final_size == 0.0


def test_does_nothing_when_no_opinions_passed():
    ablation_p, settings_p = _mocks({"technical": {"caused_trade_win_rate": 0.254, "caused_trade_count": 63}})
    with ablation_p, settings_p:
        ctx = _ctx(final_size=2.0)
        result = PivotalAgentSizingStage().execute(ctx, None)
    assert result.decision.final_size == 2.0


def test_does_nothing_when_no_risky_domain_in_report():
    ablation_p, settings_p = _mocks({"order_flow": {"caused_trade_win_rate": 0.98, "caused_trade_count": 50}})
    opinions = [_opinion(AgentDomain.TECHNICAL, "LONG", 0.9), _opinion(AgentDomain.TIME, "WAIT", 0.5)]
    with ablation_p, settings_p:
        ctx = _ctx(final_size=2.0)
        result = PivotalAgentSizingStage().execute(ctx, opinions)
    assert result.decision.final_size == 2.0


def test_shrinks_when_risky_domain_is_genuinely_pivotal():
    """technical TEK yönlü sesken (diğerleri WAIT) onu çıkarmak hiçbir
    yönlü ağırlık bırakmaz -> gerçekten pivot -> boyut küçülmeli."""
    ablation_p, settings_p = _mocks({"technical": {"caused_trade_win_rate": 0.254, "caused_trade_count": 63}})
    opinions = [
        _opinion(AgentDomain.TECHNICAL, "LONG", 0.9),
        _opinion(AgentDomain.TIME, "WAIT", 0.5),
        _opinion(AgentDomain.EPISTEMOLOGY, "WAIT", 0.5),
    ]
    with ablation_p, settings_p:
        ctx = _ctx(final_size=2.0)
        result = PivotalAgentSizingStage().execute(ctx, opinions)
    assert result.decision.final_size < 2.0
    entry = next(i for i in result.cognition.relevant_knowledge if i["type"] == "pivotal_agent_sizing")
    assert entry["data"]["pivotal_domain"] == "technical"


def test_does_not_shrink_when_risky_domain_is_not_actually_pivotal():
    """technical LONG diyor ama macro/order_flow de GÜÇLÜ şekilde LONG
    diyor -> technical'ı çıkarmak yönü DEĞİŞTİRMEZ -> pivot değil."""
    ablation_p, settings_p = _mocks({"technical": {"caused_trade_win_rate": 0.254, "caused_trade_count": 63}})
    opinions = [
        _opinion(AgentDomain.TECHNICAL, "LONG", 0.9),
        _opinion(AgentDomain.MACRO, "LONG", 0.9),
        _opinion(AgentDomain.ORDER_FLOW, "LONG", 0.9),
    ]
    with ablation_p, settings_p:
        ctx = _ctx(final_size=2.0)
        result = PivotalAgentSizingStage().execute(ctx, opinions)
    assert result.decision.final_size == 2.0


def test_never_increases_final_size():
    ablation_p, settings_p = _mocks({"technical": {"caused_trade_win_rate": 0.01, "caused_trade_count": 63}})
    opinions = [
        _opinion(AgentDomain.TECHNICAL, "LONG", 0.9),
        _opinion(AgentDomain.TIME, "WAIT", 0.5),
    ]
    with ablation_p, settings_p:
        ctx = _ctx(final_size=2.0)
        result = PivotalAgentSizingStage().execute(ctx, opinions)
    assert result.decision.final_size <= 2.0
