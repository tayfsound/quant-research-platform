"""Faz 187: gerçek pozisyon yaşam döngüsü — açılış (DecisionRecorder)
ve kapanış (PositionCloser), backtest tarzı anlık ForwardOutcome'dan ayrı."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.position_closer import PositionCloser


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
