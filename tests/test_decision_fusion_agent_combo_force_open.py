"""Faz 392 — DecisionFusion içindeki Ajan Kombinasyonu Force-Open
entegrasyonu. tests/test_decision_fusion_short_exploration.py'deki AYNI
desen: SADECE kablolamayı doğruluyoruz (force_open_eligible_pairs/
is_agent_combination_force_eligible'ın kendi mantığı zaten tests/
test_agent_combination_reliability_gate.py'de ayrı test edildi;
is_eligible'ın (kill switch/concurrent cap) kendi mantığı tests/
test_agent_combination_reliability_force_open.py'de ayrı test edildi).

Faz 392 düzeltme (aynı gün) — kullanıcı itirazı üzerine ("Onların
güvenilmez olduklarına ne kadar eminiz?"): ayrı bir force-open win_rate
eşiği YOK, kullanıcının panelden kontrol ettiği Karar Kapısı'nın kendi
eşiğini (`agent_combination_gate_enabled`/`agent_combination_gate_min_
win_rate`) paylaşır. Kapı kapalıysa win_rate hiç filtrelenmez."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.agent_combination_reliability_report import AgentCombinationReliabilityReport
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from database.repositories.agent_combination_reliability_report_repository import (
    AgentCombinationReliabilityReportRepository,
)
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.agent_combination_reliability_force_open import EXPERIMENT_BUCKET
from services.decision_fusion import DecisionFusion

# gate_eligible=True ama win_rate BİLEREK düşük (baseline'ın altında) —
# "kapı kapalıyken win_rate hiç filtrelenmiyor" davranışını test etmek
# için: sadece kapı uygunluğu (istatistiksel geçerlilik) yeterli olmalı.
_LOW_WIN_RATE_GATE_ELIGIBLE_PAIR = {
    "domains": ["onchain", "order_flow"], "combination_size": 2, "sample_size": 40,
    "win_rate": 0.50, "win_rate_delta_vs_baseline": -0.20, "fdr_significant": True,
    "max_shared_trade_overlap_pct": 0.1, "max_shared_trade_overlap_with": None,
    "distinct_days": 10, "oos_survival": True, "effective_sample_size": 36,
    "gate_eligible": True,
}


def _reset_defaults() -> None:
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        repo.set("agent_combination_force_open_enabled", "false", updated_by="test")
        repo.set("agent_combination_gate_enabled", "false", updated_by="test")
        repo.set("agent_combination_gate_min_win_rate", "0.74", updated_by="test")


def _enable_force_open() -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("agent_combination_force_open_enabled", "true", updated_by="test")


def _enable_block_gate(min_win_rate: float) -> None:
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        repo.set("agent_combination_gate_enabled", "true", updated_by="test")
        repo.set("agent_combination_gate_min_win_rate", str(min_win_rate), updated_by="test")


def _save_report(pairs: list[dict]) -> None:
    with SessionFactory.get_session() as session:
        AgentCombinationReliabilityReportRepository(session).save(
            AgentCombinationReliabilityReport(
                result={"pairs": pairs, "baseline_win_rate": 0.7, "baseline_sample_size": 100, "n_trades": 100},
            )
        )


def _ctx(direction: str, take_profit: float, stop_loss: float, confidence: float, proposed_size: float = 10.0):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "SOLUSDT"
    ctx.market.raw_snapshot = {"close": 100.0}
    ctx.decision.proposed_direction = direction
    ctx.decision.proposed_size = proposed_size
    ctx.decision.final_size = proposed_size
    ctx.decision.confidence = confidence
    ctx.decision.take_profit_distance = take_profit
    ctx.decision.stop_loss_distance = stop_loss
    return ctx


def _opinions(domains: list[AgentDomain], direction: str) -> list[AgentOpinion]:
    result = []
    for d in domains:
        o = AgentOpinion(domain=d, direction=direction, confidence=0.8)
        o.recalculate()
        result.append(o)
    return result


def _relevant_knowledge_types(ctx):
    return [item.get("type") for item in ctx.cognition.relevant_knowledge]


def test_force_open_disabled_by_default_negative_ev_still_waits():
    _reset_defaults()
    _save_report([_LOW_WIN_RATE_GATE_ELIGIBLE_PAIR])
    try:
        ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
        opinions = _opinions([AgentDomain.ONCHAIN, AgentDomain.ORDER_FLOW], "LONG")
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3), opinions)

        assert ctx.decision.action == ActionType.WAIT
        assert "experiment_bucket" not in _relevant_knowledge_types(ctx)
    finally:
        _reset_defaults()


def test_force_open_enabled_with_block_gate_off_ignores_win_rate_entirely(monkeypatch):
    """Kullanıcı isteği (2026-08-31): blok kapısı kapalıyken (kullanıcının
    kendi tercihi, "güvenilir/güvenilmez" ayrımı yapılmasın istiyor)
    win_rate hiç filtrelenmemeli — sadece kapı uygunluğu (gate_eligible)
    yeterli, düşük win_rate'li (%50, baseline altı) bir grup bile
    force-open tetiklemeli."""
    monkeypatch.setattr("services.agent_combination_reliability_force_open.is_eligible", lambda: (True, None))
    _reset_defaults()
    _enable_force_open()
    _save_report([_LOW_WIN_RATE_GATE_ELIGIBLE_PAIR])
    try:
        ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
        opinions = _opinions([AgentDomain.ONCHAIN, AgentDomain.ORDER_FLOW], "LONG")
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3), opinions)

        assert ctx.decision.action == ActionType.ENTER_LONG
        assert 0.0 < ctx.decision.final_size <= 10.0 * 0.5
        assert "experiment_bucket" in _relevant_knowledge_types(ctx)
        bucket_item = next(i for i in ctx.cognition.relevant_knowledge if i["type"] == "experiment_bucket")
        assert bucket_item["data"]["bucket"] == EXPERIMENT_BUCKET
    finally:
        _reset_defaults()


def test_force_open_enabled_with_block_gate_on_uses_its_threshold(monkeypatch):
    """Blok kapısı AÇIKKEN, force-open aynı eşiği kullanır — eşiğin
    altındaki bir grup açmaz."""
    monkeypatch.setattr("services.agent_combination_reliability_force_open.is_eligible", lambda: (True, None))
    _reset_defaults()
    _enable_force_open()
    _enable_block_gate(min_win_rate=0.80)
    _save_report([_LOW_WIN_RATE_GATE_ELIGIBLE_PAIR])  # win_rate=0.50 < 0.80
    try:
        ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
        opinions = _opinions([AgentDomain.ONCHAIN, AgentDomain.ORDER_FLOW], "LONG")
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3), opinions)

        assert ctx.decision.action == ActionType.WAIT
        assert "experiment_bucket" not in _relevant_knowledge_types(ctx)
    finally:
        _reset_defaults()


def test_force_open_enabled_with_block_gate_on_and_pair_above_threshold_opens(monkeypatch):
    monkeypatch.setattr("services.agent_combination_reliability_force_open.is_eligible", lambda: (True, None))
    _reset_defaults()
    _enable_force_open()
    _enable_block_gate(min_win_rate=0.40)
    _save_report([_LOW_WIN_RATE_GATE_ELIGIBLE_PAIR])  # win_rate=0.50 >= 0.40
    try:
        ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
        opinions = _opinions([AgentDomain.ONCHAIN, AgentDomain.ORDER_FLOW], "LONG")
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3), opinions)

        assert ctx.decision.action == ActionType.ENTER_LONG
    finally:
        _reset_defaults()


def test_force_open_enabled_but_no_matching_domains_stays_waiting(monkeypatch):
    monkeypatch.setattr("services.agent_combination_reliability_force_open.is_eligible", lambda: (True, None))
    _reset_defaults()
    _enable_force_open()
    _save_report([_LOW_WIN_RATE_GATE_ELIGIBLE_PAIR])
    try:
        ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
        # Sadece macro anlaşmış — bilinen grup (onchain+order_flow) HİÇ eşleşmiyor.
        opinions = _opinions([AgentDomain.MACRO], "LONG")
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3), opinions)

        assert ctx.decision.action == ActionType.WAIT
        assert "experiment_bucket" not in _relevant_knowledge_types(ctx)
    finally:
        _reset_defaults()


def test_force_open_enabled_but_safety_check_blocks(monkeypatch):
    """Kill switch/concurrent cap tetiklenmişse (is_eligible False),
    eşleşen grup olsa bile pozisyon açılmaz."""
    monkeypatch.setattr(
        "services.agent_combination_reliability_force_open.is_eligible",
        lambda: (False, "force_open_kill_switch_active"),
    )
    _reset_defaults()
    _enable_force_open()
    _save_report([_LOW_WIN_RATE_GATE_ELIGIBLE_PAIR])
    try:
        ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
        opinions = _opinions([AgentDomain.ONCHAIN, AgentDomain.ORDER_FLOW], "LONG")
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3), opinions)

        assert ctx.decision.action == ActionType.WAIT
        assert "experiment_bucket" not in _relevant_knowledge_types(ctx)
    finally:
        _reset_defaults()


def test_force_open_not_gate_eligible_never_opens_regardless_of_block_gate_state(monkeypatch):
    """gate_eligible=False (yetersiz örneklem/anlamlılık) — blok kapısı
    kapalı olsa bile (win_rate filtresi yok) force-open TETİKLENMEMELİ,
    çünkü bu istatistiksel geçerlilik şartı, kullanıcının "yüz kere
    yaşama" ilkesinin ta kendisi, kapı durumundan bağımsız."""
    monkeypatch.setattr("services.agent_combination_reliability_force_open.is_eligible", lambda: (True, None))
    _reset_defaults()
    _enable_force_open()
    not_gate_eligible = {**_LOW_WIN_RATE_GATE_ELIGIBLE_PAIR, "win_rate": 0.99, "gate_eligible": False}
    _save_report([not_gate_eligible])
    try:
        ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
        opinions = _opinions([AgentDomain.ONCHAIN, AgentDomain.ORDER_FLOW], "LONG")
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3), opinions)

        assert ctx.decision.action == ActionType.WAIT
        assert "experiment_bucket" not in _relevant_knowledge_types(ctx)
    finally:
        _reset_defaults()


def test_force_open_works_for_short_direction_too(monkeypatch):
    """Kullanıcı isteği SHORT'a özel değil — LONG'da da geçerli olduğu
    gibi SHORT'ta da aynen çalışmalı."""
    monkeypatch.setattr("services.agent_combination_reliability_force_open.is_eligible", lambda: (True, None))
    _reset_defaults()
    _enable_force_open()
    _save_report([_LOW_WIN_RATE_GATE_ELIGIBLE_PAIR])
    try:
        ctx = _ctx("SHORT", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
        opinions = _opinions([AgentDomain.ONCHAIN, AgentDomain.ORDER_FLOW], "SHORT")
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="SHORT", strength=0.3), opinions)

        assert ctx.decision.action == ActionType.ENTER_SHORT
        assert 0.0 < ctx.decision.final_size <= 10.0 * 0.5
    finally:
        _reset_defaults()
