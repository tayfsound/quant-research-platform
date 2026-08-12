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


def _fake_ctx(symbol: str, direction: str, size: float, confidence: float = 0.7) -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.decision.proposed_direction = direction
    ctx.decision.final_size = size
    ctx.decision.confidence = confidence
    ctx.decision.action = ActionType.ENTER_LONG if direction == "LONG" else ActionType.ENTER_SHORT
    ctx.decision.filled_price = 100.0
    ctx.risk.evaluation.verdict = "approved"
    return ctx


def _bars_from_returns(base: float, returns: list[float]) -> list:
    """_correlated_bars'ın aksine (bağımsız rastgele yürüyüşler, gerçekte
    birbirine korele DEĞİL), belirli bir getiri dizisinden GERÇEKTEN
    korele/anti-korele barlar üretir — Cross-Symbol Correlation Filter
    testleri gerçek bir yüksek korelasyon senaryosu gerektiriyor."""
    now = datetime.now(UTC)
    n = len(returns) + 1
    price = base
    bars = [OHLCV(
        timestamp=now - timedelta(minutes=n), open=price, high=price * 1.001,
        low=price * 0.999, close=price, volume=100.0,
    )]
    for i, r in enumerate(returns):
        price = price * (1 + r)
        bars.append(OHLCV(
            timestamp=now - timedelta(minutes=n - i - 1), open=price, high=price * 1.001,
            low=price * 0.999, close=price, volume=100.0,
        ))
    return bars


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


def test_apply_portfolio_fusion_discounts_confidence_for_highly_correlated_same_direction_symbols():
    """Faz 268-sonrası — Cross-Symbol Correlation Filter: VaR tabanlı
    fusion pozisyon büyüklüğünü küçültür, ama council'in kendi
    conviction'ı (confidence) da gerçekten indirime uğramalı — 2 sembol
    aynı anda aynı yönde, birbirine neredeyse özdeş (yüksek korele)
    hareket ediyorsa, bunlar bağımsız kanıt değil aynı riskin yansıması."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        base_returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005, 0.008, -0.012, 0.02]
        directional = {
            "BTCUSDT": {
                "ctx": _fake_ctx("BTCUSDT", "LONG", 0.01, confidence=0.8),
                "data": _bars_from_returns(100.0, base_returns), "direction": "LONG",
            },
            "ETHUSDT": {
                "ctx": _fake_ctx("ETHUSDT", "LONG", 0.01, confidence=0.8),
                "data": _bars_from_returns(100.0, [r * 1.01 for r in base_returns]), "direction": "LONG",
            },
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            # Gevşek bir VaR limiti — bu testin amacı boyut değil confidence.
            mock_get.side_effect = lambda key: {"starting_capital": "1000000", "max_portfolio_var_pct": "0.5"}[key]
            orch._apply_portfolio_fusion(directional)

        assert directional["BTCUSDT"]["ctx"].decision.confidence < 0.8
        assert directional["ETHUSDT"]["ctx"].decision.confidence < 0.8


def test_apply_portfolio_fusion_does_not_discount_confidence_for_uncorrelated_symbols():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        base_returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005, 0.008, -0.012, 0.02]
        anti_correlated = [-r for r in base_returns]
        directional = {
            "BTCUSDT": {
                "ctx": _fake_ctx("BTCUSDT", "LONG", 0.01, confidence=0.8),
                "data": _bars_from_returns(100.0, base_returns), "direction": "LONG",
            },
            "ETHUSDT": {
                "ctx": _fake_ctx("ETHUSDT", "LONG", 0.01, confidence=0.8),
                "data": _bars_from_returns(100.0, anti_correlated), "direction": "LONG",
            },
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            mock_get.side_effect = lambda key: {"starting_capital": "1000000", "max_portfolio_var_pct": "0.5"}[key]
            orch._apply_portfolio_fusion(directional)

        assert directional["BTCUSDT"]["ctx"].decision.confidence == 0.8
        assert directional["ETHUSDT"]["ctx"].decision.confidence == 0.8


def test_run_portfolio_aware_cycle_finalizes_every_symbol_and_applies_fusion_when_multiple_directional():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        proposals = {
            "BTCUSDT": {"ctx": _fake_ctx("BTCUSDT", "LONG", 1.0), "data": _correlated_bars(seed=1), "fee": 0.0, "direction": "LONG"},
            "ETHUSDT": {"ctx": _fake_ctx("ETHUSDT", "LONG", 1.0), "data": _correlated_bars(seed=2), "fee": 0.0, "direction": "LONG"},
        }

        with patch.object(orch, "propose", side_effect=lambda sym: proposals.get(sym)):
            with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
                # Faz 268c: run_portfolio_aware_cycle() artık başta ayrıca
                # multi_timeframe_cascade_enabled'ı da okuyor (varsayılan
                # "false" — propose() kullanılmaya devam etmeli, bu testin
                # zaten mockladığı yol).
                mock_get.side_effect = lambda key: {
                    "starting_capital": "1000",
                    "max_portfolio_var_pct": "0.001",
                    "multi_timeframe_cascade_enabled": "false",
                    "multi_timeframe_cascade_ab_test_enabled": "false",
                }[key]
                results = orch.run_portfolio_aware_cycle(["BTCUSDT", "ETHUSDT"])

        assert len(results) == 2
        symbols = {r["symbol"] for r in results}
        assert symbols == {"BTCUSDT", "ETHUSDT"}
        # Fusion gerçekten ölçeklendirdiyse, kaydedilen size 1.0'dan küçük olmalı.
        for r in results:
            assert r["size"] < 1.0


def test_run_portfolio_aware_cycle_tags_experiment_bucket_when_ab_test_enabled():
    """Faz 250: multi_timeframe_cascade_ab_test_enabled açıkken, statik
    cascade ayarı yerine her sembol bağımsız rastgele bir kovaya atanmalı
    ve ctx.cognition.relevant_knowledge'a experiment_bucket etiketi
    eklenmeli (RecordingStage'in okuyup decisions.experiment_bucket'a
    yazdığı AYNI mekanizma)."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        proposals = {
            "BTCUSDT": {"ctx": _fake_ctx("BTCUSDT", "LONG", 1.0), "data": _correlated_bars(seed=1), "fee": 0.0, "direction": "LONG"},
        }

        with patch.object(orch, "propose", side_effect=lambda sym: proposals.get(sym)):
            with patch.object(orch, "propose_multi_timeframe", side_effect=lambda sym: proposals.get(sym)):
                with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
                    mock_get.side_effect = lambda key: {
                        "starting_capital": "1000",
                        "max_portfolio_var_pct": "0.5",
                        "multi_timeframe_cascade_enabled": "false",
                        "multi_timeframe_cascade_ab_test_enabled": "true",
                    }[key]
                    with patch("services.ab_testing.assign_bucket", return_value="treatment"):
                        orch.run_portfolio_aware_cycle(["BTCUSDT"])

        ctx = proposals["BTCUSDT"]["ctx"]
        entries = [
            item for item in ctx.cognition.relevant_knowledge
            if item.get("type") == "experiment_bucket"
        ]
        assert len(entries) == 1
        assert entries[0]["data"]["bucket"] == "multi_timeframe_cascade_v1:treatment"
