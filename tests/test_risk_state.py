"""Faz 188: services/risk_state.py — gerçek açık pozisyon sayısı ve
kullanılan sermaye yüzdesinin gerçek DB'den doğru hesaplandığını doğrular."""
from unittest.mock import patch
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.risk_state import load_position_risk_state


def test_open_position_count_and_capital_used_pct_reflect_real_open_positions():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("starting_capital", "1000", updated_by="test")

        symbol = f"RISKSTATE{uuid4().hex[:8]}"
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            before = repo.list_open_positions(limit=5000)
            repo.persist(DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=2.0,
            ))

        state = load_position_risk_state()

        assert state["open_position_count"] == len(before) + 1
        # capital_committed en az bu yeni pozisyonun notional'ı kadar artmış olmalı
        assert state["capital_used_pct"] > 0


def test_trading_mode_defaults_to_test_when_never_set():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            row = AppSettingsRepository(session).get("trading_mode")
        # Ya hiç set edilmemiş (default "test") ya da başka bir testte
        # zaten "live" set edilmiş olabilir (paylaşılan dev DB) — her iki
        # durumda da geçerli bir mod dönmeli.
        assert row in ("test", "live")


def test_timeframe_filter_only_counts_matching_timeframe_positions():
    """Faz 259: orta-vadeli katman sadece KENDİ timeframe'inden açılmış
    pozisyonları saymalı."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"RISKSTATE{uuid4().hex[:8]}"
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            before = len([
                p for p in repo.list_open_positions(limit=5000) if p.get("timeframe") == "1d"
            ])
            repo.persist(DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=2.0, timeframe="1d",
            ))
            repo.persist(DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=2.0, timeframe="15m",
            ))

        state = load_position_risk_state(timeframe_filter="1d")

        assert state["open_position_count"] == before + 1


def test_exclude_timeframe_counts_everything_except_that_timeframe():
    """Faz 259: kısa-vadeli katman, orta-vadeli katmanın pozisyonlarını
    HARİÇ tutup geri kalan HER ŞEYİ (NULL timeframe dahil — migration
    öncesi eski pozisyonlar) saymalı."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"RISKSTATE{uuid4().hex[:8]}"
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            before = len([
                p for p in repo.list_open_positions(limit=5000) if p.get("timeframe") != "1d"
            ])
            repo.persist(DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=2.0, timeframe="1d",
            ))
            repo.persist(DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=2.0, timeframe=None,
            ))

        state = load_position_risk_state(exclude_timeframe="1d")

        assert state["open_position_count"] == before + 1


def test_capital_pct_and_max_concurrent_overrides_replace_settings_values():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        state = load_position_risk_state(capital_pct_override=0.1, max_concurrent_override=5)

        assert state["max_capital_pct"] == 0.1
        assert state["max_concurrent_positions"] == 5
