"""Faz 268g — "İsabeti artırmanın yolu daha akıllı kullanım" yol
haritasının D fazı. MetaStage'in ACT dalı (confidence >= act_threshold),
Kelly çarpanının (services/kelly_sizing.py) matematiği ayrı test ediliyor
(test_kelly_sizing.py) — burada SADECE MetaStage.execute()'ın bunu
gerçekten çağırıp final_size'ı ölçeklendirdiği doğrulanıyor."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from engines.cognitive_pipeline import MetaStage


def _high_confidence_long_belief() -> Belief:
    return Belief(
        direction="LONG", strength=0.95, uncertainty=0.0,
        cluster_disagreement=0.0, cluster_balance=1.0, crowding_penalty=0.0,
    )


def _supportive_opinions() -> list[AgentOpinion]:
    """Faz 268-sonrası: MetaStage artık opinions'a bakıp (a) güçlü tek-ses
    itirazı ve (b) ince konsey kontrolü yapıyor — bu testler o kontrollerin
    KONUSU değil (Kelly çarpanını test ediyorlar), o yüzden her ikisini de
    rahatça geçecek, belief ile UYUMLU 3 gerçek yönlü oy veriyoruz."""
    opinions = []
    for domain in (AgentDomain.MACRO, AgentDomain.TECHNICAL, AgentDomain.QUANT):
        o = AgentOpinion(domain=domain, direction="LONG", confidence=0.7)
        o.effective_influence = 0.6
        opinions.append(o)
    return opinions


def test_act_tier_final_size_is_scaled_by_kelly_multiplier(monkeypatch):
    import engines.cognitive_pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "kelly_size_multiplier", lambda confidence, regime=None: 0.3)

    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _high_confidence_long_belief(), _supportive_opinions())

    assert result_ctx.decision.confidence >= 0.7  # gerçekten ACT'e ulaştı
    assert abs(result_ctx.decision.final_size - 0.3) < 1e-9  # 1.0 * 0.3


def test_act_tier_with_no_kelly_data_keeps_full_size(monkeypatch):
    """Yeterli veri yoksa (fail-closed) çarpan 1.0 — mevcut davranış
    (tam boyut) hiç değişmemeli, regresyon yok."""
    import engines.cognitive_pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "kelly_size_multiplier", lambda confidence, regime=None: 1.0)

    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _high_confidence_long_belief(), _supportive_opinions())

    assert result_ctx.decision.final_size == 1.0


def test_act_tier_kelly_multiplier_never_increases_size_beyond_proposed(monkeypatch):
    """Çarpan [0,1] dışına (ör. yanlışlıkla >1) çıksa bile final_size
    proposed_size'ı aşmamalı — bu testin amacı MetaStage'in çarpanı
    olduğu gibi çarptığını doğrulamak (asıl [0,1] kısıtlaması kelly_
    sizing.py'de, test_kelly_sizing.py'de doğrulanıyor); burada sadece
    normal aralıktaki bir çarpanla final_size'ın gerçekten küçüldüğünü
    (büyümediğini) kanıtlıyoruz."""
    import engines.cognitive_pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "kelly_size_multiplier", lambda confidence, regime=None: 0.6)

    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 2.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _high_confidence_long_belief(), _supportive_opinions())

    assert result_ctx.decision.final_size < ctx.decision.proposed_size
    assert abs(result_ctx.decision.final_size - 1.2) < 1e-9
