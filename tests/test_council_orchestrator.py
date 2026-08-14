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

    monkeypatch.setattr(
        co_module, "calibrate_domain_confidence",
        lambda domain, raw, evidence_count=None, symbol=None: 0.01,
    )

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


def test_deliberate_passes_each_opinions_real_evidence_count_to_calibration(monkeypatch):
    """Faz 268e — gerçek bulgu: kalibrasyon TEK kanıtlı zayıf kararları da
    tam güçle yükseltiyordu (canlıda doğrulandı, quant_agent). deliberate()
    artık her ajanın GERÇEK evidence listesinin uzunluğunu kalibrasyona
    iletmeli — sabit/varsayılan bir sayı değil."""
    import services.council_orchestrator as co_module

    captured: dict[str, int] = {}

    def spy_calibrate(domain, raw, evidence_count=None, symbol=None):
        captured[domain] = evidence_count
        return raw

    monkeypatch.setattr(co_module, "calibrate_domain_confidence", spy_calibrate)

    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)
    # Faz A/B'nin agent_confidence_model çarpanı (varsa) opinion.evidence'ı
    # değiştirmiyor, sadece confidence'ı — bu testin gerçek amacı olan
    # "kaç kanıt" sayımını etkilemiyor.
    ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs")

    _, opinions = orchestrator.deliberate({AgentDomain.TECHNICAL: ctx})
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert captured["technical"] == len(technical.evidence)
    assert captured["technical"] > 0  # bullish+strengthening+higher_highs en az birkaç kanıt üretir


def test_deliberate_passes_the_real_symbol_to_calibration_for_asset_class_awareness(monkeypatch):
    """Faz 247 — kullanıcının getirdiği PAXG/XAUTUSDT raporu: kalibrasyon
    sembolü bilmeden global (BTC ağırlıklı) eğriyi her sembole aynen
    uyguluyordu. deliberate(symbol=...) artık bunu calibrate_domain_
    confidence'a iletmeli."""
    import services.council_orchestrator as co_module

    captured: dict[str, str | None] = {}

    def spy_calibrate(domain, raw, evidence_count=None, symbol=None):
        captured[domain] = symbol
        return raw

    monkeypatch.setattr(co_module, "calibrate_domain_confidence", spy_calibrate)

    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)
    ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs")

    orchestrator.deliberate({AgentDomain.TECHNICAL: ctx}, symbol="PAXGUSDT")

    assert captured["technical"] == "PAXGUSDT"


def test_deliberate_uses_the_regime_specific_snapshot_when_one_exists(tmp_path):
    """Faz 268b — Regime-Aware Learning: deliberate(regime=...)'e verilen
    rejim için bir snapshot varsa, GLOBAL en yeni snapshot değil o
    kullanılmalı. active_weight_snapshot_id ile hangi snapshot'ın
    gerçekten uygulandığı doğrulanabiliyor."""
    import shutil

    from contracts.agent_weight_snapshot import AgentWeightSnapshot
    from services.weight_repository import WeightRepository

    name = str(tmp_path / "council_regime_weights")
    try:
        repo = WeightRepository(storage_path=name)
        global_snapshot = repo.save(AgentWeightSnapshot(weights={"technical": 1.0}, regime=None).finalize())
        regime_snapshot = repo.save(
            AgentWeightSnapshot(weights={"technical": 1.0}, regime="bullish_high").finalize()
        )

        registry = AgentRegistry.create_default()
        orchestrator = CouncilOrchestrator(registry)
        orchestrator.weight_repository = repo
        ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs")

        orchestrator.deliberate({AgentDomain.TECHNICAL: ctx}, regime="bullish_high")
        assert orchestrator.active_weight_snapshot_id == regime_snapshot.id

        orchestrator.deliberate({AgentDomain.TECHNICAL: ctx}, regime="never_seen_regime")
        assert orchestrator.active_weight_snapshot_id == global_snapshot.id  # fail-closed fallback
    finally:
        shutil.rmtree(name, ignore_errors=True)


