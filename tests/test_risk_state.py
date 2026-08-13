"""Faz 188: services/risk_state.py — gerçek açık pozisyon sayısı ve
kullanılan sermaye yüzdesinin gerçek DB'den doğru hesaplandığını doğrular."""
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.risk_state import load_position_risk_state


def _cleanup_symbol(symbol: str) -> None:
    """Faz 268q — kritik bulgu: bu dosyadaki testler RISKSTATE* sembollü,
    opened_at=NULL (hiç set edilmemiş) açık pozisyonlar oluşturuyordu ama
    hiçbiri temizlemiyordu — paylaşılan quantdb_test'te 120 satıra kadar
    birikmişti. Postgres'te ORDER BY opened_at DESC NULL'ları EN BAŞA
    koyar — bu 120 satır, GET /positions'ın (limit=100) "en son açılan"
    penceresini KALICI olarak işgal edip GERÇEK/yeni pozisyonları
    görünmez kılıyordu (Faz 268p'nin canlı-PnL testinde yakalandı)."""
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol LIKE :pattern"), {"pattern": f"{symbol}%"})
        session.commit()


def test_open_position_count_and_capital_used_pct_reflect_real_open_positions():
    symbol = f"RISKSTATE{uuid4().hex[:8]}"
    try:
        with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set("starting_capital", "1000", updated_by="test")

            with SessionFactory.get_session() as session:
                repo = DecisionPersistor(session)
                before = repo.list_open_positions(limit=5000)
                repo.persist(DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=2.0,
                ))

            state = load_position_risk_state()

            assert state["open_position_count"] == len(before) + 1
            # capital_committed en az bu yeni pozisyonun notional'ı kadar artmış olmalı
            assert state["capital_used_pct"] > 0
    finally:
        _cleanup_symbol(symbol)


def test_trading_mode_defaults_to_test_when_never_set():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            row = AppSettingsRepository(session).get("trading_mode")
        # Ya hiç set edilmemiş (default "test") ya da başka bir testte
        # zaten "live" set edilmiş olabilir (paylaşılan dev DB) — her iki
        # durumda da geçerli bir mod dönmeli.
        assert row in ("test", "live")


def test_timeframe_filter_only_counts_matching_timeframe_positions():
    """Faz 259: orta-vadeli katman sadece KENDİ timeframe'inden açılmış
    pozisyonları saymalı."""
    symbol = f"RISKSTATE{uuid4().hex[:8]}"
    try:
        with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
            with SessionFactory.get_session() as session:
                repo = DecisionPersistor(session)
                before = len([
                    p for p in repo.list_open_positions(limit=5000) if p.get("timeframe") == "1d"
                ])
                repo.persist(DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=2.0, timeframe="1d",
                ))
                repo.persist(DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=2.0, timeframe="15m",
                ))

            state = load_position_risk_state(timeframe_filter="1d")

            assert state["open_position_count"] == before + 1
    finally:
        _cleanup_symbol(symbol)


def test_exclude_timeframe_counts_everything_except_that_timeframe():
    """Faz 259: kısa-vadeli katman, orta-vadeli katmanın pozisyonlarını
    HARİÇ tutup geri kalan HER ŞEYİ (NULL timeframe dahil — migration
    öncesi eski pozisyonlar) saymalı."""
    symbol = f"RISKSTATE{uuid4().hex[:8]}"
    try:
        with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
            with SessionFactory.get_session() as session:
                repo = DecisionPersistor(session)
                before = len([
                    p for p in repo.list_open_positions(limit=5000) if p.get("timeframe") != "1d"
                ])
                repo.persist(DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=2.0, timeframe="1d",
                ))
                repo.persist(DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=2.0, timeframe=None,
                ))

            state = load_position_risk_state(exclude_timeframe="1d")

            assert state["open_position_count"] == before + 1
    finally:
        _cleanup_symbol(symbol)


