"""Faz 264: kullanıcı isteği — ajan içi özellik ağırlıklarının (RSI/trend/
momentum vb.) gerçek sonuçlardan, kayan pencereyle periyodik öğrenilmesi.
Ajanın kendi yön/skor mantığı değişmiyor, sadece confidence'ı gerçek
doğruluğa göre kalibre ediliyor — model yoksa/yetersizse çarpan 1.0
(fail-closed, asla icat edilmiş bir ayar uygulanmaz)."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.agent_confidence_model import AgentConfidenceModel
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.agent_confidence_model import (
    ConfidenceModelRepository,
    _vectorize,
    predict_confidence_multiplier,
    train_confidence_model,
)


def test_no_saved_model_returns_neutral_multiplier(tmp_path):
    repo = ConfidenceModelRepository(storage_path=str(tmp_path / "confidence_models"))
    multiplier = predict_confidence_multiplier("technical", {"rsi_value": 90.0}, repository=repo)
    assert multiplier == 1.0


def test_vectorize_encodes_numeric_boolean_and_onehot_categorical_correctly():
    schema = {
        "numeric": ["rsi_value"],
        "boolean": ["volume_confirmation"],
        "categorical": ["trend"],
    }
    categorical_values = {"trend": ["bearish", "bullish"]}

    X = _vectorize(
        [{"rsi_value": 80.0, "volume_confirmation": True, "trend": "bullish"}],
        schema,
        categorical_values,
    )

    assert X.shape == (1, 4)  # rsi + vol_confirm + 2 trend one-hot kolonu
    assert X[0].tolist() == [80.0, 1.0, 0.0, 1.0]  # rsi, vol_confirm, trend=bearish, trend=bullish


def test_predict_confidence_multiplier_scales_by_p_correct_over_baseline(tmp_path):
    """Elle kurulmuş, tahmin edilebilir bir model: yüksek RSI -> yüksek
    P(doğru) tahmin etsin, taban oranın üstünde bir çarpan üretsin."""
    repo = ConfidenceModelRepository(storage_path=str(tmp_path / "confidence_models"))
    model = AgentConfidenceModel(
        domain="technical",
        window_size=100,
        sample_count=100,
        numeric_features=["rsi_value"],
        boolean_features=[],
        categorical_features={},
        scaler_mean=[50.0],
        scaler_scale=[10.0],
        coefficients=[1.0],  # rsi arttikca P(dogru) artar
        intercept=0.0,
        baseline_correctness_rate=0.5,
        train_accuracy=0.6,
        test_accuracy=0.6,
    )
    repo.save(model)

    high_rsi_multiplier = predict_confidence_multiplier("technical", {"rsi_value": 90.0}, repository=repo)
    low_rsi_multiplier = predict_confidence_multiplier("technical", {"rsi_value": 10.0}, repository=repo)

    assert high_rsi_multiplier > 1.0
    assert low_rsi_multiplier < 1.0
    # Sınırlı olmalı (0.5-1.5 arası, agent_confidence_model.py'deki sınır)
    assert 0.5 <= high_rsi_multiplier <= 1.5
    assert 0.5 <= low_rsi_multiplier <= 1.5


def _persist_closed_decision(symbol: str, technical_direction: str, executed_direction: str,
                              pnl: float, features: dict, closed_at: datetime) -> None:
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(),
            symbol=symbol,
            proposed_direction=executed_direction,
            final_action=executed_direction,
            final_size=0.1,
            confidence=0.5,
            status="open",
            entry_price=100.0,
            quantity=1.0,
            opened_at=closed_at - timedelta(minutes=10),
            agent_opinions=[
                {"domain": "technical", "direction": technical_direction, "confidence": 0.6},
            ],
            market_snapshot={"features": features},
        )
        persistor.persist(event)
        persistor.close_position(
            decision_id=str(event.id),
            exit_price=101.0 if pnl > 0 else 99.0,
            pnl=pnl,
            closed_at=closed_at,
        )


def test_train_confidence_model_learns_a_real_pattern_from_fresh_window_dominated_data():
    """Gerçek bulgu: _extract_training_rows sembole göre filtrelemiyor,
    tüm decisions tablosundan son `window` kapanmış işlemi çekiyor —
    paylaşılan test DB'sinde kirlenme riski var. Bu test, window'u
    kendi taze verisiyle TAMAMEN doldurup (en yeni closed_at'e sahip
    olduğu için ORDER BY ... DESC LIMIT window bunları öne alır) eski
    veriden bağımsız, kendi kendine yeterli hale getiriliyor.

    Gerçek bulgu (2. tur): tam test paketi ~5 dakika sürüyor — aradan
    geçen gerçek zamanda BAŞKA testler de "technical" domain'inde taze
    (datetime.now(UTC)) kayıtlar ekleyebiliyor, bunlar benim
    base_time=now() anlık görüntümden DAHA YENİ olup pencereden benim
    verimi dışarı itebiliyordu (izole çalıştırınca geçiyordu, tam
    pakette flaky çıktı). Gelecekteki bir zaman damgası kullanmak,
    hiçbir eşzamanlı/sıralı testin gerçek datetime.now()'ının bunu asla
    geçemeyeceğini garanti ediyor."""
    window = 120
    base_time = datetime.now(UTC) + timedelta(days=3650)
    symbol = f"CONFMODEL{uuid4().hex[:8]}"

    # Yuksek RSI'da technical_agent'in yonu HEP dogru cikiyor (executed'la
    # ayni), dusuk RSI'da HEP yanlis - ogrenilebilir, net bir orunte.
    for i in range(window // 2):
        _persist_closed_decision(
            symbol, technical_direction="LONG", executed_direction="LONG",
            pnl=10.0, features={"RSI": 85.0, "trend": "bullish"},
            closed_at=base_time - timedelta(seconds=i),
        )
    for i in range(window // 2):
        _persist_closed_decision(
            symbol, technical_direction="LONG", executed_direction="SHORT",
            pnl=10.0, features={"RSI": 15.0, "trend": "bearish"},
            closed_at=base_time - timedelta(seconds=window // 2 + i),
        )

    model = train_confidence_model("technical", window=window, min_samples=window)

    assert model is not None
    assert model.sample_count == window
    assert model.domain == "technical"
    assert "rsi_value" in model.numeric_features

    # Model, yuksek RSI'yi dogru cikma ile iliskilendirmis olmali (pozitif katsayi).
    rsi_idx = model.numeric_features.index("rsi_value")
    assert model.coefficients[rsi_idx] > 0


def test_train_confidence_model_returns_none_when_below_min_samples():
    model = train_confidence_model("technical", window=5, min_samples=10_000_000)
    assert model is None