def test_council_stage_derives_regime_from_market_features_and_forwards_it(monkeypatch):
    """Faz 268b — Regime-Aware Learning: CouncilStage.execute()'ın ctx.
    market.features'tan ("trend" + "volatility_regime") hesapladığı rejim,
    PositionCloser._extract_market_regime'in kapanmış işlemleri
    etiketlediği AYNI format ("trend_volatility") olmalı — aksi halde
    regime-özel snapshot'lar karar anında hiçbir zaman doğru seçilmez."""
    from contracts.context import CognitiveCycleContext
    from engines.cognitive_pipeline import CouncilStage
    import services.council_orchestrator as co_module

    captured = {}
    original_deliberate = co_module.CouncilOrchestrator.deliberate

    def spy_deliberate(self, contexts, regime=None, symbol=None):
        captured["regime"] = regime
        return original_deliberate(self, contexts, regime=regime, symbol=symbol)

    monkeypatch.setattr(co_module.CouncilOrchestrator, "deliberate", spy_deliberate)

    registry = AgentRegistry.create_default()
    stage = CouncilStage(registry)

    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    ctx.market.features = {"trend": "bullish", "volatility_regime": "high"}
    stage.execute(ctx)

    assert captured["regime"] == "bullish_high"


def test_unanswered_risk_challenge_reduces_real_vote_weight_end_to_end():
    """Faz 268-sonrası — kritik bulgu (üçüncü taraf mimari incelemesi +
    gerçek kod doğrulaması): RiskChallenger üretimde gerçekten itiraz
    üretiyordu (yüksek confidence + yüksek volatilite) ama hiçbir
    responder kayıtlı olmadığı için bu itirazın nihai oy ağırlığına SIFIR
    etkisi vardı — sadece explainability zincirine yazılıyordu. Bu test,
    uçtan uca gerçek CouncilOrchestrator.deliberate() ile, itirazın artık
    gerçekten opinion.performance_weight'i düşürdüğünü doğruluyor."""
    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)
    # score = trend(1.0) + momentum(1.0) + market_structure(1.5) +
    # ema_alignment(0.5) + rsi_extreme(1.0) = 5.0 -> confidence=min(1.0,0.85)=0.85 (>0.75).
    # adx>25 ile di_plus>di_minus (aksi halde varsayılan adx=0.0<20, "zayıf
    # trend" indirimi TÜM katkıları 0.7 ile çarpıp confidence'ı 0.75 eşiğinin
    # ALTINA düşürürdü — bu testin ilk halinde fark edilmeyen bir kurulum hatasıydı).
    # volatility_regime="high" -> _VOLATILITY_REGIME_TO_SCORE["high"]=0.8 (>0.7).
    # RiskChallenger'ın "Aşırı güven + yüksek volatilite" kontrolü tetiklenmeli.
    ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", rsi_value=20.0, volatility_regime="high",
        adx=30.0, di_plus=30.0, di_minus=10.0,
    )

    _, opinions = orchestrator.deliberate({AgentDomain.TECHNICAL: ctx})
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert orchestrator.last_debate_result.unanswered_challenge_penalties.get("technical") is not None
    assert technical.performance_weight < 1.0
    assert any("Unanswered risk challenge" in c for c in technical.caveats)


def test_single_agent_directional_agreement_is_not_flagged_as_crowding():
    """Faz 268-sonrası — kritik bulgu (tam test suite'i, RiskChallenger
    itiraz-etkisi düzeltmesi wire edilince ortaya çıktı): tek bir yönlü
    ajan varken (kısmi council) crowding_risk = 1/1 = 1.0 hesaplanıyordu —
    "sürü davranışı" tanım gereği tek bir ajanla anlamsız. En az 3
    bağımsız yönlü görüş olmadan bu kontrol hiç tetiklenmemeli, yani tek
    başına yüksek volatilite olmadan bench edilmemiş bir ajanın oy
    ağırlığı 1.0 kalmalı."""
    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)
    ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", volume_confirmation=True,
        volatility_regime="normal",
    )

    _, opinions = orchestrator.deliberate({AgentDomain.TECHNICAL: ctx})
    technical = next(o for o in opinions if o.domain == AgentDomain.TECHNICAL)

    assert technical.performance_weight == 1.0
    assert orchestrator.last_debate_result.unanswered_challenge_penalties == {}


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
