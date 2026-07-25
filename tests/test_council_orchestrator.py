"""Council Orchestrator testleri — AgentDomain enum anahtarları."""
from agents.registry import AgentRegistry
from services.council_orchestrator import CouncilOrchestrator
from contracts.agent import AgentDomain
from contracts.macro import MacroContext
from contracts.sentiment import SentimentContext
from contracts.onchain import OnChainContext
from contracts.technical import TechnicalContext

def test_full_council_deliberate():
    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)

    belief, opinions = orchestrator.deliberate({
        AgentDomain.MACRO: MacroContext(inflation_trend="rising", liquidity_condition="tight", central_bank_bias="hawkish"),
        AgentDomain.SENTIMENT: SentimentContext(fear_greed_index=75.0, social_media_sentiment=0.4, positioning="long_bias"),
        AgentDomain.ONCHAIN: OnChainContext(exchange_outflow_24h=300_000_000, whale_accumulation=True),
        AgentDomain.TECHNICAL: TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs", volume_confirmation=True),
    })

    assert belief.direction in ("LONG", "SHORT", "WAIT")
    assert belief.total_opinions > 0
    assert len(opinions) == belief.total_opinions

def test_partial_council():
    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)

    belief, opinions = orchestrator.deliberate({
        AgentDomain.MACRO: MacroContext(inflation_trend="falling", central_bank_bias="dovish"),
        AgentDomain.TECHNICAL: TechnicalContext(trend="bullish", market_structure="higher_highs"),
    })

    assert belief.direction in ("LONG", "SHORT", "WAIT")
    assert belief.total_opinions == 2
    assert len(opinions) == 2

def test_empty_council():
    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)

    belief, opinions = orchestrator.deliberate({})
    assert belief.direction == "WAIT"
    assert belief.total_opinions == 0
    assert len(opinions) == 0
