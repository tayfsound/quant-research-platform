"""analytics/strategy_regime_compatibility.py — Faz 338 (MetaStrategyAgent
v1). "Bu stratejinin şu anki piyasa rejiminde gerçek edge'i var mı?"
sorusuna GERÇEK verilerle cevap veren, ölçüm-only bir modül."""
from datetime import UTC, datetime
from uuid import uuid4

from analytics.strategy_regime_compatibility import compute_strategy_regime_compatibility
from services.strategy_regime_compatibility_gatherer import _strategy_label


def _records(strategy: str, regime: str, n: int, win_count: int) -> list[dict]:
    return [
        {"strategy": strategy, "market_regime": regime, "win": i < win_count}
        for i in range(n)
    ]


def test_empty_input_returns_empty_dict():
    assert compute_strategy_regime_compatibility([]) == {}


def test_below_min_group_size_is_excluded_but_overall_still_reported():
    records = _records("pump_fade", "bullish_low", n=5, win_count=4)
    result = compute_strategy_regime_compatibility(records, min_group_size=15)
    assert "pump_fade" in result
    assert result["pump_fade"]["overall_sample_size"] == 5
    assert result["pump_fade"]["by_regime"] == {}  # esik altinda, disarida


def test_regime_conditional_win_rate_and_delta_computed():
    """pump_fade bullish rejimde kötü (%20), bearish rejimde iyi (%90) —
    tam olarak bugünkü krizin ölçtüğü desen."""
    records = (
        _records("pump_fade", "bullish_normal", n=20, win_count=4)  # %20
        + _records("pump_fade", "bearish_normal", n=20, win_count=18)  # %90
    )
    result = compute_strategy_regime_compatibility(records, min_group_size=15)
    pf = result["pump_fade"]
    assert pf["overall_sample_size"] == 40
    assert pf["overall_win_rate"] == 0.55  # (4+18)/40
    assert pf["by_regime"]["bullish_normal"]["win_rate"] == 0.2
    assert pf["by_regime"]["bearish_normal"]["win_rate"] == 0.9
    assert pf["by_regime"]["bullish_normal"]["delta_vs_overall"] == -0.35
    assert pf["by_regime"]["bearish_normal"]["delta_vs_overall"] == 0.35


def test_multiple_strategies_are_kept_independent():
    records = (
        _records("pump_fade", "bullish_normal", n=20, win_count=4)
        + _records("ai_council", "bullish_normal", n=20, win_count=19)
    )
    result = compute_strategy_regime_compatibility(records, min_group_size=15)
    assert set(result.keys()) == {"pump_fade", "ai_council"}
    assert result["ai_council"]["by_regime"]["bullish_normal"]["win_rate"] == 0.95


def test_strategy_label_includes_direction_for_ai_council():
    assert _strategy_label("some_other_bucket", "LONG", None, None) == "ai_council_LONG"
    assert _strategy_label(None, "SHORT", None, None) == "ai_council_SHORT"


def test_strategy_label_includes_direction_for_pump_fade():
    from services.pump_fade_strategy import EXPERIMENT_BUCKET

    assert _strategy_label(EXPERIMENT_BUCKET, "SHORT", None, None) == "pump_fade_SHORT"


def test_strategy_label_includes_direction_for_basis_arb():
    # Faz 364 — basis_arb_v1 stratejisi kaldırıldı; sabit geçmiş
    # kararların etiketi hâlâ doğru üretilmeli.
    assert _strategy_label("basis_arb_v1", "SHORT", None, None) == "basis_arb_SHORT"


def test_strategy_label_falls_back_without_direction():
    """Yön yoksa/bilinmiyorsa (fail-closed) eski, kaba etikete düşer —
    icat edilmiş bir yön eklenmez."""
    assert _strategy_label("some_other_bucket", None, None, None) == "ai_council"
    assert _strategy_label("some_other_bucket", "", None, None) == "ai_council"


def test_strategy_label_adds_trade_type_for_ai_council_only():
    """Faz 345 — trade_type SADECE ai_council için ekleniyor; scalp
    eşiği (%4.5) altındaki stop mesafesi scalp, üstündeki swing."""
    assert _strategy_label("x", "LONG", 100.0, 98.0) == "ai_council_LONG_scalp"  # %2
    assert _strategy_label("x", "LONG", 100.0, 90.0) == "ai_council_LONG_swing"  # %10
    assert _strategy_label("x", "LONG", None, None) == "ai_council_LONG"  # veri yok -> eklenmez


