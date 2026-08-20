"""Faz 310 — kullanıcı isteği: "self modeli karar hattına bağlayalım."
Self-Model (services/self_model_gatherer.py) şu ana kadar SADECE
dashboard raporuydu — sistem "kendine ne kadar güvendiğini" biliyordu ama
bu bilgiyi kararlarında hiç kullanmıyordu (3. dış rapor bulgusu, kullanıcı
doğrulattı).

kill_switch_active/concept_drift_detected BİLEREK burada test edilmiyor —
zaten ayrı yollarla enforce ediliyorlar (ai_enabled kalıcı false, ayrı
RiskReason). Bu testler SADECE yeni katılan iki sinyali (recent_dsr, ece)
doğruluyor."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from engines.cognitive_pipeline import MetaStage


def _belief() -> Belief:
    return Belief(
        direction="LONG", strength=0.95, uncertainty=0.0,
        cluster_disagreement=0.0, cluster_balance=1.0, crowding_penalty=0.0,
        entropy=0.5,
    )


def _supportive_opinions() -> list[AgentOpinion]:
    opinions = []
    for domain in (AgentDomain.MACRO, AgentDomain.TECHNICAL, AgentDomain.QUANT):
        o = AgentOpinion(domain=domain, direction="LONG", confidence=0.8)
        o.effective_influence = 0.6
        opinions.append(o)
    return opinions


def _mock_snapshot(monkeypatch, recent_dsr=None, ece=None):
    monkeypatch.setattr(
        "services.self_model_gatherer.get_cached_self_reliability_snapshot",
        lambda: {"inputs": {"recent_dsr": recent_dsr, "ece": ece}},
    )


def test_untrustworthy_dsr_forces_wait(monkeypatch):
    """recent_dsr < UNTRUSTWORTHY_DSR_THRESHOLD (0.3) — kill switch'e
    yakın ciddiyette, ACT'i tamamen bloke etmeli."""
    _mock_snapshot(monkeypatch, recent_dsr=0.1)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief(), _supportive_opinions())

    assert result_ctx.decision.action == ActionType.WAIT
    assert result_ctx.decision.final_size == 0.0


def test_degraded_dsr_downgrades_act_to_reduce(monkeypatch):
    """DEGRADED_DSR_THRESHOLD (0.5) altında ama UNTRUSTWORTHY (0.3)
    üstünde — entropy gate'le AYNI ilke: WAIT'e değil REDUCE'a zorlar."""
    _mock_snapshot(monkeypatch, recent_dsr=0.4)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief(), _supportive_opinions())

    assert result_ctx.decision.action == ActionType.REDUCE
    assert result_ctx.decision.final_size < ctx.decision.proposed_size
    assert result_ctx.decision.final_size > 0.0


def test_poor_calibration_downgrades_act_to_reduce(monkeypatch):
    """DSR sağlıklı olsa bile kötü kalibrasyon (ece > 0.1) tek başına
    REDUCE'a zorlamalı — güven skoru güvenilir olmasa bile."""
    _mock_snapshot(monkeypatch, recent_dsr=0.999, ece=0.25)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief(), _supportive_opinions())

    assert result_ctx.decision.action == ActionType.REDUCE


def test_high_reliability_keeps_full_act_size(monkeypatch):
    """Gerçek şu anki canlı duruma yakın (DSR~0.999, ece düşük) — mevcut
    davranış hiç değişmemeli."""
    _mock_snapshot(monkeypatch, recent_dsr=0.999, ece=0.02)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief(), _supportive_opinions())

    assert result_ctx.decision.action in (ActionType.ENTER_LONG, ActionType.ENTER_SHORT)
    assert result_ctx.decision.final_size > 0.0


def test_missing_snapshot_data_fails_closed_to_unchanged_behavior(monkeypatch):
    """recent_dsr/ece None (yetersiz kanıt) — "kanıtlanana kadar güven"
    ilkesi, gate hiç tetiklenmemeli."""
    _mock_snapshot(monkeypatch, recent_dsr=None, ece=None)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief(), _supportive_opinions())

    assert result_ctx.decision.action in (ActionType.ENTER_LONG, ActionType.ENTER_SHORT)
    assert result_ctx.decision.final_size > 0.0


def test_gate_does_not_affect_wait_decisions(monkeypatch):
    """Zaten WAIT'e düşmüş bir karar bu gate yüzünden değişmemeli — SADECE
    ACT'i sıkılaştırır, asla gevşetmez."""
    _mock_snapshot(monkeypatch, recent_dsr=0.4)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    weak_belief = Belief(
        direction="LONG", strength=0.05, uncertainty=0.9,
        cluster_disagreement=0.9, cluster_balance=1.0, crowding_penalty=0.0,
        entropy=0.3,
    )
    stage = MetaStage()
    result_ctx = stage.execute(ctx, weak_belief, _supportive_opinions())

    assert result_ctx.decision.action == ActionType.WAIT
    assert result_ctx.decision.final_size == 0.0


def test_snapshot_lookup_failure_fails_closed_to_unchanged_behavior(monkeypatch):
    """Self-Model sorgusu (ör. DB hatası) patlarsa gate sessizce
    atlanmalı — yeni bir gözlemsel katman canlı kararları asla
    çökertmemeli."""
    def _raise():
        raise RuntimeError("boom")

    monkeypatch.setattr("services.self_model_gatherer.get_cached_self_reliability_snapshot", _raise)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief(), _supportive_opinions())

    assert result_ctx.decision.action in (ActionType.ENTER_LONG, ActionType.ENTER_SHORT)
    assert result_ctx.decision.final_size > 0.0
