"""Faz 199: kritik bulgu — services/portfolio_fusion.py + risk/limits/
portfolio.py (gerçek kovaryans/VaR motoru) yazılmış, test edilmişti ama
hiçbir yerden çağrılmıyordu. CognitiveOrchestrator.run_portfolio_aware_cycle
bunu gerçekten bağlıyor: 2+ sembol eşzamanlı yönlü öneri üretirse,
GERÇEKTEN açılmadan önce portföy VaR'ına göre ölçeklendiriliyor."""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from market_data.ingestion.ohlcv import OHLCV
from services.orchestrator import CognitiveOrchestrator


def _correlated_bars(n=30, base=100.0, seed=1):
    import random
    rng = random.Random(seed)
    bars = []
    price = base
    now = datetime.now(UTC)
    for i in range(n):
        price += rng.gauss(0, base * 0.01)
        bars.append(OHLCV(
            timestamp=now - timedelta(minutes=n - i),
            open=price, high=price * 1.001, low=price * 0.999, close=price, volume=100.0,
        ))
    return bars


def _fake_ctx(symbol: str, direction: str, size: float) -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.decision.proposed_direction = direction
    ctx.decision.final_size = size
    ctx.decision.action = ActionType.ENTER_LONG if direction == "LONG" else ActionType.ENTER_SHORT
    ctx.decision.filled_price = 100.0
    ctx.risk.evaluation.verdict = "approved"
    return ctx


def test_apply_portfolio_fusion_scales_down_when_var_exceeds_limit():
    """Aynı yöne (LONG+LONG, pozitif korelasyon) giren iki büyük pozisyon,
    düşük bir max_var ile gerçekten küçültülmeli."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        directional = {
            "BTCUSDT": {"ctx": _fake_ctx("BTCUSDT", "LONG", 1.0), "data": _correlated_bars(seed=1), "direction": "LONG"},
            "ETHUSDT": {"ctx": _fake_ctx("ETHUSDT", "LONG", 1.0), "data": _correlated_bars(seed=2), "direction": "LONG"},
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            mock_get.side_effect = lambda key: {"starting_capital": "1000", "max_portfolio_var_pct": "0.001"}[key]
            orch._apply_portfolio_fusion(directional)

        # Ölçeklendirme sonrası büyüklükler orijinal 1.0'dan küçük olmalı.
        assert abs(directional["BTCUSDT"]["ctx"].decision.final_size) < 1.0
        assert abs(directional["ETHUSDT"]["ctx"].decision.final_size) < 1.0


def test_apply_portfolio_fusion_leaves_sizes_unchanged_when_within_var_limit():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        directional = {
            "BTCUSDT": {"ctx": _fake_ctx("BTCUSDT", "LONG", 0.01), "data": _correlated_bars(seed=1), "direction": "LONG"},
            "ETHUSDT": {"ctx": _fake_ctx("ETHUSDT", "SHORT", 0.01), "data": _correlated_bars(seed=2), "direction": "SHORT"},
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            mock_get.side_effect = lambda key: {"starting_capital": "1000000", "max_portfolio_var_pct": "0.5"}[key]
            orch._apply_portfolio_fusion(directional)

        assert directional["BTCUSDT"]["ctx"].decision.final_size == 0.01
        assert directional["ETHUSDT"]["ctx"].decision.final_size == 0.01


def test_run_portfolio_aware_cycle_finalizes_every_symbol_and_applies_fusion_when_multiple_directional():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        proposals = {
            "BTCUSDT": {"ctx": _fake_ctx("BTCUSDT", "LONG", 1.0), "data": _correlated_bars(seed=1), "fee": 0.0, "direction": "LONG"},
            "ETHUSDT": {"ctx": _fake_ctx("ETHUSDT", "LONG", 1.0), "data": _correlated_bars(seed=2), "fee": 0.0, "direction": "LONG"},
        }

        with patch.object(orch, "propose", side_effect=lambda sym: proposals.get(sym)):
            with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
                mock_get.side_effect = lambda key: {"starting_capital": "1000", "max_portfolio_var_pct": "0.001"}[key]
                results = orch.run_portfolio_aware_cycle(["BTCUSDT", "ETHUSDT"])

        assert len(results) == 2
        symbols = {r["symbol"] for r in results}
        assert symbols == {"BTCUSDT", "ETHUSDT"}
        # Fusion gerçekten ölçeklendirdiyse, kaydedilen size 1.0'dan küçük olmalı.
        for r in results:
            assert r["size"] < 1.0