def test_strategy_label_does_not_add_trade_type_for_pump_fade_or_basis_arb():
    """pump_fade/basis_arb kendi sabit stop-geometrisiyle mekanik —
    trade_type ayrımı bilgi katmıyor, bilerek eklenmiyor."""
    from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_BUCKET

    assert _strategy_label(PUMP_FADE_BUCKET, "SHORT", 100.0, 130.0) == "pump_fade_SHORT"
    assert _strategy_label("basis_arb_v1", "SHORT", 100.0, 130.0) == "basis_arb_SHORT"


def test_gather_strategy_regime_compatibility_splits_ai_council_by_direction():
    """Faz 342 — kullanıcı bulgusu ("short pozisyonlar neden karlı
    değil?") gerçek entegrasyonu: aynı rejimde (bearish_low) LONG ve
    SHORT kapanmış kararları ai_council_LONG/ai_council_SHORT olarak
    AYRI raporlanmalı, tek bir karışık "ai_council" kovasına düşmemeli."""
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from services.strategy_regime_compatibility_gatherer import gather_strategy_regime_compatibility

    symbol = f"SRCTEST{uuid4().hex[:8]}USDT"
    ids = []
    try:
        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)

            def _open_and_close(direction: str, win: bool) -> None:
                from contracts.decision_event import DecisionEvent

                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction=direction, final_action=direction,
                    final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                )
                persistor.persist(event)
                ids.append(event.id)
                persistor.close_position(
                    decision_id=str(event.id), exit_price=100.0,
                    pnl=(10.0 if win else -10.0), closed_at=datetime.now(UTC),
                    market_regime="bearish_low",
                )

            _open_and_close("LONG", True)
            _open_and_close("SHORT", False)

        result = gather_strategy_regime_compatibility()
        by_strategy = result["by_strategy"]
        assert "ai_council_LONG" in by_strategy
        assert "ai_council_SHORT" in by_strategy
    finally:
        from sqlalchemy import text as _text

        with SessionFactory.get_session() as session:
            session.execute(_text("DELETE FROM decisions WHERE symbol = :s"), {"s": symbol})
            session.commit()


def test_gather_strategy_regime_compatibility_splits_ai_council_by_trade_type():
    """Faz 345 — kullanıcı vizyonu ("scalp %99 başarılı bu koşullarda")
    gerçek entegrasyonu: AYNI rejimde/yönde scalp ve swing kapanışları
    ai_council_LONG_scalp/ai_council_LONG_swing olarak AYRI raporlanmalı."""
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from services.strategy_regime_compatibility_gatherer import gather_strategy_regime_compatibility

    symbol = f"SRCTT{uuid4().hex[:8]}USDT"
    try:
        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)

            def _open_and_close(stop_loss_price: float, win: bool) -> None:
                from contracts.decision_event import DecisionEvent

                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                    stop_loss_price=stop_loss_price,
                )
                persistor.persist(event)
                persistor.close_position(
                    decision_id=str(event.id), exit_price=100.0,
                    pnl=(10.0 if win else -10.0), closed_at=datetime.now(UTC),
                    market_regime="bullish_low",
                )

            _open_and_close(98.0, True)  # %2 -> scalp
            _open_and_close(90.0, False)  # %10 -> swing

        result = gather_strategy_regime_compatibility()
        by_strategy = result["by_strategy"]
        assert "ai_council_LONG_scalp" in by_strategy
        assert "ai_council_LONG_swing" in by_strategy
    finally:
        from sqlalchemy import text as _text

        with SessionFactory.get_session() as session:
            session.execute(_text("DELETE FROM decisions WHERE symbol = :s"), {"s": symbol})
            session.commit()


def test_records_with_missing_fields_are_skipped():
    records = [
        {"strategy": "pump_fade", "market_regime": None, "win": True},
        {"strategy": None, "market_regime": "bullish_normal", "win": True},
        {"strategy": "pump_fade", "market_regime": "bullish_normal", "win": None},
    ]
    result = compute_strategy_regime_compatibility(records)
    assert result == {}
