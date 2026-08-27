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
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000", "max_portfolio_var_pct": "0.001", "act_threshold": "0.65"}[key]
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
            # Faz 355 — act_threshold kasıtlı olarak çok düşük: bu testin
            # amacı VaR-tabanlı fusion'ı izole test etmek, ENB indiriminin
            # (sadece 2 sembol olduğu için HER ZAMAN tetiklenir, bkz.
            # test_apply_portfolio_fusion_discounts_confidence_when_
            # effective_number_of_bets_is_low) WAIT'e çevirmesini engellemek.
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000000", "max_portfolio_var_pct": "0.5", "act_threshold": "0.01"}[key]
            orch._apply_portfolio_fusion(directional)

        # ENB indirimi (sadece 2 bahis olduğu için) confidence'ı ve final_size'ı
        # meşru şekilde biraz küçültüyor artık (bkz. Faz 355) — bu test'in asıl
        # amacı olan "VaR limiti içindeyken fusion boyutu ÇÖKERTMESİN" hâlâ
        # geçerli: orijinal 0.01'e yakın kalmalı, sıfıra/near-zero'ya değil.
        assert directional["BTCUSDT"]["ctx"].decision.final_size > 0.005
        assert directional["ETHUSDT"]["ctx"].decision.final_size > 0.005


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
            # act_threshold kasıtlı olarak çok düşük: bu testin amacı iki
            # indirimin ZİNCİRLENMESİ, WAIT'e dönme davranışı DEĞİL (o ayrı
            # bir testte, bkz. test_apply_portfolio_fusion_reverts_to_wait_
            # when_discount_drops_below_act_threshold).
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000000", "max_portfolio_var_pct": "0.5", "act_threshold": "0.01"}[key]
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


def test_apply_portfolio_fusion_shrinks_final_size_not_just_confidence():
    """Faz 355 — kritik bulgu: portföy-seviyeli indirim önceden SADECE
    ctx.decision.confidence'ı güncelliyordu, final_size'a hiç dokunmuyordu
    (final_size MetaStage'de TEK seferlik hesaplanıp bir daha yeniden
    türetilmiyordu) — yani indirim gerçek pozisyon boyutunu asla
    küçültmüyordu, sadece explain sayfasındaki sayıyı değiştiriyordu.
    Artık final_size de AYNI oranda küçülüyor."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        base_returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005, 0.008, -0.012, 0.02]
        directional = {
            "BTCUSDT": {
                "ctx": _fake_ctx("BTCUSDT", "LONG", 1.0, confidence=0.8),
                "data": _bars_from_returns(100.0, base_returns), "direction": "LONG",
            },
            "ETHUSDT": {
                "ctx": _fake_ctx("ETHUSDT", "LONG", 1.0, confidence=0.8),
                "data": _bars_from_returns(100.0, [r * 1.01 for r in base_returns]), "direction": "LONG",
            },
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            # Gevşek bir VaR limiti — bu testin amacı VaR-tabanlı fusion
            # değil, confidence indiriminin final_size'a yansıması.
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000000", "max_portfolio_var_pct": "0.5", "act_threshold": "0.01"}[key]
            orch._apply_portfolio_fusion(directional)

        confidence_ratio = directional["BTCUSDT"]["ctx"].decision.confidence / 0.8
        # VaR-tabanlı fusion da boyutu ayrıca küçültebiliyor (aynı fonksiyon
        # ikisini birden yapıyor) — final_size, EN AZINDAN confidence'ın
        # küçüldüğü oran kadar küçülmüş olmalı (VaR fusion'ın kendi payı
        # üstüne binebilir, bu yüzden <= değil sıkı bir eşitlik aranmıyor).
        assert directional["BTCUSDT"]["ctx"].decision.final_size < confidence_ratio + 0.01
        assert directional["BTCUSDT"]["ctx"].decision.final_size < 1.0


def test_apply_portfolio_fusion_reverts_to_wait_when_discount_drops_below_act_threshold():
    """Faz 355 — MetaStage'in ACT kararını verdiği confidence, portföy
    indirimiyle act_threshold'un altına düşerse, karar artık dürüstçe
    WAIT'e çevriliyor (önceden aksiyon hiç yeniden kontrol edilmiyordu —
    "eşiği geçti" kararı eski/yüksek confidence'la kalıcı hale geliyordu)."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        orch = CognitiveOrchestrator()

        base_returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.015, -0.005, 0.008, -0.012, 0.02]
        directional = {
            "BTCUSDT": {
                "ctx": _fake_ctx("BTCUSDT", "LONG", 1.0, confidence=0.8),
                "data": _bars_from_returns(100.0, base_returns), "direction": "LONG",
            },
            "ETHUSDT": {
                "ctx": _fake_ctx("ETHUSDT", "LONG", 1.0, confidence=0.8),
                "data": _bars_from_returns(100.0, [r * 1.01 for r in base_returns]), "direction": "LONG",
            },
        }

        with patch("database.repositories.app_settings_repository.AppSettingsRepository.get") as mock_get:
            # act_threshold'u orijinal confidence'a (0.8) neredeyse eşit
            # tutuyoruz ki EN KÜÇÜK bir indirim bile eşiğin altına düşürsün.
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000000", "max_portfolio_var_pct": "0.5", "act_threshold": "0.79"}[key]
            orch._apply_portfolio_fusion(directional)

        for symbol in ("BTCUSDT", "ETHUSDT"):
            ctx = directional[symbol]["ctx"]
            assert ctx.decision.confidence < 0.79
            assert ctx.decision.action == ActionType.WAIT
            assert ctx.decision.final_size == 0.0
            revert_entries = [
                item["data"] for item in ctx.cognition.relevant_knowledge
                if item.get("type") == "portfolio_confidence_discount"
                and item["data"]["reason"].endswith("_dropped_below_act_threshold")
            ]
            assert len(revert_entries) >= 1


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
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000000", "max_portfolio_var_pct": "0.5", "act_threshold": "0.01"}[key]
            orch._apply_portfolio_fusion(directional)

        # Faz 355 — bu testin asıl amacı same_direction_correlation'ın
        # (korelasyona bakan mekanizma) anti-korele sembollerde tetiklen-
        # MEMESİ; ENB (Effective Number of Bets, korelasyondan bağımsız,
        # SADECE sembol sayısına bakan AYRI bir mekanizma) burada yine de
        # tetiklenebilir (2 bahis her zaman MIN_EFFECTIVE_BETS=3'ün altında)
        # — bu test onu kapsamıyor, bkz. test_apply_portfolio_fusion_
        # discounts_confidence_when_effective_number_of_bets_is_low.
        for symbol in ("BTCUSDT", "ETHUSDT"):
            reasons = [
                item["data"]["reason"]
                for item in directional[symbol]["ctx"].cognition.relevant_knowledge
                if item.get("type") == "portfolio_confidence_discount"
            ]
            assert "same_direction_correlation" not in reasons


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
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000000", "max_portfolio_var_pct": "0.5", "act_threshold": "0.65"}[key]
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
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000000", "max_portfolio_var_pct": "0.5", "act_threshold": "0.65"}[key]
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
            # Faz 355 — act_threshold çok düşük: bu test VaR/birim
            # ölçeklendirmesini izole ediyor, ENB'nin (2 sembol olduğu için
            # her zaman tetiklenen, meşru) confidence indiriminin WAIT'e
            # çevirmesini istemiyoruz.
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000", "max_portfolio_var_pct": "0.5", "act_threshold": "0.01"}[key]
            orch._apply_portfolio_fusion(directional)

        # Gevşek VaR limitinde eski birim hatasındaki gibi ~30'a çökmemeli.
        # Faz 355'ten sonra ENB indirimi miktarı meşru şekilde biraz daha
        # küçültüyor (10000'den ~300-400'e) — asıl korunan şey eski birim
        # hatasının payı (30), o yüzden eşik 5000'den 100'e çekildi.
        assert directional["VETUSDT"]["ctx"].decision.final_size > 100.0
        assert directional["ALGOUSDT"]["ctx"].decision.final_size > 100.0


