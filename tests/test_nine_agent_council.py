"""Agent kalitesi turu — gate kanıtı: AgentDomain enum'daki 16 domain'in
hepsi mimaride gerçek bir role sahip (4 orijinal oy-ajanı + Pattern/Quant/
Order Flow/Time/Epistemology bu turda eklendi + Risk/Alter Ego eleştirmen +
Source Reliability annotator + Portfolio/Executive ayrı mekanizmalar).

Bu test, 9 oy-veren ajanın hepsinin AgentRegistry.create_default() ile
gerçekten register edildiğini ve CouncilOrchestrator.deliberate() üzerinden
gerçekten çalışıp tek bir belief'e sentezlendiğini kanıtlıyor."""
from agents.registry import AgentRegistry
from contracts.agent import AgentDomain
from contracts.macro import MacroContext
from contracts.onchain import OnChainContext
from contracts.order_flow import OrderFlowContext
from contracts.pattern import PatternContext
from contracts.quant import QuantContext
from contracts.sentiment import SentimentContext
from contracts.technical import TechnicalContext
from contracts.time_context import TimeContext
from contracts.epistemology import EpistemologyContext
from services.council_orchestrator import CouncilOrchestrator


def test_all_nine_voting_agents_are_registered_by_default():
    registry = AgentRegistry.create_default()
    domains = set(registry.list_domains())
    expected = {
        AgentDomain.MACRO, AgentDomain.SENTIMENT, AgentDomain.ONCHAIN, AgentDomain.TECHNICAL,
        AgentDomain.PATTERN, AgentDomain.QUANT, AgentDomain.ORDER_FLOW,
        AgentDomain.TIME, AgentDomain.EPISTEMOLOGY,
    }
    assert expected.issubset(domains)


def test_full_council_with_all_nine_domains_produces_one_belief():
    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)

    belief, opinions = orchestrator.deliberate({
        AgentDomain.MACRO: MacroContext(inflation_trend="falling", central_bank_bias="dovish"),
        AgentDomain.SENTIMENT: SentimentContext(fear_greed_index=20.0),
        AgentDomain.ONCHAIN: OnChainContext(whale_accumulation=True),
        AgentDomain.TECHNICAL: TechnicalContext(trend="bullish", market_structure="higher_highs"),
        AgentDomain.PATTERN: PatternContext(structure_phase="accumulation", break_of_structure="bullish"),
        AgentDomain.QUANT: QuantContext(zscore=-2.0, hurst_exponent=0.3),
        AgentDomain.ORDER_FLOW: OrderFlowContext(bid_ask_imbalance=0.4),
        AgentDomain.TIME: TimeContext(),
        AgentDomain.EPISTEMOLOGY: EpistemologyContext(feature_completeness=0.9),
    })

    assert len(opinions) == 9
    assert belief.direction in ("LONG", "SHORT", "WAIT")
    assert belief.total_opinions == 9

    # Time/Epistemology her zaman WAIT oyu verir — gerçek bir muhalefet
    # olarak kayda geçmeli, sessizce yutulmamalı.
    domains_voting_wait = {o.domain for o in opinions if o.direction == "WAIT"}
    assert AgentDomain.TIME in domains_voting_wait
    assert AgentDomain.EPISTEMOLOGY in domains_voting_wait
