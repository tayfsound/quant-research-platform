"""Faz 187: gerçek pozisyon yaşam döngüsü — açılış (DecisionRecorder)
ve kapanış (PositionCloser), backtest tarzı anlık ForwardOutcome'dan ayrı."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.position_closer import PositionCloser


def test_close_due_positions_checks_all_open_positions_not_just_the_default_200_cap():
    """KRİTİK regresyon kilidi — gerçek olay (2026-08-19, canlıda
    yakalandı): sistemde GERÇEKTEN 2631 açık pozisyon varken, close_due_
    positions() decision_repo.list_open_positions()'ı hiç argüman
    vermeden (varsayılan limit=200) çağırıyordu. ORDER BY opened_at DESC
    yüzünden en eski ~2431 pozisyon (bazıları %20+ kârda, GPSUSDT/
    TUTUSDT/HEMIUSDT/PORTALUSDT dahil) bu döngüye HİÇ girmiyordu — stop/
    hedef/likidasyon/breakeven/trailing kontrolü sonsuza kadar
    atlanıyordu. Artık limit=None ile TÜM açık pozisyonlar taranmalı."""
    captured = {}

    class _FakeRepo:
        def list_open_positions(self, limit=200, offset=0):
            captured["limit"] = limit
            captured["offset"] = offset
            return []

    closer = PositionCloser(_FixedPriceProvider(100.0))
    closer.close_due_positions(_FakeRepo())

    assert captured["limit"] is None


def test_list_open_positions_with_limit_none_returns_every_row_not_just_the_default_cap():
    """decision_persistor.py::list_open_positions'ın limit=None desteğini
    gerçek veriyle doğrular — LIMIT ifadesi tamamen kaldırılmalı,
    limit verilen küçük bir sayıdan daha FAZLA satır dönmeli."""
    from contracts.decision_event import DecisionEvent

    symbol_prefix = f"POSALL{uuid4().hex[:6]}"
    now = datetime.now(UTC)
    ids = []
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        for i in range(3):
            event = DecisionEvent(
                id=uuid4(), timestamp=now, symbol=f"{symbol_prefix}{i}",
                proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
                status="open", entry_price=100.0, quantity=1.0, opened_at=now,
                stop_loss_price=90.0, take_profit_price=140.0,
            )
            persistor.persist(event)
            ids.append(str(event.id))

    try:
        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            limited = persistor.list_open_positions(limit=1)
            unlimited = persistor.list_open_positions(limit=None)

        assert len(limited) == 1
        unlimited_ids = {p["id"] if isinstance(p["id"], str) else str(p["id"]) for p in unlimited}
        assert set(ids).issubset(unlimited_ids)
    finally:
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM decisions WHERE symbol LIKE :p"), {"p": f"{symbol_prefix}%"})
            session.commit()


def test_risk_approved_directional_decision_opens_a_real_position_with_entry_price_and_no_pnl_yet():
    """DecisionRecorder seviyesinde, doğrudan: gerçek Council'in (boş ctx.market
    ile hep WAIT üretmesi — ayrı, bilinen bir davranış) değişkenliğine bağlı
    kalmadan, risk-onaylı yönlü bir karar geldiğinde DecisionPersistor'ın
    gerçekten 'open' bir pozisyon satırı yazdığını doğrular."""
    from unittest.mock import patch

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from contracts.context import CognitiveCycleContext
        from services.decision_recorder import DecisionRecorder

        symbol = f"POSLIFE{uuid4().hex[:8]}"
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.decision.proposed_direction = "LONG"
        ctx.decision.final_size = 0.3
        ctx.decision.filled_price = 27123.45
        ctx.risk.evaluation.verdict = "approved"

        DecisionRecorder().record(ctx)

    with SessionFactory.get_session() as session:
        rows = DecisionPersistor(session).list_open_positions(limit=200)
    matches = [r for r in rows if r["symbol"] == symbol]

    assert matches
    pos = matches[0]
    assert pos["status"] == "open"
    assert pos["entry_price"] == 27123.45
    assert pos["quantity"] == 0.3
    assert pos["opened_at"] is not None
    assert pos["pnl"] is None
    assert pos["exit_price"] is None


def test_leveraged_position_scales_quantity_and_computes_liquidation_price():
    """Faz 255: kullanıcı isteği — token bazlı kaldıraç. symbol_leverage
    ayarında bir sembol için kaldıraç varsa, açılan pozisyonun quantity'si
    (aynı teminatla daha büyük notional kontrolü — gerçek kaldıraçlı
    işlemin tanımı) buna göre ölçeklenmeli ve gerçek bir likidasyon
    fiyatı hesaplanmalı."""
    import json
    from unittest.mock import patch

    from database.repositories.app_settings_repository import AppSettingsRepository
    from simulator.margin import compute_liquidation_price

    symbol = f"POSLEV{uuid4().hex[:8]}"

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        current = json.loads(repo.get("symbol_leverage") or "{}")
        current[symbol] = 10.0
        repo.set("symbol_leverage", json.dumps(current), updated_by="test")

    try:
        with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
            from contracts.context import CognitiveCycleContext
            from services.decision_recorder import DecisionRecorder

            ctx = CognitiveCycleContext()
            ctx.market.symbol = symbol
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.final_size = 0.3
            ctx.decision.filled_price = 100.0
            ctx.risk.evaluation.verdict = "approved"

            DecisionRecorder().record(ctx)

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions(limit=200)
        pos = next(r for r in rows if r["symbol"] == symbol)

        assert pos["leverage"] == 10.0
        assert abs(pos["quantity"] - 3.0) < 1e-9  # 0.3 * 10x kaldıraç
        expected_liq = compute_liquidation_price(100.0, "LONG", leverage=10.0)
        assert abs(pos["liquidation_price"] - expected_liq) < 1e-9
    finally:
        # Gerçek bulgu: bu test her çalıştığında symbol_leverage'e YENİ bir
        # POSLEV<hex> girdisi ekleyip hiç temizlemiyordu — paylaşılan test
        # DB'sinde onlarca çalıştırma sonucunda değer 256 karakter VARCHAR
        # sınırını aştı (StringDataRightTruncation), bu testi VE ilgisiz
        # başka testleri (test_pairs_trader.py) çökertti.
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            current = json.loads(repo.get("symbol_leverage") or "{}")
            current.pop(symbol, None)
            repo.set("symbol_leverage", json.dumps(current), updated_by="test")


def test_wait_decision_never_opens_a_position():
    from unittest.mock import patch

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from contracts.context import CognitiveCycleContext
        from services.decision_recorder import DecisionRecorder

        symbol = f"POSNOTRADE{uuid4().hex[:8]}"
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.decision.proposed_direction = "WAIT"
        ctx.decision.final_size = 0.0
        ctx.risk.evaluation.verdict = "approved"

        DecisionRecorder().record(ctx)

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(ctx.cycle_id))

    assert row["status"] == "no_trade"
    assert row["entry_price"] is None
    assert row["opened_at"] is None


def test_risk_rejected_directional_decision_never_opens_a_position():
    from unittest.mock import patch

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from contracts.context import CognitiveCycleContext
        from services.decision_recorder import DecisionRecorder

        symbol = f"POSREJECTED{uuid4().hex[:8]}"
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.decision.proposed_direction = "LONG"
        ctx.decision.final_size = 0.3
        ctx.decision.filled_price = 100.0
        ctx.risk.evaluation.verdict = "rejected"

        DecisionRecorder().record(ctx)

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(ctx.cycle_id))

    assert row["status"] == "no_trade"
    assert row["entry_price"] is None


def test_position_closer_never_closes_on_age_alone_regardless_of_how_old():
    """Faz 215: kritik bulgu — vade dolunca kapatma (time_expired)
    kaldırıldı. Kullanıcının kendi sözleriyle: "bile bile zarar etmek
    demek bu." Gerçek veriyle doğrulandı: trade_horizon (10 dk) <
    candle_timeframe (15 dk) olduğunda kapanan işlemlerin %64'ü stop/
    target'a hiç ulaşmadan, sadece vade dolduğu için kapanıyordu — sinyal
    kalitesinden bağımsız, yapay bir kayıp mekanizmasıydı. Bu test, çok
    eski (1 hafta önce açılmış) ama fiyatı hâlâ stop/target arasında olan
    bir pozisyonun HÂLÂ açık kalması gerektiğini kanıtlıyor."""
    from contracts.decision_event import DecisionEvent

    symbol = f"POSNOEXP{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        very_old_event = DecisionEvent(
            id=uuid4(),
            timestamp=now - timedelta(days=7),
            symbol=symbol,
            proposed_direction="LONG",
            final_action="LONG",
            final_size=1.0,
            confidence=0.7,
            status="open",
            entry_price=100.0,
            quantity=1.0,
            opened_at=now - timedelta(days=7),
            stop_loss_price=90.0,
            take_profit_price=110.0,
        )
        DecisionPersistor(session).persist(very_old_event)

    # Fiyat stop (90) ile target (110) arasında — ne kadar eski olursa
    # olsun kapanmamalı.
    closer = PositionCloser(_FixedPriceProvider(103.0))
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    assert str(very_old_event.id) not in {c["decision_id"] for c in closed}

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(very_old_event.id))
    assert row["status"] == "open"


class _FixedPriceProvider:
    """Faz 192 testleri için: MockProvider'ın rastgele yürüyüşü yerine
    kontrollü bir güncel fiyat döndürür."""
    def __init__(self, price: float):
        self.price = price

    def get_ohlcv(self, symbol, timeframe, limit=1):
        from market_data.ingestion.ohlcv import OHLCV
        now = datetime.now(UTC)
        return [OHLCV(timestamp=now, open=self.price, high=self.price, low=self.price, close=self.price, volume=1.0)]


def test_position_closer_closes_immediately_on_take_profit_before_hold_expires():
    from contracts.decision_event import DecisionEvent

    symbol = f"POSTPHIT{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=90.0, take_profit_price=110.0,
        )
        DecisionPersistor(session).persist(event)

    # hold_seconds çok uzun (1 saat) — sadece TP'nin vadeyi beklemeden
    # kapattığını kanıtlamak için.
    closer = PositionCloser(_FixedPriceProvider(111.0), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    closed_ids = {c["decision_id"]: c for c in closed}
    assert str(event.id) in closed_ids
    assert closed_ids[str(event.id)]["exit_reason"] == "take_profit"

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "closed"
    assert row["exit_price"] == 111.0
    assert row["pnl"] > 0


def test_position_closer_closes_immediately_on_stop_loss_before_hold_expires():
    from contracts.decision_event import DecisionEvent

    symbol = f"POSSLHIT{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="SHORT", final_action="SHORT", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=110.0, take_profit_price=80.0,
        )
        DecisionPersistor(session).persist(event)

    closer = PositionCloser(_FixedPriceProvider(112.0), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    closed_ids = {c["decision_id"]: c for c in closed}
    assert str(event.id) in closed_ids
    assert closed_ids[str(event.id)]["exit_reason"] == "stop_loss"

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["pnl"] < 0


def test_breakeven_stop_ratchets_stop_to_entry_after_1r_profit_and_prevents_full_loss():
    """Faz 268ae — kullanıcı isteği: "pozisyon karlı gidiyor ama işler
    tersine döndü, stop yükseltilse tam zarar yerine nötr/az zararla
    çıkabilir." Gerçek veri bulgusu: son 30 günde stop_loss çıkışları
    -$2422, take_profit çıkışları sadece +$130 — yani sistemin kurduğu
    1:4 hedef/stop oranı gerçek sonuçlara hiç yansımıyordu, çünkü kârlı
    açılıp geri dönen pozisyonlar tam stop mesafesini yiyordu. Bu test:
    fiyat 1R (giriş-stop mesafesi kadar) lehte hareket edince stopun
    girişe çekildiğini, SONRA fiyat geri dönüp o yeni (sıkı) stopa
    takılınca kaybın eski (geniş) stopa göre çok daha küçük kaldığını
    kanıtlıyor. trailing_stop_distance_pct=0 ile trailing devre dışı —
    bu test SADECE breakeven mantığını izole doğruluyor (trailing ayrı,
    kendi testlerinde doğrulanıyor)."""
    from contracts.decision_event import DecisionEvent
    from database.repositories.app_settings_repository import AppSettingsRepository

    symbol = f"POSBE{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    entry, old_stop, target = 100.0, 90.0, 140.0  # risk = 10 (1R), hedef uzakta

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=entry, quantity=1.0, opened_at=now,
            stop_loss_price=old_stop, take_profit_price=target,
        )
        DecisionPersistor(session).persist(event)
        AppSettingsRepository(session).set("trailing_stop_distance_pct", "0", updated_by="test")

    try:
        # 1. adım: fiyat tam 1R kadar lehte (110) — ne stop ne hedefe
        # ulaşmadı, ama breakeven ratchet tetiklenmeli.
        closer_step1 = PositionCloser(_FixedPriceProvider(entry + (entry - old_stop)))
        with SessionFactory.get_session() as session:
            closed_step1 = closer_step1.close_due_positions(DecisionPersistor(session))
        assert not any(c["decision_id"] == str(event.id) for c in closed_step1)

        with SessionFactory.get_session() as session:
            row = DecisionPersistor(session).get_by_id(str(event.id))
        assert row["status"] == "open"
        assert row["stop_loss_price"] == entry  # stop girişe çekildi

        # 2. adım: fiyat geri dönüp YENİ (sıkı) stopun biraz altına
        # düşüyor — eski stop (90) hâlâ çok uzakta olurdu, ama artık
        # girişte takılmalı.
        closer_step2 = PositionCloser(_FixedPriceProvider(99.0))
        with SessionFactory.get_session() as session:
            closed_step2 = closer_step2.close_due_positions(DecisionPersistor(session))

        closed_ids = {c["decision_id"]: c for c in closed_step2}
        assert str(event.id) in closed_ids
        assert closed_ids[str(event.id)]["exit_reason"] == "breakeven_stop"

        with SessionFactory.get_session() as session:
            row = DecisionPersistor(session).get_by_id(str(event.id))
        assert row["status"] == "closed"
        # Eski (geniş) stop olan 90'a takılmış olsaydı kayıp ~10x daha
        # büyük olurdu — breakeven ratchet kaybı gerçekten küçültmüş
        # olmalı.
        old_stop_gross_pnl = (old_stop - entry) * 1.0  # -10.0
        assert old_stop_gross_pnl < row["pnl"] < 0.0
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("trailing_stop_distance_pct", "0.05", updated_by="test")


def test_breakeven_stop_never_loosens_and_is_symmetric_for_short():
    """Aynı mekanizmanın SHORT yönde de çalıştığını ve stopun asla ilk
    seviyesinden daha gevşek bir yöne çekilmediğini (sadece sıkılaştığını)
    doğruluyor. trailing_stop_distance_pct=0 ile trailing devre dışı —
    bu test SADECE breakeven mantığını izole doğruluyor."""
    from contracts.decision_event import DecisionEvent
    from database.repositories.app_settings_repository import AppSettingsRepository

    symbol = f"POSBESHORT{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    entry, old_stop, target = 100.0, 110.0, 60.0  # risk = 10, SHORT

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="SHORT", final_action="SHORT", final_size=1.0, confidence=0.7,
            status="open", entry_price=entry, quantity=1.0, opened_at=now,
            stop_loss_price=old_stop, take_profit_price=target,
        )
        DecisionPersistor(session).persist(event)
        AppSettingsRepository(session).set("trailing_stop_distance_pct", "0", updated_by="test")

    try:
        closer_step1 = PositionCloser(_FixedPriceProvider(entry - (old_stop - entry)))  # 90.0, 1R lehte
        with SessionFactory.get_session() as session:
            closer_step1.close_due_positions(DecisionPersistor(session))

        with SessionFactory.get_session() as session:
            row = DecisionPersistor(session).get_by_id(str(event.id))
        assert row["status"] == "open"
        assert row["stop_loss_price"] == entry

        # Fiyat girişin biraz da altına inip geri girişin ÜSTÜNE çıksa
        # bile (SHORT için "lehte" tekrar) stop girişten daha gevşek bir
        # yere (>entry, yani eski 110'a doğru) ASLA geri çekilmemeli.
        closer_step2 = PositionCloser(_FixedPriceProvider(80.0))
        with SessionFactory.get_session() as session:
            closer_step2.close_due_positions(DecisionPersistor(session))
        with SessionFactory.get_session() as session:
            row = DecisionPersistor(session).get_by_id(str(event.id))
        assert row["stop_loss_price"] == entry  # hâlâ girişte, gevşemedi
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("trailing_stop_distance_pct", "0.05", updated_by="test")


def test_breakeven_stop_trigger_threshold_is_configurable_and_lower_than_full_1r():
    """Faz 269-sonrası — kullanıcı bulgusu: pump_fade_v1 (5x kaldıraçlı,
    az likit coinlerde SHORT) pozisyonları TAM 1R'a (eski sabit eşik)
    hiç ulaşmadan (gerçek veride sadece %1-1.8 lehte gidip) ters dönüp
    likidasyona kadar gitti — koruma hiç devreye giremedi. Eşik artık
    AppSettings'ten okunuyor (varsayılan 0.5R); bu test SADECE 0.5R
    kadar lehte giden bir fiyatın (eski sabit 1.0R kuralında HİÇ
    tetiklenmeyecek bir mesafe) artık breakeven'i tetiklediğini
    kanıtlıyor."""
    from contracts.decision_event import DecisionEvent
    from database.repositories.app_settings_repository import AppSettingsRepository

    symbol = f"POSBELOW{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    entry, old_stop, target = 100.0, 90.0, 140.0  # risk = 10 (1R)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=entry, quantity=1.0, opened_at=now,
            stop_loss_price=old_stop, take_profit_price=target,
        )
        DecisionPersistor(session).persist(event)
        AppSettingsRepository(session).set("breakeven_trigger_r_multiple", "0.5", updated_by="test")

    try:
        # Sadece 0.5R (5.0) kadar lehte — eski sabit 1.0R kuralında bu
        # fiyat breakeven'i HİÇ tetiklemezdi.
        closer = PositionCloser(_FixedPriceProvider(entry + (entry - old_stop) * 0.5))
        with SessionFactory.get_session() as session:
            closer.close_due_positions(DecisionPersistor(session))

        with SessionFactory.get_session() as session:
            row = DecisionPersistor(session).get_by_id(str(event.id))
        assert row["status"] == "open"
        assert row["stop_loss_price"] == entry  # 0.5R'de bile stop girişe çekildi
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("breakeven_trigger_r_multiple", "0.5", updated_by="test")


def test_breakeven_stop_does_not_trigger_below_the_configured_threshold():
    """Eşiğin altındaki bir hareket (0.3R < ayarlanan 0.5R eşiği) hâlâ
    tetiklememeli — bu, eşiğin gerçekten UYGULANDIĞININ (her zaman
    tetiklenmediğinin) kanıtı."""
    from contracts.decision_event import DecisionEvent
    from database.repositories.app_settings_repository import AppSettingsRepository

    symbol = f"POSBENOTRIG{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    entry, old_stop, target = 100.0, 90.0, 140.0

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=entry, quantity=1.0, opened_at=now,
            stop_loss_price=old_stop, take_profit_price=target,
        )
        DecisionPersistor(session).persist(event)
        AppSettingsRepository(session).set("breakeven_trigger_r_multiple", "0.5", updated_by="test")

    try:
        closer = PositionCloser(_FixedPriceProvider(entry + (entry - old_stop) * 0.3))
        with SessionFactory.get_session() as session:
            closer.close_due_positions(DecisionPersistor(session))

        with SessionFactory.get_session() as session:
            row = DecisionPersistor(session).get_by_id(str(event.id))
        assert row["stop_loss_price"] == old_stop  # eşiğin altında, tetiklenmedi
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("breakeven_trigger_r_multiple", "0.5", updated_by="test")


def test_trailing_stop_locks_in_real_profit_beyond_breakeven():
    """Kullanıcı bulgusu: pump_fade pozisyonları ~$2k kârdayken piyasa
    tersine dönüp ~-$2k zarara kadar gidebiliyordu — breakeven (girişe
    çekme) TEK BAŞINA yetersizdi, çünkü SADECE net zararı önlüyor,
    GERÇEK kârı hiç KİLİTLEMİYOR. Fiyat entry_price'ın ÇOK ötesine
    (%30) gidince, trailing stop artık entry_price'ın DA ötesinde bir
    seviyeye (gerçek kilitlenmiş kâr) çekilmeli — sadece girişe değil."""
    from contracts.decision_event import DecisionEvent

    symbol = f"POSTRAIL{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    entry, old_stop, target = 100.0, 90.0, 200.0  # risk = 10, hedef uzakta

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=entry, quantity=1.0, opened_at=now,
            stop_loss_price=old_stop, take_profit_price=target,
        )
        DecisionPersistor(session).persist(event)

    # Fiyat entry'nin %30 üstüne çıkıyor — trailing_stop_distance_pct
    # varsayılanı (%5) ile trailing adayı: 130 - 100*0.05 = 125.
    closer = PositionCloser(_FixedPriceProvider(130.0))
    with SessionFactory.get_session() as session:
        closer.close_due_positions(DecisionPersistor(session))

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "open"
    assert abs(row["stop_loss_price"] - 125.0) < 1e-9  # entry_price'ın (100) ÖTESİNDE, gerçek kâr kilitli


def test_trailing_stop_never_loosens_on_a_small_pullback():
    """Fiyat zirveden hafifçe geri çekilse bile (henüz yeni stopun
    altına düşmeden) trailing stop ASLA gevşememeli — sadece sıkılaşır."""
    from contracts.decision_event import DecisionEvent

    symbol = f"POSTRAILHOLD{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    entry, old_stop, target = 100.0, 90.0, 200.0

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=entry, quantity=1.0, opened_at=now,
            stop_loss_price=old_stop, take_profit_price=target,
        )
        DecisionPersistor(session).persist(event)

    closer_step1 = PositionCloser(_FixedPriceProvider(130.0))  # stop -> 125
    with SessionFactory.get_session() as session:
        closer_step1.close_due_positions(DecisionPersistor(session))

    # Küçük bir geri çekilme (128), YENİ stopun (125) altına düşmüyor —
    # trailing adayı 128-100*0.05=123 < 125, stop GEVŞEMEMELİ.
    closer_step2 = PositionCloser(_FixedPriceProvider(128.0))
    with SessionFactory.get_session() as session:
        closed = closer_step2.close_due_positions(DecisionPersistor(session))

    assert not any(c["decision_id"] == str(event.id) for c in closed)
    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert abs(row["stop_loss_price"] - 125.0) < 1e-9  # hâlâ 125, gevşemedi


def test_trailing_stop_closes_the_position_while_still_profitable_after_a_reversal():
    """Kullanıcının anlattığı TAM senaryo: pozisyon büyük kâra ulaşıyor,
    piyasa tersine dönüyor — pozisyon artık ZARARA değil, hâlâ KÂRLI bir
    seviyede (trailing stop) kapanmalı. Bu, breakeven'in TEK BAŞINA
    çözemediği asıl sorun (girişe çekilen stop sadece $0 verirdi)."""
    from contracts.decision_event import DecisionEvent

    symbol = f"POSTRAILCLS{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    entry, old_stop, target = 100.0, 90.0, 200.0

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=entry, quantity=1.0, opened_at=now,
            stop_loss_price=old_stop, take_profit_price=target,
        )
        DecisionPersistor(session).persist(event)

    closer_step1 = PositionCloser(_FixedPriceProvider(130.0))  # stop -> 125
    with SessionFactory.get_session() as session:
        closer_step1.close_due_positions(DecisionPersistor(session))

    # Piyasa tersine dönüyor, yeni (sıkı) stopun (125) altına düşüyor.
    closer_step2 = PositionCloser(_FixedPriceProvider(124.0))
    with SessionFactory.get_session() as session:
        closed = closer_step2.close_due_positions(DecisionPersistor(session))

    closed_ids = {c["decision_id"]: c for c in closed}
    assert str(event.id) in closed_ids

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "closed"
    assert row["pnl"] > 0  # HÂLÂ KÂRLI kapandı — eski davranışta bu zarar olurdu


def test_trailing_stop_disabled_when_distance_pct_is_zero():
    """trailing_stop_distance_pct=0 ile trailing tamamen kapalı —
    SADECE breakeven (girişe çekme) çalışmalı, mevcut davranış
    (Faz 268ae) hiç değişmemeli."""
    from contracts.decision_event import DecisionEvent
    from database.repositories.app_settings_repository import AppSettingsRepository

    symbol = f"POSTRAILOFF{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    entry, old_stop, target = 100.0, 90.0, 200.0

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=entry, quantity=1.0, opened_at=now,
            stop_loss_price=old_stop, take_profit_price=target,
        )
        DecisionPersistor(session).persist(event)
        AppSettingsRepository(session).set("trailing_stop_distance_pct", "0", updated_by="test")

    try:
        closer = PositionCloser(_FixedPriceProvider(130.0))
        with SessionFactory.get_session() as session:
            closer.close_due_positions(DecisionPersistor(session))

        with SessionFactory.get_session() as session:
            row = DecisionPersistor(session).get_by_id(str(event.id))
        assert row["stop_loss_price"] == entry  # SADECE breakeven, 125 DEĞİL
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("trailing_stop_distance_pct", "0.05", updated_by="test")


def test_take_profit_exit_is_charged_the_cheaper_maker_fee_not_taker():
    """Faz 223: kullanıcı isteği — "işlem ücretlerinden kurtulmanın ya da
    minimize etmenin yolları var mı." Gerçek bulgu: çıkış her zaman taker
    oranıyla ücretlendiriliyordu. take_profit çıkışı gerçekte hedef
    fiyata önceden oturmuş bir LIMIT emrinin dolmasıdır — gerçek
    borsalarda "maker" (%0.02, taker'ın %0.05'inden ucuz) sayılır."""
    from contracts.decision_event import DecisionEvent
    from simulator.fee_engine import FeeConfig

    entry, target = 100.0, 110.0
    qty = 1.0
    cfg = FeeConfig()
    expected_fee = entry * qty * cfg.taker_rate + target * qty * cfg.maker_rate

    symbol = f"POSTPFEE{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=qty, confidence=0.7,
            status="open", entry_price=entry, quantity=qty, opened_at=now,
            stop_loss_price=90.0, take_profit_price=target,
        )
        DecisionPersistor(session).persist(event)

    closer = PositionCloser(_FixedPriceProvider(target))
    with SessionFactory.get_session() as session:
        closer.close_due_positions(DecisionPersistor(session))

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["outcome"]["fee"] == pytest.approx(expected_fee)


def test_stop_loss_exit_is_still_charged_full_taker_fee_on_both_legs():
    from contracts.decision_event import DecisionEvent
    from simulator.fee_engine import FeeConfig

    entry, stop = 100.0, 90.0
    qty = 1.0
    cfg = FeeConfig()
    expected_fee = entry * qty * cfg.taker_rate + stop * qty * cfg.taker_rate

    symbol = f"POSSLFEE{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=qty, confidence=0.7,
            status="open", entry_price=entry, quantity=qty, opened_at=now,
            stop_loss_price=stop, take_profit_price=110.0,
        )
        DecisionPersistor(session).persist(event)

    closer = PositionCloser(_FixedPriceProvider(stop))
    with SessionFactory.get_session() as session:
        closer.close_due_positions(DecisionPersistor(session))

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["outcome"]["fee"] == pytest.approx(expected_fee)


def test_position_closer_does_not_close_when_price_between_stop_and_target_and_hold_not_expired():
    from contracts.decision_event import DecisionEvent

    symbol = f"POSNOTRIGGER{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=90.0, take_profit_price=110.0,
        )
        DecisionPersistor(session).persist(event)

    closer = PositionCloser(_FixedPriceProvider(103.0), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    assert str(event.id) not in {c["decision_id"] for c in closed}

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "open"


def test_position_closer_skips_close_when_current_price_is_implausibly_far_from_entry():
    """Faz 239: kritik bulgu — MARKET_DATA_FALLBACK_TO_MOCK=True iken gerçek
    Binance isteği başarısız olunca BinanceProvider sessizce sembolden
    bağımsız ~$50,000 mock fiyata düşüyordu. Gerçek örnek: ADAUSDT pozisyonu
    (entry_price=$0.202) bu sahte fiyatla "take_profit"a ulaştı sanılıp
    $9.9 milyon hayali kâr kaydetti — hem PnL gösterimini hem
    _record_agent_learning() üzerinden ajan öğrenme sinyalini kirletti.
    Bu test, entry_price'a göre 20 kattan fazla sapan bir "güncel fiyat"ın
    (bu senaryodaki gibi bir BTC-ölçekli mock fiyatın gerçek bir ADAUSDT
    pozisyonuna sızması) pozisyonu KAPATMADIĞINI kanıtlıyor — ne stop ne de
    target tetiklenmiş gibi davranılmamalı, pozisyon açık kalmalı."""
    from contracts.decision_event import DecisionEvent

    symbol = f"POSFAKEPRICE{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=0.202, quantity=198.91, opened_at=now,
            stop_loss_price=0.19, take_profit_price=0.22,
        )
        DecisionPersistor(session).persist(event)

    # Gerçek bug'daki tam senaryo: entry $0.202 iken sağlayıcı BTC-ölçekli
    # $49,855.91 döndürüyor (>100,000x sapma) — take_profit'in çok üzerinde,
    # ama gerçek bir ADAUSDT fiyat hareketi olamaz.
    closer = PositionCloser(_FixedPriceProvider(49855.91), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    assert str(event.id) not in {c["decision_id"] for c in closed}

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "open"
    assert row["pnl"] is None


def test_position_closer_skips_close_when_market_is_closed(monkeypatch):
    """Faz 244: kritik bulgu — MSFT/NVDA/AAPL gibi hisse pozisyonları piyasa
    kapalıyken (gece/hafta sonu) bile her dakika kontrol ediliyordu;
    YahooProvider bu durumda hata vermek yerine GERÇEK ama SAATLERCE BAYAT
    (dünün kapanışı) bir fiyat döndürüyor, bu "şu anki fiyat" gibi
    kullanılıyordu. Bu test, piyasa kapalıyken (is_market_open=False) fiyat
    stop/target'ı tetiklese bile pozisyonun KAPANMADIĞINI kanıtlıyor."""
    import services.position_closer as position_closer_module
    from contracts.decision_event import DecisionEvent

    monkeypatch.setattr(position_closer_module, "is_market_open", lambda symbol, now=None: False)

    symbol = f"MSFT{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=90.0, take_profit_price=110.0,
        )
        DecisionPersistor(session).persist(event)

    # 111.0, take_profit'in (110.0) üzerinde — piyasa açık olsaydı kapanırdı.
    closer = PositionCloser(_FixedPriceProvider(111.0), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    assert str(event.id) not in {c["decision_id"] for c in closed}

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "open"


def test_position_closer_still_closes_on_legitimate_large_but_plausible_move():
    """Güvenlik kontrolü meşru büyük hareketleri (ör. gerçek bir küçük-cap
    coin'in %50 pump/dump yapması) yanlışlıkla reddetmemeli — sadece
    20 kat ve üstü ölçek sıçramalarını (mock-fiyat sızıntısının imzası)
    reddetmeli."""
    from contracts.decision_event import DecisionEvent

    symbol = f"POSREALMOVE{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=90.0, take_profit_price=110.0,
        )
        DecisionPersistor(session).persist(event)

    # %11 gerçek bir hareket — reddedilmemeli, normal şekilde take_profit'e ulaşmalı.
    closer = PositionCloser(_FixedPriceProvider(111.0), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    assert str(event.id) in {c["decision_id"] for c in closed}


def test_position_closer_closes_at_liquidation_price_before_stop_loss_for_leveraged_position():
    """Faz 255: kullanıcı isteği — kaldıraç desteği. Kaldıraçlı bir
    pozisyon gerçek likidasyon fiyatına stop_loss'tan ÖNCE ulaşırsa,
    sistem bunu "liquidation" olarak açıkça etiketleyip kapatmalı —
    stop_loss ile karışmamalı, likidasyonu görmezden gelmemeli."""
    from contracts.decision_event import DecisionEvent
    from simulator.margin import compute_liquidation_price

    symbol = f"POSLIQ{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    leverage = 10.0
    liquidation_price = compute_liquidation_price(100.0, "LONG", leverage=leverage)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=80.0, take_profit_price=120.0,  # geniş stop — likidasyon önce tetiklenmeli
            leverage=leverage, liquidation_price=liquidation_price,
        )
        DecisionPersistor(session).persist(event)

    # Fiyat likidasyon seviyesinin altına düştü ama stop_loss'a (80) henüz ulaşmadı.
    closer = PositionCloser(_FixedPriceProvider(liquidation_price - 0.5), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    closed_ids = {c["decision_id"]: c for c in closed}
    assert str(event.id) in closed_ids
    assert closed_ids[str(event.id)]["exit_reason"] == "liquidation"

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["exit_price"] == liquidation_price


def test_position_closer_ignores_liquidation_for_spot_position():
    """leverage=1.0 (spot) bir pozisyonda liquidation_price None olmalı —
    likidasyon kavramı kaldıraçsız pozisyonda geçersiz, hiçbir fiyat
    hareketi "liquidation" olarak kapatmamalı."""
    from contracts.decision_event import DecisionEvent

    symbol = f"POSSPOT{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            stop_loss_price=90.0, take_profit_price=110.0,
            leverage=1.0, liquidation_price=None,
        )
        DecisionPersistor(session).persist(event)

    # Fiyat stop/target arasında — hiçbir sebeple kapanmamalı.
    closer = PositionCloser(_FixedPriceProvider(95.0), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    assert str(event.id) not in {c["decision_id"] for c in closed}


def test_excluded_from_stats_position_does_not_pollute_agent_learning_on_close():
    """Faz 282 — kritik bulgu (2026-08-19, kullanıcı: "ajanları da çok
    rahat yanıltır bu veri"): excluded_from_stats=true işaretli kararlar
    (ör. faz279/280/281'de bilinen bug'lardan kirlenmiş diye işaretlenen
    pump_fade/scalp/hedge pozisyonları) dashboard/istatistik sorgularının
    hepsinde hariç tutuluyordu ama _record_agent_learning() bu bayrağı
    hiç kontrol etmiyordu — kapandıklarında hâlâ AgentMemory'ye (ve
    oradan WeightOptimizer/SourceReliabilityAgent öğrenmesine) sızıyordu.
    reliability_legacy_cutoff_at SADECE decision_opened_at'e göre zaman
    tabanlı filtreliyor — kesimden SONRA açılıp bilinen bir bug'dan
    etkilenen (excluded_from_stats=true) bir kararı yakalamıyor."""
    from contracts.decision_event import DecisionEvent
    from sqlalchemy import text

    symbol = f"POSEXCLLRN{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
        stop_loss_price=90.0, take_profit_price=110.0,
        agent_opinions=[{"domain": "technical", "direction": "LONG", "confidence": 0.6}],
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
        session.execute(
            text("UPDATE decisions SET excluded_from_stats = true WHERE id = :id"),
            {"id": str(event.id)},
        )
        session.commit()

    closer = PositionCloser(_FixedPriceProvider(110.0), hold_seconds=3600)
    from unittest.mock import patch
    with patch.object(closer.agent_memory, "record") as record_spy:
        with SessionFactory.get_session() as session:
            closed = closer.close_due_positions(DecisionPersistor(session))

    assert str(event.id) in {c["decision_id"] for c in closed}
    assert not record_spy.called