def test_apply_portfolio_fusion_considers_real_existing_open_positions_not_just_this_cycle():
    """Kullanıcı isteği: "orta-vadeli katmanı portföy VaR'ına dahil et...
    tam birleşik portföy VaR'ı." Öncesinde SADECE bu cycle'daki eşzamanlı
    yeni öneriler kovaryans matrisine giriyordu — saatler önce açılmış
    büyük, korele bir pozisyon (kısa-vadeli VEYA orta-vadeli katmandan,
    ayrım yapılmıyor) hiç görülmüyordu, ve TEK bir yeni öneriyle
    (len(directional)==1) eski kod hiç çalışmıyordu bile. Burada
    GERÇEKTEN açık, çok büyük ve yeni öneriyle MÜKEMMEL korele bir
    pozisyon var — tek başına yeni öneri bunu görüp küçülmeli."""
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
            mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false", "starting_capital": "1000", "max_portfolio_var_pct": "0.001", "act_threshold": "0.65"}[key]
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
                #
                # Faz 363 — kritik bulgu: bu test finalize_proposal() üzerinden
                # gerçekten record_stage.execute() -> decision_recorder.record()
                # kadar gidiyor, o da (Faz 361/362'de eklenen) signal_
                # persistence_gate_enabled/pyramid_regime_gate_enabled gibi
                # ayarları okuyor. Sabit bir dict'in exact-match [key] araması
                # (KeyError fırlatan) HER yeni ayar eklendiğinde bu testi
                # kırıyordu — DEFAULTS'a düşen bir fallback'e çevrildi, ileride
                # eklenecek ayarlar bu testi bir daha kırmasın diye.
                from database.repositories.app_settings_repository import DEFAULTS

                overrides = {
                    "max_confidence_mode_enabled": "false",
                    "starting_capital": "1000",
                    "max_portfolio_var_pct": "0.001",
                    "multi_timeframe_cascade_enabled": "false",
                    "multi_timeframe_cascade_ab_test_enabled": "false",
                    "act_threshold": "0.65",
                }
                mock_get.side_effect = lambda key: overrides.get(key, DEFAULTS.get(key))
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
                    mock_get.side_effect = lambda key: {"max_confidence_mode_enabled": "false",
                        "starting_capital": "1000",
                        "max_portfolio_var_pct": "0.5",
                        "multi_timeframe_cascade_enabled": "false",
                        "multi_timeframe_cascade_ab_test_enabled": "true",
                        "act_threshold": "0.65",
                        # Faz 367 — decision_recorder.py'nin finalize_proposal
                        # yolunda okuduğu yeni asset-class/rejim aç-kapa
                        # ayarları; test hiçbir sınıfı/rejimi kapatmıyor.
                        "asset_class_trading_enabled": '{"crypto": true, "commodity": true, "equity": true}',
                        "regime_trading_enabled": (
                            '{"bullish_high": true, "bullish_normal": true, "bullish_low": true, '
                            '"bearish_high": true, "bearish_normal": true, "bearish_low": true}'
                        ),
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
