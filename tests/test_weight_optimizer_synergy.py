"""Faz 367-devam — kullanıcı isteği: "ajan kombinasyon kısmındaki gate
değerinin üzerinde bir kombinasyon gelirse, bu kombinasyondaki ajanları
güçlendirsin." services/weight_optimizer.py::WeightOptimizer.
_compute_synergy_adjustments + propose_weights() entegrasyonu."""
from contracts.agent_combination_reliability_report import AgentCombinationReliabilityReport
from contracts.agent_performance import AgentPerformanceRecord
from database.repositories.agent_combination_reliability_report_repository import (
    AgentCombinationReliabilityReportRepository,
)
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.agent_memory import AgentMemory
from services.weight_optimizer import MAX_SYNERGY_ADJUSTMENT, WeightOptimizer
from services.weight_repository import WeightRepository


def _save_report(pairs: list[dict]) -> None:
    with SessionFactory.get_session() as session:
        AgentCombinationReliabilityReportRepository(session).save(
            AgentCombinationReliabilityReport(
                result={"pairs": pairs, "baseline_win_rate": 0.7, "baseline_sample_size": 100, "n_trades": 100},
            )
        )


def _set_threshold(value: str) -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("agent_combination_gate_min_win_rate", value, updated_by="test")


_STRONG_PAIR = {
    "domains": ["technical", "quant"], "win_rate": 0.95,
    "fdr_significant": True, "max_shared_trade_overlap_pct": 0.1, "sample_size": 40,
    "distinct_days": 10,
}
_WEAK_PAIR = {
    "domains": ["macro", "credit"], "win_rate": 0.40,
    "fdr_significant": True, "max_shared_trade_overlap_pct": 0.1, "sample_size": 40,
    "distinct_days": 10,
}


def test_compute_synergy_adjustments_boosts_domains_in_a_strong_trustworthy_group():
    _set_threshold("0.74")
    _save_report([_STRONG_PAIR])
    try:
        adjustments = WeightOptimizer._compute_synergy_adjustments(["technical", "quant", "macro"])
        assert adjustments["technical"] > 0
        assert adjustments["quant"] > 0
        assert "macro" not in adjustments
    finally:
        _set_threshold("0.74")


def test_compute_synergy_adjustments_never_penalizes_a_below_threshold_group():
    """Sadece güçlendirme yönü — eşiğin altındaki bir grup HİÇ katkı
    vermemeli (negatif düzeltme yok), o zaten decision-time kapısının işi."""
    _set_threshold("0.74")
    _save_report([_WEAK_PAIR])
    try:
        adjustments = WeightOptimizer._compute_synergy_adjustments(["macro", "credit"])
        assert adjustments == {}
    finally:
        _set_threshold("0.74")


def test_compute_synergy_adjustments_ignores_a_pair_that_is_not_fdr_significant():
    _set_threshold("0.74")
    not_significant = dict(_STRONG_PAIR, fdr_significant=False)
    _save_report([not_significant])
    try:
        adjustments = WeightOptimizer._compute_synergy_adjustments(["technical", "quant"])
        assert adjustments == {}
    finally:
        _set_threshold("0.74")


def test_compute_synergy_adjustments_ignores_a_pair_with_high_shared_trade_overlap():
    _set_threshold("0.74")
    high_overlap = dict(_STRONG_PAIR, max_shared_trade_overlap_pct=0.9)
    _save_report([high_overlap])
    try:
        adjustments = WeightOptimizer._compute_synergy_adjustments(["technical", "quant"])
        assert adjustments == {}
    finally:
        _set_threshold("0.74")


def test_compute_synergy_adjustments_is_bounded_by_max_synergy_adjustment():
    _set_threshold("0.74")
    extreme_pair = dict(_STRONG_PAIR, win_rate=1.0)
    _save_report([extreme_pair])
    try:
        adjustments = WeightOptimizer._compute_synergy_adjustments(["technical"])
        assert adjustments["technical"] <= MAX_SYNERGY_ADJUSTMENT
    finally:
        _set_threshold("0.74")


def test_compute_synergy_adjustments_returns_empty_with_no_saved_report(monkeypatch):
    """Fail-closed: rapor hiç oluşmamışsa hiçbir düzeltme uygulanmaz.
    Paylaşılan quantdb_test'te başka testlerden kalan bir rapor olabildiği
    için (bkz. AGENT_MEMORY "shared test state bloat"), get_latest()
    doğrudan None döndürecek şekilde monkeypatch'leniyor — testin kendi
    izolasyonu gerçek DB temizliğine bağımlı kalmasın diye."""
    from database.repositories.agent_combination_reliability_report_repository import (
        AgentCombinationReliabilityReportRepository,
    )
    monkeypatch.setattr(AgentCombinationReliabilityReportRepository, "get_latest", lambda self: None)
    adjustments = WeightOptimizer._compute_synergy_adjustments(["technical", "quant"])
    assert adjustments == {}


def test_propose_weights_applies_synergy_adjustment_and_records_it_transparently(tmp_path, monkeypatch):
    """Kullanıcı bulgusu (2026-08-28): sentiment ajanı solo %5 isabetle
    kaldırılmıştı ama pattern+sentiment gibi ikilileri %99+ isabetliydi —
    bu entegrasyon, solo zayıf ama grupta güçlü bir ajanın nihai ağırlığını
    yukarı çekmeli, VE düzeltme snapshot'ta ayrı/şeffaf görünmeli."""
    memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_history"))
    for _ in range(20):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="LONG", confidence=0.6,
            was_correct=True, market_regime="trend",
        ))
        memory.record(AgentPerformanceRecord(
            agent_domain="quant", direction="LONG", confidence=0.6,
            was_correct=True, market_regime="trend",
        ))

    _set_threshold("0.74")
    _save_report([_STRONG_PAIR])
    try:
        # Önce sinerji düzeltmesi OLMADAN solo ağırlığı ölç (karşılaştırma
        # için, monkeypatch ile geçici olarak devre dışı bırakılıyor).
        monkeypatch.setattr(WeightOptimizer, "_compute_synergy_adjustments", staticmethod(lambda domains: {}))
        weight_repo = WeightRepository(storage_path=str(tmp_path / "weight_history"))
        optimizer = WeightOptimizer(memory, weight_repository=weight_repo)
        solo_snapshot = optimizer.propose_weights()
        monkeypatch.undo()

        weight_repo_2 = WeightRepository(storage_path=str(tmp_path / "weight_history_2"))
        optimizer_2 = WeightOptimizer(memory, weight_repository=weight_repo_2)
        boosted_snapshot = optimizer_2.propose_weights()

        assert boosted_snapshot.weights["technical"] > solo_snapshot.weights["technical"]
        assert boosted_snapshot.synergy_adjustments.get("technical", 0.0) > 0
        assert boosted_snapshot.synergy_adjustments.get("quant", 0.0) > 0
    finally:
        _set_threshold("0.74")
