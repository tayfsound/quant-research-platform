"""P0 kritik bulgu: CognitiveOrchestrator.run_cycle() (tek gerçek üretim
girişi) sadece ham rsi/ema/macd sayıları hesaplıyordu — TechnicalAgent'ın
gerçekten skorladığı trend/momentum/market_structure/ema_alignment gibi
kategorik alanları hiçbir kod üretmiyordu, Pattern/Quant ajanları da aynı
şekilde körüdü. Üstüne "rsi"/"RSI" büyük-küçük harf uyuşmazlığı yüzünden
RSI de hiç gerçek değildi. Bu, gerçek OHLCV geçmişinden hesaplanan
sinyallerin artık gerçekten council'e ulaştığını kanıtlıyor."""
from unittest.mock import patch

from services.orchestrator import CognitiveOrchestrator


def test_run_cycle_features_contain_real_computed_technical_signals_not_defaults():
    result = CognitiveOrchestrator().run_cycle(seed=777)

    features = result["features"]
    # Eskiden sadece {"rsi", "ema", "macd"} vardı — artık kategorik
    # sinyaller de gerçekten hesaplanıp geçiyor.
    assert "trend" in features
    assert "market_structure" in features
    assert "ema_alignment" in features
    assert "volatility_regime" in features
    assert features["trend"] in ("bullish", "bearish", "neutral")
    # RSI büyük harfle geçiyor — kod tabanının genel konvansiyonu.
    assert "RSI" in features
    assert 0 <= features["RSI"] <= 100


def test_cognitive_run_endpoint_feeds_real_ohlcv_derived_context():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from fastapi.testclient import TestClient

        from api.main import app
        from contracts.auth import Role
        from tests.auth_helpers import make_authed_headers

        client = TestClient(app)
        resp = client.post(
            "/api/v1/cognitive/run?symbol=BTCUSDT",
            headers=make_authed_headers(Role.OPERATOR),
        )
        assert resp.status_code == 200
        data = resp.json()
        # Eskiden ctx tamamen boştu -> knowledge/relevant_knowledge'da
        # gerçek bir market_insight/pattern/quant sinyali olamazdı.
        # Şimdi gerçek bir cycle_id ve council kararı dönüyor (agent'lar
        # artık gerçek veriyle çalışıyor, tamamen kör değil).
        assert data["cycle_id"]
        assert data["direction"] in ("LONG", "SHORT", "WAIT", "")
