"""Faz 259: kullanıcı isteği — orta-vadeli pozisyon katmanı (ayrı günlük/4h
sinyal, ayrı sermaye havuzu, kısa-vadeli katmandan bağımsız). Kısa-vadeli
katmanı hiç etkilemediğini (varsayılan devre dışı) ve devredeyken kendi
timeframe/sermaye ayarlarını gerçekten kullandığını doğrular."""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import numpy as np

from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.orchestrator import CognitiveOrchestrator


class _FakeProvider:
    def __init__(self, bars: list):
        self.bars = bars

    def get_ohlcv(self, symbol, timeframe, limit=100):
        return self.bars[-limit:]


def _real_looking_bars(n=60, seed=7):
    rng = np.random.RandomState(seed)
    prices = np.cumsum(rng.normal(0, 2.0, n)) + 100
    prices = np.abs(prices) + 50
    now = datetime.now(UTC)
    return [
        OHLCV(
            timestamp=now - timedelta(days=n - i),
            open=v, high=v * 1.01, low=v * 0.99, close=v, volume=1000.0,
        )
        for i, v in enumerate(prices)
    ]


def test_medium_term_disabled_by_default_returns_none():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"MEDTERM{uuid4().hex[:6]}USDT"
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("medium_term_enabled", "false", updated_by="test")

        orch = CognitiveOrchestrator(data_provider=_FakeProvider(_real_looking_bars()))
        result = orch.propose_medium_term(symbol)

        assert result is None


def test_medium_term_enabled_uses_its_own_timeframe_and_capital_settings():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"MEDTERM{uuid4().hex[:6]}USDT"
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            repo.set("medium_term_enabled", "true", updated_by="test")
            repo.set("medium_term_timeframe", "1d", updated_by="test")
            repo.set("medium_term_capital_pct", "0.1", updated_by="test")
            repo.set("medium_term_max_concurrent", "5", updated_by="test")

        try:
            orch = CognitiveOrchestrator(data_provider=_FakeProvider(_real_looking_bars()))
            result = orch.propose_medium_term(symbol)

            assert result is not None
            ctx = result["ctx"]
            assert ctx.market.timeframe == "1d"
            # Faz 259: kısa-vadelinin max_capital_pct'inden (varsayılan 0.4)
            # bağımsız, kendi %10'luk havuzunu kullanmalı.
            assert ctx.risk.max_capital_pct == 0.1
            assert ctx.risk.max_concurrent_positions == 5
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set("medium_term_enabled", "false", updated_by="test")


def test_run_medium_term_cycle_now_applies_portfolio_fusion():
    """Faz 268-sonrası — kullanıcı isteği: "orta-vadeli katmanı portföy
    VaR'ına dahil et... tam birleşik portföy VaR'ı." Önceden bu
    metodun kendi docstring'i "portföy VaR füzyonu kasıtlı olarak
    burada YOK" diyordu — artık kısa-vadeli katmanla AYNI _apply_
    portfolio_fusion çağrılıyor, gerçek yönlü bir öneri üretildiğinde."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"MEDTERM{uuid4().hex[:6]}USDT"
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            repo.set("medium_term_enabled", "true", updated_by="test")
            repo.set("medium_term_timeframe", "1d", updated_by="test")

        try:
            orch = CognitiveOrchestrator(data_provider=_FakeProvider(_real_looking_bars()))
            with patch.object(orch, "_apply_portfolio_fusion") as mock_fusion, \
                    patch.object(orch, "propose_medium_term") as mock_propose, \
                    patch.object(orch, "finalize_proposal", return_value={"symbol": symbol, "direction": "LONG"}):
                from contracts.context import CognitiveCycleContext
                from contracts.contexts.decision import ActionType

                ctx = CognitiveCycleContext()
                ctx.decision.proposed_direction = "LONG"
                ctx.decision.final_size = 1.0
                ctx.decision.action = ActionType.ENTER_LONG
                mock_propose.return_value = {"ctx": ctx, "data": _real_looking_bars(), "direction": "LONG", "fee": 0.0}

                orch.run_medium_term_cycle([symbol])

            mock_fusion.assert_called_once()
            called_directional = mock_fusion.call_args[0][0]
            assert symbol in called_directional
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set("medium_term_enabled", "false", updated_by="test")


def test_run_medium_term_cycle_skips_symbols_with_no_data():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("medium_term_enabled", "true", updated_by="test")

        try:
            orch = CognitiveOrchestrator(data_provider=_FakeProvider([]))
            results = orch.run_medium_term_cycle(["NODATAUSDT"])

            assert len(results) == 1
            assert results[0]["direction"] == "NEUTRAL"
            assert results[0]["error"] == "no_data_or_disabled"
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set("medium_term_enabled", "false", updated_by="test")
