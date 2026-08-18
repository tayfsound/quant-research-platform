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

        # Kullanıcı bulgusu: explain sayfası "%74 güvenli bir ajan varken
        # nihai karar neden %28 çıktı" sorusuna cevap veremiyordu — bu
        # indirim(ler) artık relevant_knowledge'a (ve oradan agent_
        # contributions'a) neden/öncesi/sonrasıyla kaydediliyor. Bu
        # senaryoda 2 sembol hem yüksek korele HEM de (sadece 2 bahis
        # olduğu için) düşük ENB'li — ikisi de tetiklenip zincirleniyor.
        btc_discounts = [
            item["data"] for item in directional["BTCUSDT"]["ctx"].cognition.relevant_knowledge
            if item.get("type") == "portfolio_confidence_discount"
        ]
        assert len(btc_discounts) == 2
        assert btc_discounts[0]["reason"] == "same_direction_correlation"
        assert btc_discounts[0]["confidence_before"] == 0.8
        assert btc_discounts[1]["reason"] == "low_effective_number_of_bets"
        assert btc_discounts[1]["confidence_after"] == directional["BTCUSDT"]["ctx"].decision.confidence


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


def test_apply_portfolio_fusion_discounts_confidence_when_effective_number_of_bets_is_low():
    """Faz 268-sonrası — Effective Number of Bets (Cognitive Core 2.0/M6):
    Cross-Symbol Correlation Filter'ın aksine (tek sembol çiftine bakar),
    ENB PORTFÖYÜN GENELİNİ ölçer. Buradaki iki sembol birbirine düşük
    korele (Cross-Symbol filtresi TETİKLENMEZ — max_corr <= 0.7 eşiğinin
    altında kalacak şekilde seçildi) ama ENB doğrudan mock'lanarak düşük
    (1.0 < MIN_EFFECTIVE_BETS=3.0) döndürülüyor — bu SADECE ENB katmanının
    kendi indirimini izole test eder."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        base_returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005, 0.008, -0.012, 0.02]
        low_corr_returns = [0.01, 0.02, -0.03, 0.015, -0.01, -0.005, 0.02, -0.008, 0.012, -0.02]
        directional = {
            "BTCUSDT": {
                "ctx": _fake_ctx("BTCUSDT", "LONG", 0.01, confidence=0.8),
                "data": _bars_from_returns(100.0, base_returns), "direction": "LONG",
            },
            "ETHUSDT": {
                "ctx": _fake_ctx("ETHUSDT", "LONG", 0.01, confidence=0.8),
                "data": _bars_from_returns(100.0, low_corr_returns), "direction": "LONG",
            },
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            mock_get.side_effect = lambda key: {"starting_capital": "1000000", "max_portfolio_var_pct": "0.5"}[key]
            with patch(
                "analytics.portfolio_intelligence.compute_effective_number_of_bets",
                return_value={"effective_number_of_bets": 1.0, "position_count": 2, "diversification_ratio": 0.5},
            ):
                orch._apply_portfolio_fusion(directional)

        assert directional["BTCUSDT"]["ctx"].decision.confidence < 0.8
        assert directional["ETHUSDT"]["ctx"].decision.confidence < 0.8


def test_apply_portfolio_fusion_does_not_discount_confidence_when_effective_number_of_bets_is_sufficient():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        base_returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005, 0.008, -0.012, 0.02]
        low_corr_returns = [0.01, 0.02, -0.03, 0.015, -0.01, -0.005, 0.02, -0.008, 0.012, -0.02]
        directional = {
            "BTCUSDT": {
                "ctx": _fake_ctx("BTCUSDT", "LONG", 0.01, confidence=0.8),
                "data": _bars_from_returns(100.0, base_returns), "direction": "LONG",
            },
            "ETHUSDT": {
                "ctx": _fake_ctx("ETHUSDT", "LONG", 0.01, confidence=0.8),
                "data": _bars_from_returns(100.0, low_corr_returns), "direction": "LONG",
            },
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            mock_get.side_effect = lambda key: {"starting_capital": "1000000", "max_portfolio_var_pct": "0.5"}[key]
            with patch(
                "analytics.portfolio_intelligence.compute_effective_number_of_bets",
                return_value={"effective_number_of_bets": 5.0, "position_count": 2, "diversification_ratio": 2.5},
            ):
                orch._apply_portfolio_fusion(directional)

        assert directional["BTCUSDT"]["ctx"].decision.confidence == 0.8
        assert directional["ETHUSDT"]["ctx"].decision.confidence == 0.8


def test_apply_portfolio_fusion_does_not_collapse_realistic_quantities_to_near_zero():
    """Gerçek canlı bulgu (2026-08-18): final_size bu noktada base-varlık
    MİKTARI (örn. 10000 VET), ama PortfolioFusionStage.fuse() proposed_
    sizes'ı "portföy değerinin fraksiyonu" (0-1 ağırlık) olarak bekliyor.
    Miktarı doğrudan ağırlık gibi weights@cov@weights VaR hesabına sokmak
    (eski davranış) portfolio_var'ı gerçek dışı şişiriyordu (örn. 10000
    büyüklüğünde bir "ağırlık" tek başına VaR limitini binlerce kat aşar),
    scale-down çarpanı neredeyse sıfıra çöküyor ve GERÇEK açık
    pozisyonlarda notional $0.01-$0.20 arasına düşüyordu (olması gereken
    ~$50 yerine). Ucuz bir sembol (fiyat ~0.005, VET'e benzer) ve makul
    bir sermaye/limit ile: gevşek bir VaR limitinde bu miktarlar
    KIRPILMAMALI."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        directional = {
            "VETUSDT": {
                "ctx": _fake_ctx("VETUSDT", "LONG", 10000.0),
                "data": _correlated_bars(base=0.005, seed=1), "direction": "LONG",
            },
            "ALGOUSDT": {
                "ctx": _fake_ctx("ALGOUSDT", "SHORT", 10000.0),
                "data": _correlated_bars(base=0.005, seed=2), "direction": "SHORT",
            },
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            mock_get.side_effect = lambda key: {"starting_capital": "1000", "max_portfolio_var_pct": "0.5"}[key]
            orch._apply_portfolio_fusion(directional)

        # Gevşek limitte hiç ölçeklenmemeli — miktar 10000'e yakın kalmalı,
        # eski birim hatasındaki gibi ~30'a çökmemeli.
        assert directional["VETUSDT"]["ctx"].decision.final_size > 5000.0
        assert directional["ALGOUSDT"]["ctx"].decision.final_size > 5000.0


def test_apply_portfolio_fusion_considers_real_existing_open_positions_not_just_this_cycle():
    """Kullanıcı isteği: "orta-vadeli katmanı portföy VaR'ına dahil et...
    tam birleşik portföy VaR'ı." Öncesinde SADECE bu cycle'daki eşzamanlı
    yeni öneriler kovaryans matrisine giriyordu — saatler önce açılmış
    büyük, korele bir pozisyon (kısa-vadeli VEYA orta-vadeli katmandan,
    ayrım yapılmıyor) hiç görülmüyordu, ve TEK bir yeni öneriyle
    (len(directional)==1) eski kod hiç çalışmıyordu bile. Burada
    GERÇEKTEN açık, çok büyük ve yeni öneriyle MÜKEMMEL korele bir
    pozisyon var — tek başına yeni öneri bunu görüp küçülmeli."""
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        existing_symbol = f"EXISTFUSE{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        with SessionFactory.get_session() as session:
            DecisionPersistor(session).persist(DecisionEvent(
                id=uuid4(), timestamp=now, symbol=existing_symbol,
                proposed_direction="LONG", final_action="LONG", final_size=1000.0, confidence=0.7,
                status="open", entry_price=100.0, quantity=1000.0, opened_at=now,
            ))

        new_symbol = f"NEWFUSE{uuid4().hex[:8]}"
        bars = _correlated_bars(seed=7)
        directional = {
            new_symbol: {"ctx": _fake_ctx(new_symbol, "LONG", 1.0), "data": bars, "direction": "LONG"},
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            # Küçük bir kasa (1000) + çok büyük mevcut pozisyon (notional
            # 100.000, kasanın 100 katı) — tek başına bile VaR'ı çok
            # aşar; aynı yönde/mükemmel korele yeni öneri bunu ARTIRIR.
            mock_get.side_effect = lambda key: {"starting_capital": "1000", "max_portfolio_var_pct": "0.001"}[key]
            with patch.object(orch.data_provider, "get_ohlcv", return_value=bars):
                orch._apply_portfolio_fusion(directional)

        # Eski kodda len(directional)==1 olduğu için fusion hiç
        # çalışmazdı, final_size hep 1.0 kalırdı. Artık gerçek açık
        # pozisyonla birlikte değerlendirilip küçülmüş olmalı.
        assert directional[new_symbol]["ctx"].decision.final_size < 1.0


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
