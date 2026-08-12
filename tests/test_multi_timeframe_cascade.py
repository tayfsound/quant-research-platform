"""Faz 268c — "İsabeti artırmanın yolu daha akıllı kullanım" yol
haritasının Faz C'si (Multi-Timeframe Cascade). Rapor: "1m LONG + 15m
LONG + 1h LONG üçlüsü, yalnızca 1m LONG'dan çok daha güçlü bir
konviksiyon demektir — şu an bu bilgi Council'a hiç ulaşmıyor."
"""
from unittest.mock import patch

from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.orchestrator import _combine_timeframe_beliefs


def test_combine_all_agree_long_produces_high_combined_confidence():
    beliefs = {
        "15m": {"direction": "LONG", "confidence": 0.7},
        "1h": {"direction": "LONG", "confidence": 0.6},
    }
    result = _combine_timeframe_beliefs(beliefs)
    assert result["combined_direction"] == "LONG"
    # Bağımsız kanıtların çarpımı, tek başına en güçlü kanıttan (0.7) daha
    # yüksek bir kombine olasılık üretmeli — bu tam olarak raporun
    # "birden fazla zaman dilimi teyidi = daha güçlü konviksiyon" iddiası.
    assert result["combined_confidence"] > 0.7
    assert result["agreement_count"] == 2
    assert result["total_informative"] == 2


def test_combine_conflicting_timeframes_produces_lower_confidence_than_either_alone():
    beliefs = {
        "15m": {"direction": "LONG", "confidence": 0.7},
        "1h": {"direction": "SHORT", "confidence": 0.7},
    }
    result = _combine_timeframe_beliefs(beliefs)
    # Simetrik çelişki -> ~0.5 (kararsız), her iki tarafın kendi başına
    # ürettiği 0.7'den kesinlikle düşük.
    assert result["combined_confidence"] < 0.7


def test_combine_ignores_wait_neutral_timeframes():
    beliefs = {
        "15m": {"direction": "WAIT", "confidence": 0.9},
        "1h": {"direction": "LONG", "confidence": 0.6},
    }
    result = _combine_timeframe_beliefs(beliefs)
    assert result["combined_direction"] == "LONG"
    assert result["total_informative"] == 1  # WAIT hiç sayılmadı
    assert result["combined_confidence"] == 0.6


def test_combine_with_no_informative_timeframes_returns_none_direction():
    beliefs = {"15m": {"direction": "WAIT", "confidence": 0.5}, "1h": {"direction": "NEUTRAL", "confidence": 0.0}}
    result = _combine_timeframe_beliefs(beliefs)
    assert result["combined_direction"] is None
    assert result["combined_confidence"] == 0.0
    assert result["total_informative"] == 0


def test_combine_empty_beliefs_does_not_crash():
    result = _combine_timeframe_beliefs({})
    assert result["combined_direction"] is None
    assert result["total_informative"] == 0


def test_propose_multi_timeframe_injects_timeframe_belief_before_council(tmp_path):
    """Bütün pipeline: propose_multi_timeframe(), gerçek CognitiveEngine'i
    (embedding dahil) üst zaman dilimleri + birincil için çalıştırıp,
    birincilin relevant_knowledge'ına gerçek bir "timeframe_belief" girişi
    ekliyor mu?"""
    from market_data.ingestion.data_provider import MockProvider
    from services.orchestrator import CognitiveOrchestrator

    # candle_timeframe varsayılanı "15m" — birincil zaman dilimiyle
    # çakışmaması için farklı iki zaman dilimi seçildi (aksi halde
    # propose_multi_timeframe kasıtlı olarak birincili tekrar hesaplamaz,
    # bkz. "if tf == primary_timeframe: continue").
    orch = CognitiveOrchestrator(data_provider=MockProvider(seed=7))
    result = orch.propose_multi_timeframe("BTCUSDT", timeframes=["5m", "1h"])

    assert result is not None
    entries = [
        item for item in result["ctx"].cognition.relevant_knowledge
        if item.get("type") == "timeframe_belief"
    ]
    assert len(entries) == 1
    data = entries[0]["data"]
    assert set(data["per_timeframe"].keys()) == {"5m", "1h"}
    assert "combined_direction" in data


def test_run_portfolio_aware_cycle_uses_multi_timeframe_only_when_enabled():
    """Faz 268c — kullanıcı kararı: raporun TAM versiyonu ama varsayılan
    KAPALI (opt-in, medium_term_enabled ile aynı desen) — açık maliyet
    (sembol başına ~3x CognitiveEngine) sessizce her kuruluma
    dayatılmamalı."""
    from market_data.ingestion.data_provider import MockProvider
    from services.orchestrator import CognitiveOrchestrator

    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(
            "multi_timeframe_cascade_enabled", "false", updated_by="test"
        )

    orch = CognitiveOrchestrator(data_provider=MockProvider(seed=7))
    with patch.object(orch, "propose", wraps=orch.propose) as spy_propose, \
         patch.object(orch, "propose_multi_timeframe", wraps=orch.propose_multi_timeframe) as spy_cascade:
        orch.run_portfolio_aware_cycle(["BTCUSDT"])
        assert spy_propose.called
        assert not spy_cascade.called

    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(
            "multi_timeframe_cascade_enabled", "true", updated_by="test"
        )
    try:
        with patch.object(orch, "propose", wraps=orch.propose) as spy_propose, \
             patch.object(orch, "propose_multi_timeframe", wraps=orch.propose_multi_timeframe) as spy_cascade:
            orch.run_portfolio_aware_cycle(["BTCUSDT"])
            assert spy_cascade.called
            assert not spy_propose.called
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "multi_timeframe_cascade_enabled", "false", updated_by="test"
            )
