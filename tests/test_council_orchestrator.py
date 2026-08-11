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


def test_domain_confidence_calibration_is_applied_before_recalculate(monkeypatch):
    """Faz 268al — "İsabeti artırmanın yolu daha akıllı kullanım" yol
    haritasının A fazı (Confidence Kalibrasyonu). Her ajanın oy ağırlığına
    giren confidence (bkz. AgentOpinion.recalculate -> intrinsic_trust ->
    effective_influence -> BeliefEngine oy ağırlıklandırması), council
    birleştirmesinden ÖNCE domain-özel kalibrasyon eğrisinden geçmeli.
    Eğrinin kendi matematiği ayrı test ediliyor (test_confidence_
    calibration.py) — burada SADECE deliberate()'in bunu gerçekten
    çağırıp opinion.confidence'ı (ve dolayısıyla intrinsic_trust'ı)
    değiştirdiği doğrulanıyor."""
    import services.council_orchestrator as co_module

    monkeypatch.setattr(co_module, "calibrate_domain_confidence", lambda domain, raw: 0.01)

    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)
    ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs")

    _, opinions = orchestrator.deliberate({AgentDomain.TECHNICAL: ctx})
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert technical.confidence == 0.01
    # recalculate() intrinsic_trust'ı confidence'ın %25'i üzerinden
    # hesaplıyor — kalibrasyon sonrası değerle yeniden hesaplanmış olmalı,
    # ajanın ham (kalibrasyon öncesi) beyanıyla değil.
    expected_intrinsic_trust = (
        0.01 * 0.25
        + technical.data_quality * 0.20
        + technical.evidence_strength * 0.20
        + technical.freshness * 0.15
        + technical.source_reliability * 0.20
    )
    assert abs(technical.intrinsic_trust - expected_intrinsic_trust) < 1e-9


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
