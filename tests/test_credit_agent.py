"""agents/credit_agent.py — Faz 333. "Credit leads equity": tahvil
piyasası kredi koşulları risk varlıklarından ÖNCE sinyal verir."""
from agents.credit_agent import CreditAgent
from contracts.agent import AgentDomain
from contracts.credit import CreditContext


def test_inverted_curve_and_widening_spread_produce_short():
    opinion = CreditAgent().analyze(
        CreditContext(yield_curve_signal="inverted", credit_spread_trend="widening")
    )
    assert opinion.direction == "SHORT"
    assert opinion.domain == AgentDomain.CREDIT
    assert opinion.confidence == 1.0


def test_normal_curve_and_narrowing_spread_produce_long():
    opinion = CreditAgent().analyze(
        CreditContext(yield_curve_signal="normal", credit_spread_trend="narrowing")
    )
    assert opinion.direction == "LONG"


def test_no_signal_produces_wait():
    opinion = CreditAgent().analyze(CreditContext(yield_curve_signal="", credit_spread_trend=""))
    assert opinion.direction == "WAIT"
    assert opinion.confidence == 0.0


def test_normal_curve_alone_is_neutral_not_rewarded():
    """Yield curve inversiyonu asimetrik puanlanıyor — "normal" durumun
    kendisi bir alpha kaynağı sayılmıyor, sadece "uyarı yok" demek."""
    opinion = CreditAgent().analyze(
        CreditContext(yield_curve_signal="normal", credit_spread_trend="stable")
    )
    assert opinion.direction == "WAIT"


def test_credit_agent_is_registered_as_a_voting_domain():
    from agents.registry import AgentRegistry
    from contracts.agent import VOTING_AGENT_DOMAINS

    assert AgentDomain.CREDIT in VOTING_AGENT_DOMAINS
    registry = AgentRegistry.create_default()
    assert registry.get(AgentDomain.CREDIT) is not None


def test_context_adapter_to_credit_is_fail_closed_on_missing_data(monkeypatch):
    from contracts.context import CognitiveCycleContext
    from services.context_adapter import ContextAdapter

    monkeypatch.setattr("market_data.macro.fred_provider.fetch_yield_curve_signal", lambda: None)
    monkeypatch.setattr("market_data.macro.fred_provider.fetch_credit_spread_trend", lambda: None)

    ctx = CognitiveCycleContext()
    result = ContextAdapter().to_credit(ctx)
    assert result.yield_curve_signal == ""
    assert result.credit_spread_trend == ""
