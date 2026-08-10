"""Council Orchestrator testleri — AgentDomain enum anahtarları."""
from agents.registry import AgentRegistry
from contracts.agent import AgentDomain
from contracts.macro import MacroContext
from contracts.onchain import OnChainContext
from contracts.sentiment import SentimentContext
from contracts.technical import TechnicalContext
from services.council_orchestrator import CouncilOrchestrator


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


def test_technical_confidence_model_adjusts_opinion_confidence_when_saved():
    """Faz 264: ajan içi güven kalibrasyonu — kaydedilmiş bir model varsa
    technical ajanının confidence'ı gerçek geçmiş doğruluğa göre
    ayarlanmalı; model yoksa (varsayılan test durumu, diğer testler)
    hiçbir şey değişmemeli."""
    from contracts.agent_confidence_model import AgentConfidenceModel
    from services.agent_confidence_model import ConfidenceModelRepository

    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)
    ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs", rsi_value=90.0)

    _, opinions_before = orchestrator.deliberate({AgentDomain.TECHNICAL: ctx})
    technical_before = next(o for o in opinions_before if o.domain == AgentDomain.TECHNICAL)

    repo = ConfidenceModelRepository()
    repo.save(AgentConfidenceModel(
        domain="technical",
        window_size=100,
        sample_count=100,
        numeric_features=["rsi_value"],
        boolean_features=[],
        categorical_features={},
        scaler_mean=[50.0],
        scaler_scale=[10.0],
        coefficients=[2.0],  # yuksek RSI -> yuksek P(dogru) -> carpan > 1
        intercept=0.0,
        baseline_correctness_rate=0.5,
        train_accuracy=0.6,
        test_accuracy=0.6,
    ))
    try:
        _, opinions_after = orchestrator.deliberate({AgentDomain.TECHNICAL: ctx})
        technical_after = next(o for o in opinions_after if o.domain == AgentDomain.TECHNICAL)

        assert technical_after.confidence != technical_before.confidence
        assert any("kalibrasyon" in c for c in technical_after.caveats)
    finally:
        # Diğer testleri etkilememesi için modeli kaldır.
        model_file = repo.storage_path / "technical_latest.json"
        if model_file.exists():
            model_file.unlink()
