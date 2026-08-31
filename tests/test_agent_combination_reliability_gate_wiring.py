"""Faz 367-devam — decision_recorder.py::record()'a wire edilen Ajan
Kombinasyonu Güvenilirliği Kapısı entegrasyon testleri. tests/
test_mae_mfe_bucket_gate_wiring.py'deki AYNI desen."""
import uuid

from contracts.agent import AgentDomain, AgentOpinion
from contracts.agent_combination_reliability_report import AgentCombinationReliabilityReport
from contracts.context import CognitiveCycleContext
from database.repositories.agent_combination_reliability_report_repository import (
    AgentCombinationReliabilityReportRepository,
)
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder


def _reset_defaults() -> None:
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        repo.set("agent_combination_gate_enabled", "false", updated_by="test")
        repo.set("agent_combination_gate_min_win_rate", "0.80", updated_by="test")


def _enable_gate(min_win_rate: float = 0.80) -> None:
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


def _ctx(symbol: str, direction: str = "LONG") -> CognitiveCycleContext:
    return CognitiveCycleContext(
        market={"symbol": symbol, "raw_snapshot": {"close": 100.0}, "features": {}},
        decision={
            "proposed_direction": direction, "final_action": direction,
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )


def _opinions(domains: list[AgentDomain], direction: str = "LONG") -> list[AgentOpinion]:
    result = []
    for d in domains:
        o = AgentOpinion(domain=d, direction=direction, confidence=0.8)
        o.recalculate()
        result.append(o)
    return result


_LOW_TRUSTED_PAIR = {
    "domains": ["technical", "quant"], "combination_size": 2, "sample_size": 40,
    "win_rate": 0.40, "win_rate_delta_vs_baseline": -0.30, "fdr_significant": True,
    "max_shared_trade_overlap_pct": 0.1, "max_shared_trade_overlap_with": None,
    "distinct_days": 10,
}


def test_gate_disabled_by_default_does_not_block():
    _reset_defaults()
    _save_report([_LOW_TRUSTED_PAIR])
    symbol = f"ACRTEST{uuid.uuid4().hex[:6]}USDT"
    event = DecisionRecorder().record(_ctx(symbol), _opinions([AgentDomain.TECHNICAL, AgentDomain.QUANT]))
    assert event.status == "open"


def test_enabled_gate_blocks_a_known_low_reliability_matching_group():
    _reset_defaults()
    _enable_gate(min_win_rate=0.80)
    _save_report([_LOW_TRUSTED_PAIR])
    symbol = f"ACRTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), _opinions([AgentDomain.TECHNICAL, AgentDomain.QUANT]))
        assert event.status == "no_trade"

        # Kullanıcı isteği (2026-08-31): bu kapı da diğerleriyle AYNI
        # desende artık görünürlük bırakıyor.
        gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block"]
        assert len(gate_blocks) == 1
        assert gate_blocks[0]["data"]["gate"] == "agent_combination_gate"
        assert set(gate_blocks[0]["data"]["agreeing_domains"]) == {"technical", "quant"}
    finally:
        _reset_defaults()


def test_enabled_gate_does_not_block_when_agreeing_domains_dont_match():
    """Bilinen düşük-güvenilirlikli grup (technical+quant) bu kararda
    HİÇ anlaşmamış (sadece macro anlaşmış) — engellenmemeli."""
    _reset_defaults()
    _enable_gate(min_win_rate=0.80)
    _save_report([_LOW_TRUSTED_PAIR])
    symbol = f"ACRTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), _opinions([AgentDomain.MACRO]))
        assert event.status == "open"
    finally:
        _reset_defaults()


def test_enabled_gate_ignores_a_pair_that_is_not_fdr_significant():
    """FDR'ı geçmemiş bir 'düşük' win_rate — istatistiksel olarak gürültü
    olabilir, gerçek bir kanıt sayılmıyor, engellememeli."""
    _reset_defaults()
    _enable_gate(min_win_rate=0.80)
    not_significant = dict(_LOW_TRUSTED_PAIR, fdr_significant=False)
    _save_report([not_significant])
    symbol = f"ACRTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), _opinions([AgentDomain.TECHNICAL, AgentDomain.QUANT]))
        assert event.status == "open"
    finally:
        _reset_defaults()


def test_enabled_gate_ignores_a_pair_with_high_shared_trade_overlap():
    """Kullanıcı bulgusu (2026-08-28): örtüşme yüksekse (aynı işlemlerin
    tekrar sayımı olabilir) bu grup 'bağımsız kanıt' sayılmıyor,
    engellememeli — sadece gerçekten örtüşmesiz gruplar güvenilir."""
    _reset_defaults()
    _enable_gate(min_win_rate=0.80)
    high_overlap = dict(_LOW_TRUSTED_PAIR, max_shared_trade_overlap_pct=0.9)
    _save_report([high_overlap])
    symbol = f"ACRTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), _opinions([AgentDomain.TECHNICAL, AgentDomain.QUANT]))
        assert event.status == "open"
    finally:
        _reset_defaults()


def test_enabled_gate_does_not_block_a_high_reliability_matching_group():
    _reset_defaults()
    _enable_gate(min_win_rate=0.80)
    high_pair = dict(_LOW_TRUSTED_PAIR, win_rate=0.95, win_rate_delta_vs_baseline=0.25)
    _save_report([high_pair])
    symbol = f"ACRTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), _opinions([AgentDomain.TECHNICAL, AgentDomain.QUANT]))
        assert event.status == "open"
    finally:
        _reset_defaults()


def test_enabled_gate_with_no_saved_report_does_not_block():
    """Fail-open: rapor hiç oluşmamışsa (yeni kurulum) hiçbir zaman
    engellenmez."""
    _reset_defaults()
    _enable_gate(min_win_rate=0.80)
    symbol = f"ACRTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), _opinions([AgentDomain.TECHNICAL, AgentDomain.QUANT]))
        assert event.status == "open"
    finally:
        _reset_defaults()
