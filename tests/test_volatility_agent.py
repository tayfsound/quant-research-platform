"""agents/volatility_agent.py — Faz 336. Deribit DVOL (kriptonun VIX'i) —
direction'dan bağımsız, ayrı bir risk/rejim ekseni."""
from agents.volatility_agent import VolatilityAgent
from contracts.agent import AgentDomain
from contracts.volatility import VolatilityContext


def test_spiking_dvol_produces_short():
    opinion = VolatilityAgent().analyze(VolatilityContext(dvol_level=80.0, dvol_trend="spiking"))
    assert opinion.direction == "SHORT"
    assert opinion.domain == AgentDomain.VOLATILITY
    assert opinion.confidence == 0.5


def test_falling_dvol_produces_long():
    opinion = VolatilityAgent().analyze(VolatilityContext(dvol_level=35.0, dvol_trend="falling"))
    assert opinion.direction == "LONG"


def test_stable_dvol_produces_wait():
    opinion = VolatilityAgent().analyze(VolatilityContext(dvol_level=45.0, dvol_trend="stable"))
    assert opinion.direction == "WAIT"
    assert "dvol_trend" not in opinion.feature_contributions


def test_no_data_is_fail_closed():
    opinion = VolatilityAgent().analyze(VolatilityContext(dvol_level=None, dvol_trend=""))
    assert opinion.direction == "WAIT"
    assert opinion.confidence == 0.0
    assert opinion.feature_contributions == {}


def test_dvol_level_always_logged_as_evidence_when_available():
    opinion = VolatilityAgent().analyze(VolatilityContext(dvol_level=42.5, dvol_trend="stable"))
    assert any("42.5" in e for e in opinion.evidence)


def test_volatility_agent_is_registered_as_a_voting_domain():
    from agents.registry import AgentRegistry
    from contracts.agent import VOTING_AGENT_DOMAINS

    assert AgentDomain.VOLATILITY in VOTING_AGENT_DOMAINS
    registry = AgentRegistry.create_default()
    assert registry.get(AgentDomain.VOLATILITY) is not None


def test_context_adapter_to_volatility_is_fail_closed_on_missing_data(monkeypatch):
    from contracts.context import CognitiveCycleContext
    from services.context_adapter import ContextAdapter

    monkeypatch.setattr("market_data.volatility.deribit_provider.fetch_dvol_level", lambda currency="BTC": None)
    monkeypatch.setattr("market_data.volatility.deribit_provider.fetch_dvol_trend", lambda currency="BTC": None)

    ctx = CognitiveCycleContext()
    result = ContextAdapter().to_volatility(ctx)
    assert result.dvol_level is None
    assert result.dvol_trend == ""
