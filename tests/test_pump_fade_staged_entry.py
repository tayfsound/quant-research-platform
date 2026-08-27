"""pump_fade Kademeli Giriş (Staged Entry) testleri — Faz 364.

Kullanıcı fikri, gerçek Binance verisiyle kalibre edildi (43 sembol, 250
gün, 15 bağımsız +%50 pump olayı): dip-bazlı %50'de hedefin %25'i açılır
(düşük kaldıraç, stop'a mesafe uzak); dip-bazlı %80'e ulaşırsa 3 katı
büyüyüp %100'e tamamlanır (bu ikinci bacak, add-stop mesafesi çok yakın
olduğu için yüksek kaldıraç kaldırabilir); ortak stop dip-bazlı %90'da —
örneklemde HİÇ ulaşılmayan (0/11) bir seviye."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.risk_limit_repository import RiskLimitModel, RiskLimitRepository
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.pump_fade_strategy import EXPERIMENT_BUCKET, PumpFadeStrategy


def _cleanup_symbol(symbol: str) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
        session.commit()


def _cleanup_max_position_size() -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM risk_limits WHERE limit_type = 'max_position_size'"))
        session.commit()


def _bar(low: float, close: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime.now(UTC), open=close, high=max(low, close), low=low, close=close, volume=1.0
    )


def _pump_then_settled_bars(low: float, peak: float, flat_bars: int = 7) -> list[OHLCV]:
    bars = [_bar(low, low), _bar(low, peak)]
    bars += [_bar(peak, peak) for _ in range(flat_bars)]
    return bars


class _FakeProvider:
    def __init__(self, bars_by_symbol: dict):
        self.bars_by_symbol = bars_by_symbol

    def get_ohlcv(self, symbol, timeframe, limit=100):
        return self.bars_by_symbol.get(symbol, [])


def _set_settings(**overrides) -> None:
    defaults = {
        "pump_fade_enabled": "true",
        "pump_fade_max_loss_per_trade_usd": "100",
        "pump_fade_max_open_positions": "1000",
        "pump_fade_leverage": "10",
        "pump_fade_min_gain_pct": "0.25",
        "pump_fade_lookback_hours": "48",
        "pump_fade_stop_distance_pct": "0.15",
        "pump_fade_take_profit_pct": "0.25",
        "starting_capital": "100000",
        "pump_fade_max_total_capital_pct": "1000000",
        "pump_fade_reentry_min_gain_pct": "0.50",
        "pump_fade_staged_entry_enabled": "true",
        "pump_fade_staged_entry_first_leg_pct": "0.25",
        "pump_fade_staged_entry_add_trigger_gain_pct": "0.80",
        "pump_fade_staged_entry_stop_gain_pct": "0.90",
        # Faz 367-devam — bkz. test_pump_fade_strategy.py::_set_pump_fade_
        # settings'teki AYNI düzeltmenin gerekçesi: legacy_cutoff_at boşken
        # circuit breaker paylaşılan quantdb_test'in TÜM geçmişini
        # topluyordu, tam paket çalışırken sessizce tetikleniyordu.
        "pump_fade_circuit_breaker_legacy_cutoff_at": datetime.now(UTC).isoformat(),
    }
    defaults.update(overrides)
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key, value in defaults.items():
            repo.set(key, value, updated_by="test")
    _cleanup_max_position_size()


@pytest.fixture(autouse=True)
def _reset_staged_entry_setting_after_test():
    """pump_fade_staged_entry_enabled paylaşılan test DB'sinde kalıcı —
    bu dosyanın testleri bitince "kapalı" varsayılanına döner, aksi halde
    test_pump_fade_strategy.py gibi başka test dosyalarına sızabilir."""
    yield
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("pump_fade_staged_entry_enabled", "false", updated_by="test")


def test_run_cycle_opens_staged_first_leg_when_enabled(monkeypatch):
    """dip=10, current=15 (gain_pct=%50) — ilk bacak açılmalı, tam boyut
    DEĞİL (hedefin %25'i), staged_entry_add_pending=True, staged_entry_
    low_price=10 olarak kaydedilmeli."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_settings()
        monkeypatch.setattr("services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol])
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 15.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert len(result["opened"]) == 1
        assert result["opened"][0]["staged"] == "first_leg"

        with SessionFactory.get_session() as session:
            row = session.execute(
                text(
                    "SELECT status, quantity, leverage, stop_loss_price, staged_entry_add_pending, "
                    "staged_entry_low_price FROM decisions WHERE symbol = :s"
                ),
                {"s": symbol},
            ).mappings().one()
        assert row["status"] == "open"
        assert row["staged_entry_add_pending"] is True
        assert row["staged_entry_low_price"] == pytest.approx(10.0)
        # Ortak stop dip-bazlı %90: 10 * 1.90 = 19.0
        assert row["stop_loss_price"] == pytest.approx(19.0)
        # Stop mesafesi entry'ye (15) göre (19-15)/15 = %26.67 -> güvenli
        # kaldıraç ~2.47x, hedef 10x'in ALTINDA kırpılmalı.
        assert row["leverage"] < 10.0
    finally:
        _cleanup_symbol(symbol)


def test_run_cycle_opens_normal_single_shot_when_staged_disabled(monkeypatch):
    """Regresyon: staged_entry kapalıyken davranış birebir eskisi gibi
    kalmalı — tek seferde tam boyut, staged alanları None."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_settings(pump_fade_staged_entry_enabled="false")
        monkeypatch.setattr("services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol])
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 15.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert len(result["opened"]) == 1
        assert "staged" not in result["opened"][0]
        with SessionFactory.get_session() as session:
            row = session.execute(
                text("SELECT staged_entry_add_pending, staged_entry_low_price FROM decisions WHERE symbol = :s"),
                {"s": symbol},
            ).mappings().one()
        assert row["staged_entry_add_pending"] is None
        assert row["staged_entry_low_price"] is None
    finally:
        _cleanup_symbol(symbol)


def _open_staged_first_leg(symbol: str, low: float, entry_price: float) -> str:
    """Testler için doğrudan bir 'ilk bacak' pozisyonu kurar (run_cycle'ı
    tekrar tetiklemeden) — add-tetiği testlerinin odağı sadece
    try_apply_staged_adds() olsun diye."""
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction="SHORT", final_action="SHORT", final_size=1.0, confidence=0.0,
        status="open", entry_price=entry_price, quantity=10.0, opened_at=now,
        stop_loss_price=low * 1.90, take_profit_price=entry_price * 0.75, leverage=2.0,
        experiment_bucket=EXPERIMENT_BUCKET,
        staged_entry_add_pending=True, staged_entry_low_price=low,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return str(event.id)


def test_try_apply_staged_adds_noop_when_disabled():
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _open_staged_first_leg(symbol, low=10.0, entry_price=15.0)
        _set_settings(pump_fade_staged_entry_enabled="false")

        added = PumpFadeStrategy(data_provider=_FakeProvider({})).try_apply_staged_adds()
        assert added == []
    finally:
        _cleanup_symbol(symbol)


def test_try_apply_staged_adds_noop_below_trigger():
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _open_staged_first_leg(symbol, low=10.0, entry_price=15.0)
        _set_settings()
        # gain_pct_now = (17-10)/10 = %70 < add_trigger (%80)
        provider = _FakeProvider({symbol: [_bar(17.0, 17.0)]})

        added = PumpFadeStrategy(data_provider=provider).try_apply_staged_adds()
        assert added == []
        with SessionFactory.get_session() as session:
            pending = session.execute(
                text("SELECT staged_entry_add_pending FROM decisions WHERE symbol = :s"), {"s": symbol}
            ).scalar()
        assert pending is True  # hâlâ bekliyor, tetiklenmedi
    finally:
        _cleanup_symbol(symbol)


def test_try_apply_staged_adds_opens_add_leg_and_uses_higher_leverage(monkeypatch):
    """Gerçek veriyle kalibre edilen kritik iddia: ekleme bacağı, ilk
    bacaktan DAHA YÜKSEK güvenli kaldıraç kullanabilmeli (ortak stop'a
    mesafesi çok daha yakın olduğu için)."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        first_leg_id = _open_staged_first_leg(symbol, low=10.0, entry_price=15.0)
        _set_settings()
        # gain_pct_now = (18-10)/10 = %80 -> tam add tetiğinde
        provider = _FakeProvider({symbol: [_bar(18.0, 18.0)]})

        added = PumpFadeStrategy(data_provider=provider).try_apply_staged_adds()

        assert len(added) == 1
        assert added[0]["staged"] == "add_leg"
        # Ortak stop hâlâ 10*1.90=19.0, add entry=18 -> mesafe (19-18)/18=%5.56
        assert added[0]["stop_loss_price"] == pytest.approx(19.0)
        assert added[0]["leverage"] > 5.0  # ~11.3x güvenli tavan, 10x hedefin altında kalır ama yüksek

        with SessionFactory.get_session() as session:
            first_leg_pending = session.execute(
                text("SELECT staged_entry_add_pending FROM decisions WHERE id = :id"), {"id": first_leg_id}
            ).scalar()
            open_count = session.execute(
                text("SELECT count(*) FROM decisions WHERE symbol = :s AND status = 'open'"), {"s": symbol}
            ).scalar()
        assert first_leg_pending is False  # bir daha eklenmeyecek
        assert open_count == 2  # ilk bacak + ekleme, iki AYRI pozisyon
    finally:
        _cleanup_symbol(symbol)


def test_try_apply_staged_adds_marks_added_without_opening_when_price_already_past_stop():
    """Fiyat pencereler arası zıplayıp ortak stop'u add-tetiğiyle AYNI anda
    geçmişse: yeni bir bacak AÇILMAMALI (mantıksız, negatif/sıfır stop
    mesafesi), ama pending bayrağı yine de kapatılmalı (ilk bacak kendi
    stop'una PositionCloser tarafından bırakılıyor)."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        first_leg_id = _open_staged_first_leg(symbol, low=10.0, entry_price=15.0)
        _set_settings()
        # gain_pct_now = (20-10)/10 = %100, stop (19.0) ZATEN geçilmiş.
        provider = _FakeProvider({symbol: [_bar(20.0, 20.0)]})

        added = PumpFadeStrategy(data_provider=provider).try_apply_staged_adds()

        assert added == []
        with SessionFactory.get_session() as session:
            pending = session.execute(
                text("SELECT staged_entry_add_pending FROM decisions WHERE id = :id"), {"id": first_leg_id}
            ).scalar()
            open_count = session.execute(
                text("SELECT count(*) FROM decisions WHERE symbol = :s AND status = 'open'"), {"s": symbol}
            ).scalar()
        assert pending is False
        assert open_count == 1  # ikinci bir bacak açılmadı
    finally:
        _cleanup_symbol(symbol)


def test_staged_legs_split_total_risk_budget_between_them(monkeypatch):
    """max_loss_per_trade_usd tam olarak first_leg_pct'e göre bölünmeli —
    ikisi toplamda normal (kademesiz) bir işlemle AYNI $ risk tavanını
    taşımalı (yoğunluk/rejim çarpanları 1.0 olduğunda)."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_settings(pump_fade_max_loss_per_trade_usd="100", pump_fade_staged_entry_first_leg_pct="0.25")
        monkeypatch.setattr("services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol])
        monkeypatch.setattr("services.pump_fade_strategy._compute_density_size_multiplier", lambda *a, **k: 1.0)
        monkeypatch.setattr("services.pump_fade_strategy._compute_regime_size_multiplier", lambda *a, **k: 1.0)
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 15.0)})

        PumpFadeStrategy(data_provider=provider).run_cycle()

        with SessionFactory.get_session() as session:
            row = session.execute(
                text("SELECT entry_price, stop_loss_price, quantity, leverage FROM decisions WHERE symbol = :s"),
                {"s": symbol},
            ).mappings().one()
        stop_distance_pct = (row["stop_loss_price"] - row["entry_price"]) / row["entry_price"]
        # notional (quantity*entry_price) = margin*leverage -> stop'ta
        # kaybedilen $ = notional * stop_distance_pct (leverage zaten
        # notional'ın içinde, ayrıca çarpılmaz).
        implied_max_loss = row["quantity"] * row["entry_price"] * stop_distance_pct
        assert implied_max_loss == pytest.approx(25.0, rel=0.01)  # 100 * 0.25
    finally:
        _cleanup_symbol(symbol)
