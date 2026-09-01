"""Faz 401 — Market State / Direction Katmanı Faz 1: KnowledgeStage'de
visibility-only bir relevant_knowledge girdisi (tests/
test_knowledge_stage_cross_asset_context.py'deki AYNI desen). Sembol-bazlı
kısım her zaman hesaplanır (sıfır maliyetli saf fonksiyon); küme-bazlı
kısım SADECE en son kaydedilmiş market_state_snapshots raporunda bu
sembol varsa eklenir."""
from contracts.context import CognitiveCycleContext
from contracts.market_state_report import MarketStateReport
from database.repositories.market_state_report_repository import (
    MarketStateReportModel,
    MarketStateReportRepository,
)
from database.session_factory import SessionFactory
from engines.cognitive_pipeline import KnowledgeStage


def _cleanup(report_id) -> None:
    with SessionFactory.get_session() as session:
        session.query(MarketStateReportModel).filter_by(id=report_id).delete()
        session.commit()


def test_appends_per_symbol_market_state_even_without_a_saved_cluster_report():
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    ctx.market.features = {"long_term_trend_regime": "bull_trend", "hurst_exponent": 0.7}

    ctx = KnowledgeStage().execute(ctx)

    entries = [i for i in ctx.cognition.relevant_knowledge if i.get("type") == "market_state"]
    assert len(entries) == 1
    assert entries[0]["data"]["direction"] == "LONG"
    assert entries[0]["data"]["cluster_peer_count"] is None


def test_appends_cluster_fields_when_a_saved_report_covers_this_symbol():
    report = MarketStateReport(result={
        "by_symbol": {"BTCUSDT": {"peer_count": 3, "cluster_agreement": 0.67, "cluster_reversing_fraction": 0.33}},
    })
    with SessionFactory.get_session() as session:
        MarketStateReportRepository(session).save(report)
    try:
        ctx = CognitiveCycleContext()
        ctx.market.symbol = "BTCUSDT"
        ctx.market.features = {"long_term_trend_regime": "bear_trend", "hurst_exponent": 0.2}

        ctx = KnowledgeStage().execute(ctx)

        entries = [i for i in ctx.cognition.relevant_knowledge if i.get("type") == "market_state"]
        assert entries[0]["data"]["cluster_peer_count"] == 3
        assert entries[0]["data"]["cluster_agreement"] == 0.67
        assert entries[0]["data"]["direction"] == "SHORT"
    finally:
        _cleanup(report.id)


def test_missing_features_defaults_to_neutral_not_invented():
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "SOMENEWUSDT"
    ctx.market.features = {}

    ctx = KnowledgeStage().execute(ctx)

    entries = [i for i in ctx.cognition.relevant_knowledge if i.get("type") == "market_state"]
    assert entries[0]["data"]["direction"] == "NEUTRAL"
    assert entries[0]["data"]["confidence"] == 0.0
