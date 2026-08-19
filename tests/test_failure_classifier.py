"""Faz 268-sonrası — kullanıcının kendi getirdiği çerçeve: her SL işlemini
GERÇEK MAE/MFE verisine göre direction_error/barrier_error diye ayırma."""
from analytics.failure_classifier import classify_stop_loss_failure, summarize_stop_loss_failures


def test_scenario_a_bad_prediction_is_direction_error():
    """Kullanıcının Senaryo A'sı: MFE küçük, fiyat hiç lehimize gitmedi."""
    result = classify_stop_loss_failure(
        entry_price=100.0, stop_loss_price=99.0, take_profit_price=102.0,
        mae_pct=-0.015, mfe_pct=0.008,
    )
    assert result == "direction_error"


def test_scenario_b_stop_too_tight_is_barrier_error():
    """Kullanıcının Senaryo B'si: MFE hedefe çok yakın/üstünde ama stop
    dar olduğu için işlem yine de kaybetti — model hatası değil."""
    result = classify_stop_loss_failure(
        entry_price=100.0, stop_loss_price=99.0, take_profit_price=102.0,
        mae_pct=-0.0105, mfe_pct=0.018,
    )
    assert result == "barrier_error"


def test_scenario_c_deep_adverse_move_with_tiny_mfe_is_direction_error():
    result = classify_stop_loss_failure(
        entry_price=100.0, stop_loss_price=99.0, take_profit_price=102.0,
        mae_pct=-0.017, mfe_pct=0.003,
    )
    assert result == "direction_error"


def test_missing_data_is_insufficient_data_not_a_fabricated_category():
    assert classify_stop_loss_failure(None, 99.0, 102.0, -0.01, 0.01) == "insufficient_data"
    assert classify_stop_loss_failure(100.0, 99.0, 102.0, None, 0.01) == "insufficient_data"
    assert classify_stop_loss_failure(100.0, 99.0, 102.0, -0.01, None) == "insufficient_data"
    assert classify_stop_loss_failure(100.0, 99.0, None, -0.01, 0.01) == "insufficient_data"


def test_reachability_exactly_at_threshold_is_barrier_error():
    # planned_target_pct = 0.02, mfe_pct = 0.014 -> reachability tam 0.7.
    result = classify_stop_loss_failure(
        entry_price=100.0, stop_loss_price=99.0, take_profit_price=102.0,
        mae_pct=-0.01, mfe_pct=0.014,
    )
    assert result == "barrier_error"


def test_summarize_stop_loss_failures_returns_real_shape():
    result = summarize_stop_loss_failures(hours=90)
    assert "total_stop_loss_trades" in result
    assert result["direction_error_count"] + result["barrier_error_count"] + result["insufficient_data_count"] == result["total_stop_loss_trades"]
    if result["total_stop_loss_trades"] > 0:
        assert 0.0 <= (result["direction_error_pct"] or 0.0) <= 1.0


def test_summarize_stop_loss_failures_counts_by_closed_at_not_opened_at():
    """Gerçek canlı bulgu (2026-08-18): pozisyonlar günlerce açık
    kalabiliyor — opened_at'a göre filtrelemek, GÜNLER önce açılıp
    BUGÜN stop'a takılmış bir işlemi "son dönem stop-loss'ları"ndan
    tamamen düşürüyordu. 10 gün önce açılıp AZ ÖNCE stop_loss ile
    kapanmış bir işlem, 90 saatlik pencerede SAYILMALI."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    symbol = f"FAILCLS{uuid4().hex[:8]}"
    old_open = datetime.now(UTC) - timedelta(days=10)
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
            final_size=1.0, confidence=0.7, status="open",
            entry_price=100.0, quantity=1.0, opened_at=old_open,
            stop_loss_price=99.0, take_profit_price=102.0,
        )
        repo.persist(event)

    before = summarize_stop_loss_failures(hours=90)

    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        # planned_target_pct=0.02, mfe_pct=0.008 -> reachability=0.4,
        # eşiğin altında -> direction_error (test_scenario_a ile aynı girdi).
        repo.close_position(
            decision_id=str(event.id), exit_price=99.0, pnl=-1.0, closed_at=now,
            outcome={"exit_reason": "stop_loss", "mae_pct": -0.015, "mfe_pct": 0.008},
        )

    after = summarize_stop_loss_failures(hours=90)

    assert after["total_stop_loss_trades"] == before["total_stop_loss_trades"] + 1
    assert after["direction_error_count"] == before["direction_error_count"] + 1


def test_pump_fade_stop_losses_are_isolated_from_ai_council_top_level_counts():
    """Faz 282 — kritik bulgu ("A/B kanal izolasyonu"): pump_fade_v1, AI
    konseyinden tamamen yalıtık mekanik bir fade stratejisi — kendi
    stop-loss örüntüsü üst düzey (AI konseyi) sayılara karışırsa LLM
    denetçisi yanlış bir teşhise varabilir. Bir pump_fade_v1 stop-loss'u
    üst düzey sayılara HİÇ eklenmemeli, sadece ayrı 'pump_fade' alanına."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    symbol = f"FAILPF{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="SHORT", final_action="SHORT",
            final_size=1.0, confidence=0.7, status="open",
            entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=102.0, take_profit_price=90.0,
            experiment_bucket="pump_fade_v1",
        )
        repo.persist(event)

    before = summarize_stop_loss_failures(hours=90)

    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        # planned_target_pct=0.1, mfe_pct=0.008 -> reachability=0.08 -> direction_error.
        repo.close_position(
            decision_id=str(event.id), exit_price=102.0, pnl=-2.0, closed_at=now,
            outcome={"exit_reason": "stop_loss", "mae_pct": -0.02, "mfe_pct": 0.008},
        )

    after = summarize_stop_loss_failures(hours=90)

    assert after["total_stop_loss_trades"] == before["total_stop_loss_trades"]
    assert after["pump_fade"]["total_stop_loss_trades"] == before["pump_fade"]["total_stop_loss_trades"] + 1
    assert after["pump_fade"]["direction_error_count"] == before["pump_fade"]["direction_error_count"] + 1
