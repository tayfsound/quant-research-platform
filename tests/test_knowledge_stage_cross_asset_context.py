"""FIL Faz C — kullanıcı isteği (2026-08-31): Causal Inference'in
(Granger causality — BTC/ETH'nin diğer sembolleri öngörüp öngörmediği)
haftalık raporu, KnowledgeStage'de visibility-only bir relevant_knowledge
girdisi olarak ekleniyor. SADECE son kaydedilmiş rapor okunuyor (CANLI
gather_causal_relationships() ÇAĞRILMIYOR — pahalı olurdu)."""
from contracts.causal_inference_report import CausalInferenceReport
from contracts.context import CognitiveCycleContext
from database.repositories.causal_inference_report_repository import (
    CausalInferenceReportRepository,
)
from database.session_factory import SessionFactory
from engines.cognitive_pipeline import KnowledgeStage


def _save_report(relationships: list[dict]) -> None:
    with SessionFactory.get_session() as session:
        CausalInferenceReportRepository(session).save(
            CausalInferenceReport(
                result={
                    "cause_symbols_tested": ["BTCUSDT", "ETHUSDT"],
                    "effect_symbols_tested": [],
                    "pairs_tested": 1,
                    "significant_relationships": relationships,
                    "fdr_significant_relationships": relationships,
                    "fdr_alpha": 0.05,
                }
            )
        )


def test_appends_cross_asset_context_when_symbol_is_a_known_effect():
    _save_report([
        {"cause": "BTCUSDT", "effect": "SOLUSDT", "best_lag": 3, "best_p_value": 0.012,
         "sample_size": 180, "fdr_significant": True},
    ])
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "SOLUSDT"

    ctx = KnowledgeStage().execute(ctx)

    entries = [i for i in ctx.cognition.relevant_knowledge if i.get("type") == "cross_asset_context"]
    assert len(entries) == 1
    assert entries[0]["data"] == {"cause": "BTCUSDT", "best_lag": 3, "best_p_value": 0.012, "sample_size": 180}


def test_no_entry_when_symbol_is_not_a_known_effect():
    _save_report([
        {"cause": "BTCUSDT", "effect": "SOLUSDT", "best_lag": 3, "best_p_value": 0.012,
         "sample_size": 180, "fdr_significant": True},
    ])
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "UNRELATEDUSDT"

    ctx = KnowledgeStage().execute(ctx)

    entries = [i for i in ctx.cognition.relevant_knowledge if i.get("type") == "cross_asset_context"]
    assert entries == []


def test_appends_multiple_entries_when_both_btc_and_eth_predict_the_symbol():
    _save_report([
        {"cause": "BTCUSDT", "effect": "DOGEUSDT", "best_lag": 1, "best_p_value": 0.02,
         "sample_size": 150, "fdr_significant": True},
        {"cause": "ETHUSDT", "effect": "DOGEUSDT", "best_lag": 2, "best_p_value": 0.03,
         "sample_size": 150, "fdr_significant": True},
    ])
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "DOGEUSDT"

    ctx = KnowledgeStage().execute(ctx)

    entries = [i for i in ctx.cognition.relevant_knowledge if i.get("type") == "cross_asset_context"]
    assert {e["data"]["cause"] for e in entries} == {"BTCUSDT", "ETHUSDT"}
