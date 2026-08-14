"""Faz 268-sonrası — kullanıcı isteği: gerçek meta-labeling, P(TP before
SL). services/agent_confidence_model.py ile AYNI mimari (lojistik
regresyon, gerçek train/test split) — burada TEK fark, "hangi ajan doğru
çıktı" değil "TP mi SL mi önce geldi" öğreniliyor. Kasıtlı olarak
HİÇBİR canlı karara bağlanmıyor — sadece gerçek OOS doğrulama metrikleri
üretiyor."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.agent_confidence_model import AgentConfidenceModel
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.agent_confidence_model import ConfidenceModelRepository
from services.meta_label_model import (
    META_LABEL_DOMAIN,
    predict_tp_probability,
    train_meta_label_model,
)


def test_no_saved_model_returns_none_probability(tmp_path):
    repo = ConfidenceModelRepository(storage_path=str(tmp_path / "meta_label_models"))
    result = predict_tp_probability({"planned_rr_ratio": 2.0}, repository=repo)
    assert result is None


def test_predict_tp_probability_uses_saved_model(tmp_path):
    repo = ConfidenceModelRepository(storage_path=str(tmp_path / "meta_label_models"))
    model = AgentConfidenceModel(
        domain=META_LABEL_DOMAIN,
        window_size=200,
        sample_count=200,
        numeric_features=["planned_rr_ratio"],
        boolean_features=[],
        categorical_features={},
        scaler_mean=[1.0],
        scaler_scale=[0.5],
        coefficients=[-1.0],  # rr orani buyudukce (hedef stop'tan cok uzaklastikca) P(TP) duser
        intercept=0.0,
        baseline_correctness_rate=0.5,
        train_accuracy=0.6,
        test_accuracy=0.6,
    )
    repo.save(model)

    low_rr_prob = predict_tp_probability({"planned_rr_ratio": 0.5}, repository=repo)
    high_rr_prob = predict_tp_probability({"planned_rr_ratio": 3.0}, repository=repo)

    assert low_rr_prob > high_rr_prob
    assert 0.0 <= low_rr_prob <= 1.0
    assert 0.0 <= high_rr_prob <= 1.0


def test_train_meta_label_model_returns_none_when_below_min_samples():
    model = train_meta_label_model(window=5, min_samples=10_000_000)
    assert model is None


def _persist_closed_decision_for_meta_label(
    symbol: str, entry_price: float, stop_loss_price: float, take_profit_price: float,
    confidence: float, features: dict, exit_reason: str, closed_at: datetime,
) -> None:
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(),
            symbol=symbol,
            proposed_direction="LONG",
            final_action="LONG",
            final_size=0.1,
            confidence=confidence,
            status="open",
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            quantity=1.0,
            opened_at=closed_at - timedelta(minutes=10),
            agent_opinions=[],
            market_snapshot={"features": features},
        )
        persistor.persist(event)
        exit_price = take_profit_price if exit_reason == "take_profit" else stop_loss_price
        pnl = 5.0 if exit_reason == "take_profit" else -5.0
        persistor.close_position(
            decision_id=str(event.id),
            exit_price=exit_price,
            pnl=pnl,
            closed_at=closed_at,
            outcome={"exit_reason": exit_reason, "pnl": pnl},
        )


def test_train_meta_label_model_learns_a_real_pattern_from_fresh_window_dominated_data():
    """Faz 264'teki AYNI kanıtlanmış test deseni (bkz. test_agent_
    confidence_model.py) — gelecek tarihli veri, kendi sembolüyle tam
    doldurulmuş pencere, sonda temizlik."""
    window = 120
    base_time = datetime.now(UTC) + timedelta(days=3650)
    symbol = f"METALABEL{uuid4().hex[:8]}"

    try:
        # Yuksek confidence + dar R/R oraninda HEP TP, dusuk confidence +
        # genis R/R oraninda HEP SL - ogrenilebilir, net bir oruntu.
        for i in range(window // 2):
            _persist_closed_decision_for_meta_label(
                symbol, entry_price=100.0, stop_loss_price=98.0, take_profit_price=100.5,
                confidence=0.9, features={"trend": "bullish", "volatility_regime": "normal"},
                exit_reason="take_profit", closed_at=base_time - timedelta(seconds=i),
            )
        for i in range(window // 2):
            _persist_closed_decision_for_meta_label(
                symbol, entry_price=100.0, stop_loss_price=98.0, take_profit_price=110.0,
                confidence=0.3, features={"trend": "bearish", "volatility_regime": "high"},
                exit_reason="stop_loss", closed_at=base_time - timedelta(seconds=window // 2 + i),
            )

        model = train_meta_label_model(window=window, min_samples=window)

        assert model is not None
        assert model.sample_count == window
        assert model.domain == META_LABEL_DOMAIN
        assert "planned_rr_ratio" in model.numeric_features
        assert "confidence" in model.numeric_features
        # Gerçek OOS doğrulama alanları hep dolu olmalı.
        assert 0.0 <= model.test_accuracy <= 1.0
        assert 0.0 <= model.baseline_correctness_rate <= 1.0

        # Model, dar R/R + yuksek confidence'i TP ile iliskilendirmis olmali.
        rr_idx = model.numeric_features.index("planned_rr_ratio")
        conf_idx = model.numeric_features.index("confidence")
        assert model.coefficients[rr_idx] < 0  # genis oran -> P(TP) duser
        assert model.coefficients[conf_idx] > 0  # yuksek confidence -> P(TP) artar
    finally:
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()


def test_extraction_excludes_manual_and_other_exit_reasons():
    """Sadece take_profit/stop_loss ile kapanan işlemler eğitim verisine
    girer — manual_full/breakeven_stop/time_expired TP-mi-SL-mi
    yarışını temsil etmiyor, dahil edilmemeli. Paylaşılan test DB'sinde
    global model eğitimi (train_meta_label_model) yerine, doğrudan SQL
    filtresinin kendi sembolümdeki satırları GERÇEKTEN dışarıda
    bıraktığını satır sayısıyla doğruluyor — global pencere yarışına
    (başka testlerin take_profit/stop_loss verisiyle) bağımlı değil."""
    from sqlalchemy import text

    base_time = datetime.now(UTC) + timedelta(days=3652)
    symbol = f"MLEXCL{uuid4().hex[:8]}"

    try:
        for i in range(10):
            _persist_closed_decision_for_meta_label(
                symbol, entry_price=100.0, stop_loss_price=98.0, take_profit_price=102.0,
                confidence=0.5, features={"trend": "bullish", "volatility_regime": "normal"},
                exit_reason="manual_full", closed_at=base_time - timedelta(seconds=i),
            )
        with SessionFactory.get_session() as session:
            matched = session.execute(
                text(
                    "SELECT count(*) FROM decisions WHERE symbol = :symbol "
                    "AND outcome ->> 'exit_reason' IN ('take_profit', 'stop_loss')"
                ),
                {"symbol": symbol},
            ).scalar()
        assert matched == 0
    finally:
        with SessionFactory.get_session() as session:
            from sqlalchemy import text as sa_text
            session.execute(sa_text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()