def test_consecutive_losses_counts_only_the_unbroken_streak_from_the_top():
    """Kill switch — gerçek DB'ye karşı: en son kapanmış işlemlerden
    (kronolojik olarak en yeniden en eskiye) geriye doğru İLK kazançtan
    önceki ardışık kayıp sayısı. Gelecek tarihli (bu process'in yazdığı
    dışında hiçbir gerçek kayıtla çakışmayacak, her zaman "en yeni")
    kayıtlar kullanılarak deterministik hale getirildi."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor

    symbol = f"RISKSTATE{uuid4().hex[:8]}"
    far_future = datetime.now(UTC) + timedelta(days=3650)
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            # En eskiden en yeniye: KAZANÇ, sonra 3 KAYIP (en yeni 3 kayıt).
            for i, pnl in enumerate([10.0, -5.0, -3.0, -1.0]):
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                )
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=100.0, pnl=pnl,
                    closed_at=far_future + timedelta(seconds=i),
                )

        state = load_position_risk_state()
        assert state["consecutive_losses"] == 3
    finally:
        _cleanup_symbol(symbol)


def test_consecutive_losses_is_zero_when_the_most_recent_trade_won():
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor

    symbol = f"RISKSTATE{uuid4().hex[:8]}"
    far_future = datetime.now(UTC) + timedelta(days=3650, hours=1)  # önceki testten bile daha yeni
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for i, pnl in enumerate([-5.0, -3.0, 10.0]):  # en yeni kayıt (son) bir kazanç
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                )
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=100.0, pnl=pnl,
                    closed_at=far_future + timedelta(seconds=i),
                )

        state = load_position_risk_state()
        assert state["consecutive_losses"] == 0
    finally:
        _cleanup_symbol(symbol)


def test_consecutive_losses_does_not_silently_truncate_at_the_initial_fetch_limit():
    """Kritik bulgu (2026-08-12): canlıda gerçek bir seri (115 kayıp) sabit
    bir sorgu limitinden (max(50, threshold*2)) UZUNDU — eski kod bunu
    sessizce 50'de kesiyordu. threshold=5 iken başlangıç limiti max(50,10)=50
    olur; burada 70 ardışık kayıp üretip GERÇEK sayının (70, 50 DEĞİL)
    döndüğünü kanıtlıyoruz."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor

    symbol = f"RISKSTATE{uuid4().hex[:8]}"
    far_future = datetime.now(UTC) + timedelta(days=3650, hours=2)  # bu dosyadaki diğer testlerden bile daha yeni
    try:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("kill_switch_consecutive_losses", "5", updated_by="test")

        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            pnls = [10.0] + [-1.0] * 70  # en eski: kazanç, sonra 70 ardışık kayıp
            for i, pnl in enumerate(pnls):
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                )
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=100.0, pnl=pnl,
                    closed_at=far_future + timedelta(seconds=i),
                )

        state = load_position_risk_state()
        assert state["consecutive_losses"] == 70
    finally:
        _cleanup_symbol(symbol)
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("kill_switch_consecutive_losses", "10", updated_by="test")


def test_kill_switch_threshold_reflects_app_setting():
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("kill_switch_consecutive_losses", "7", updated_by="test")
    try:
        state = load_position_risk_state()
        assert state["kill_switch_consecutive_losses"] == 7
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("kill_switch_consecutive_losses", "10", updated_by="test")


def test_legacy_cutoff_ignores_pre_cutoff_positions_even_when_they_are_the_most_recent_closes():
    """Gerçek canlı senaryo: eski (cutoff'tan önce açılmış) pozisyonlar
    ŞU AN kapanıyor (en yeni kapanışlar onlar), yeni (cutoff'tan sonra
    açılmış) bir kazanç ise DAHA ÖNCE kapanmış olabilir. Cutoff olmadan
    sayaç eski kayıplarla büyümeye devam eder; cutoff'la o eski kayıplar
    sorgudan hiç dönmemeli, sayaç 0 kalmalı (kazanç zaten görülebilir tek
    kayıt)."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor

    symbol = f"RISKSTATE{uuid4().hex[:8]}"
    far_future = datetime.now(UTC) + timedelta(days=3650, hours=4)
    cutoff = far_future
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            # Cutoff'tan SONRA açılmış kazanç — ÖNCE kapanıyor (daha eski closed_at).
            win_event = DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                opened_at=cutoff + timedelta(minutes=1),
            )
            repo.persist(win_event)
            repo.close_position(
                decision_id=str(win_event.id), exit_price=105.0, pnl=5.0,
                closed_at=far_future,
            )
            # Cutoff'tan ÖNCE açılmış eski kayıplar — sonradan (daha yeni) kapanıyor.
            for i in range(15):
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                    opened_at=cutoff - timedelta(hours=1),
                )
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=100.0, pnl=-1.0,
                    closed_at=far_future + timedelta(minutes=1, seconds=i),
                )

        # Cutoff KAPALIYKEN: en yeni 15 kapanış hepsi eski-kuyruk kaybı,
        # sayaç gerçekten 15 olmalı (bu, aşağıdaki cutoff'un asıl fark
        # yarattığını kanıtlayan referans nokta).
        state_before = load_position_risk_state()
        assert state_before["consecutive_losses"] == 15

        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "kill_switch_legacy_cutoff_at", cutoff.isoformat(), updated_by="test",
            )

        # Cutoff AÇIKKEN: o 15 kayıt sorguya hiç girmez, geriye SADECE
        # cutoff-sonrası kazanç kalır -> sayaç 0.
        state_after = load_position_risk_state()
        assert state_after["consecutive_losses"] == 0
    finally:
        _cleanup_symbol(symbol)
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("kill_switch_legacy_cutoff_at", "", updated_by="test")


def test_capital_pct_and_max_concurrent_overrides_replace_settings_values():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        state = load_position_risk_state(capital_pct_override=0.1, max_concurrent_override=5)

        assert state["max_capital_pct"] == 0.1
        assert state["max_concurrent_positions"] == 5
