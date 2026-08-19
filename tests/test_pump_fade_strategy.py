"""Pump-Fade Strategy testleri — bkz. services/pump_fade_strategy.py.
Kullanıcı isteği: AI konsey/confidence sisteminden tamamen yalıtık, test
amaçlı mekanik bir strateji ("son iki günde %100 yapmış coinleri short'la,
kasanın %5'i kadar 5x pozisyona gir, %100 kâr ettiğinde çık")."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.risk_limit_repository import RiskLimitModel, RiskLimitRepository
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.pump_fade_strategy import (
    EXPERIMENT_BUCKET,
    PumpFadeStrategy,
    _compute_density_size_multiplier,
    find_pump_candidates,
)


def _seed_max_position_size(value: float) -> None:
    with SessionFactory.get_session() as session:
        RiskLimitRepository(session).save(RiskLimitModel(
            id=uuid4(), scope="global", limit_type="max_position_size",
            value=value, hash="", created_by="test", created_at=datetime.now(UTC),
        ))


def _bar(low: float, close: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime.now(UTC), open=close, high=max(low, close), low=low, close=close, volume=1.0
    )


def _pump_then_settled_bars(low: float, peak: float, flat_bars: int = 7) -> list[OHLCV]:
    """Faz 292 — pump + ardından TOPARLANMAMIŞ, yatay bir dönem: yeni
    giriş-zamanlaması filtrelerinin (zirve yakınlığı + kısa-vadeli momentum
    teyidi) hâlâ geçmesi için gerçekçi bir fixture. Sadece iki bar'lık ham
    "pump" fixture'ı (eski testler) momentum penceresiyle ÇAKIŞIYORDU —
    fiyat zaten "toparlanmış" gibi okunuyordu, oysa asıl senaryo tam tersi
    (fiyat hâlâ zirvede/yatay, henüz geri dönmemiş)."""
    bars = [_bar(low, low), _bar(low, peak)]
    bars += [_bar(peak, peak) for _ in range(flat_bars)]
    return bars


# Faz 292 varsayılanları — testlerde find_pump_candidates'e doğrudan
# geçirilen giriş-zamanlaması parametreleri (gevşek: eski davranışı
# olabildiğince koruyacak şekilde, asıl davranış _set_pump_fade_settings
# üzerinden AppSettings'ten okunuyor).
_PEAK_WINDOW_HOURS = 72
_MAX_PULLBACK_FROM_PEAK_PCT = 0.08
_MOMENTUM_CONFIRMATION_HOURS = 6
_MOMENTUM_TOLERANCE_PCT = 0.01


class _FakeProvider:
    def __init__(self, bars_by_symbol: dict):
        self.bars_by_symbol = bars_by_symbol

    def get_ohlcv(self, symbol, timeframe, limit=100):
        return self.bars_by_symbol.get(symbol, [])


def _cleanup_symbol(symbol: str) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
        session.commit()


def _cleanup_max_position_size() -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM risk_limits WHERE limit_type = 'max_position_size'"))
        session.commit()


def _cleanup_density_events() -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM system_events WHERE event_type = 'pump_fade_candidate_density'"))
        session.commit()


def _set_pump_fade_settings(**overrides) -> None:
    defaults = {
        "pump_fade_enabled": "false",
        "pump_fade_capital_pct": "0.05",
        "pump_fade_leverage": "5",
        "pump_fade_min_gain_pct": "1.0",
        "pump_fade_lookback_hours": "48",
        "pump_fade_stop_distance_pct": "0.15",
        "starting_capital": "1000",
    }
    defaults.update(overrides)
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key, value in defaults.items():
            repo.set(key, value, updated_by="test")

    # Kullanıcı bulgusu — tam paket çalışırken (tek başına değil) bu
    # dosyadaki bir test başarısız oluyordu: risk_limits tablosu TÜM test
    # dosyaları arasında paylaşılıyor (ör. test_orchestrator_risk_limits.py
    # kendi max_position_size=1.0 satırını hiç temizlemiyor) — pump_fade_
    # strategy.py artık bu AYNI global max_position_size'ı okuduğu için
    # (bkz. _try_open'daki güvenlik tavanı kontrolü), başka bir test
    # dosyasından kalan bir satır burayı sessizce etkileyebiliyordu. Her
    # pump-fade testi "limit yok" temiz durumuyla başlasın diye burada
    # temizleniyor — bir test kendi limitini seçmek isterse _seed_max_
    # position_size'ı BUNDAN SONRA çağırır.
    _cleanup_max_position_size()


def _find_candidates(symbols, provider, lookback_hours=48, min_gain_pct=1.0):
    return find_pump_candidates(
        symbols, provider, lookback_hours, min_gain_pct,
        _PEAK_WINDOW_HOURS, _MAX_PULLBACK_FROM_PEAK_PCT,
        _MOMENTUM_CONFIRMATION_HOURS, _MOMENTUM_TOLERANCE_PCT,
    )


def test_find_pump_candidates_identifies_symbol_meeting_gain_threshold():
    provider = _FakeProvider({
        "PUMPUSDT": _pump_then_settled_bars(10.0, 22.0),  # low=10, current=22 -> %120 kazanç
        "FLATUSDT": [_bar(10.0, 10.0), _bar(10.0, 10.5)],  # %5 kazanç, eşiğin altında
    })
    candidates = _find_candidates(["PUMPUSDT", "FLATUSDT"], provider)
    assert {c["symbol"] for c in candidates} == {"PUMPUSDT"}
    assert candidates[0]["gain_pct"] == pytest.approx(1.2)


def test_find_pump_candidates_skips_symbols_when_fetch_fails():
    class _BrokenProvider:
        def get_ohlcv(self, symbol, timeframe, limit=100):
            raise RuntimeError("network down")

    candidates = _find_candidates(["BROKENUSDT"], _BrokenProvider())
    assert candidates == []


def test_find_pump_candidates_skips_symbols_with_insufficient_bars():
    provider = _FakeProvider({"THINUSDT": [_bar(10.0, 20.0)]})
    candidates = _find_candidates(["THINUSDT"], provider)
    assert candidates == []


def test_find_pump_candidates_rejects_when_price_already_pulled_back_from_peak():
    """Faz 292 — kullanıcı bulgusu (gerçek CHIPUSDT örneği): fiyat zirveden
    izin verilen tavanın (varsayılan %8) ötesinde geri çekilmişse, gain_pct
    eşiği hâlâ geçse bile giriş olmamalı — "geç kalınmış" pump."""
    # Zirve 30, sonra %20 geri çekilip 24'te yatay kalmış (izin verilen
    # %8'in çok üstünde bir pullback).
    bars = [_bar(10.0, 10.0), _bar(10.0, 30.0)] + [_bar(24.0, 24.0) for _ in range(7)]
    provider = _FakeProvider({"LATEUSDT": bars})
    candidates = _find_candidates(["LATEUSDT"], provider)
    assert candidates == []


def test_find_pump_candidates_rejects_when_short_term_momentum_already_reversed():
    """Faz 292 — fiyat zirveye yakın kalsa bile son birkaç saatte ZATEN
    net yukarı toparlanmaya başlamışsa (momentum_tolerance_pct'i aşan bir
    hareket) giriş olmamalı — CHIPUSDT'de tam olan buydu."""
    # Zirve 22'de, ardından yatay, SON 3 barda momentum toleransının (%1)
    # çok üstünde bir sıçrama (22 -> 24, ~%9).
    bars = [_bar(10.0, 10.0), _bar(10.0, 22.0)] + [_bar(22.0, 22.0) for _ in range(4)] + [
        _bar(22.0, 23.0), _bar(22.5, 23.5), _bar(23.0, 24.0),
    ]
    provider = _FakeProvider({"BOUNCEDUSDT": bars})
    candidates = _find_candidates(["BOUNCEDUSDT"], provider)
    assert candidates == []


def test_run_cycle_skipped_when_disabled():
    _set_pump_fade_settings(pump_fade_enabled="false")
    result = PumpFadeStrategy(data_provider=_FakeProvider({})).run_cycle()
    assert result == {"skipped": "pump_fade_disabled"}


def test_run_cycle_opens_short_position_with_leverage_clamped_by_safety_lock(monkeypatch):
    """Varsayılan pump_fade_stop_distance_pct=0.15 ile max_safe_leverage
    hedef 5x'i ~4.35x'e kırpmalı — kullanıcının onayladığı güvenlik kilidi
    gerçekten uygulanıyor mu?"""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert result["candidates_found"] == 1
        assert len(result["opened"]) == 1
        opened = result["opened"][0]
        assert opened["symbol"] == symbol
        assert 4.0 < opened["leverage"] < 5.0  # kırpılmış, ama 5x'e yakın

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions(limit=50)
        row = next(r for r in rows if r["symbol"] == symbol)
        assert row["direction"] == "SHORT"
        assert row["experiment_bucket"] == EXPERIMENT_BUCKET
        assert row["leverage"] == pytest.approx(opened["leverage"])
        # Güvenlik: likidasyon her zaman stop'tan daha uzakta kalmalı
        # (SHORT'ta ikisi de fiyatın YUKARI gitmesiyle tetiklenir).
        assert row["liquidation_price"] > row["stop_loss_price"] > row["entry_price"]
        # Çıkış kuralı: "%100 kâr ettiğinde" -> fiyat AŞAĞI inince kâr.
        assert row["take_profit_price"] < row["entry_price"]
        assert row["quantity"] > 0
    finally:
        _cleanup_symbol(symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_clamps_leverage_when_notional_would_exceed_max_position_size(monkeypatch):
    """Kullanıcı bulgusu — gerçek olay: PORTALUSDT'de $25.000 marjin ×
    4,35x kaldıraç = $108.695 notional açıldı, ama RiskEngine'in gerçek
    max_position_size tavanı $100.000'di; bu strateji izole olduğu için
    hiç kontrol edilmemişti. margin=$50, hedef kaldıraç güvenlik kilidiyle
    ~4.35x'e kırpılır (varsayılan %15 stop mesafesi) -> kırpılmamış
    notional ~$217.4. max_position_size=$100 verilince kaldıraç 100/50=2.0'a
    kırpılmalı."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        _seed_max_position_size(100.0)
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert len(result["opened"]) == 1
        opened = result["opened"][0]
        assert opened["leverage"] == pytest.approx(2.0)

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions(limit=50)
        row = next(r for r in rows if r["symbol"] == symbol)
        notional = row["quantity"] * row["entry_price"]
        assert notional == pytest.approx(100.0, rel=1e-3)
    finally:
        _cleanup_symbol(symbol)
        _cleanup_max_position_size()
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_does_not_open_position_when_margin_alone_exceeds_max_position_size(monkeypatch):
    """Margin (1x kaldıraçta bile) tavanı aşıyorsa pozisyon HİÇ açılmamalı
    — "sinyal limitleri gevşetemez, sadece küçültebilir/reddedebilir"
    ilkesi, kırpmanın bir noktadan sonra anlamsız kaldığı durum."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        _seed_max_position_size(25.0)  # margin=$50 > $25 tavanı, 1x'te bile sığmaz
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert result["opened"] == []
        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions(limit=50)
        assert not any(r["symbol"] == symbol for r in rows)
    finally:
        _cleanup_symbol(symbol)
        _cleanup_max_position_size()
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_take_profit_is_independent_of_leverage(monkeypatch):
    """Kullanıcı bulgusu: eski kural take_profit = entry*(1-1/leverage)
    idi — stop mesafesi genişleyip güvenlik kilidi leverage'ı düşürünce bu
    ham hedef SESSİZCE kayardı (198 gerçek pump olayında ölçülen en iyi
    ham hedeften, %25'ten, uzaklaşırdı). Artık pump_fade_take_profit_pct
    doğrudan kullanılıyor — leverage ne olursa olsun (burada geniş stopla
    düşük bir leverage'a zorlanıyor) ham hedef SABİT kalmalı."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(
            pump_fade_enabled="true",
            pump_fade_stop_distance_pct="0.30",  # leverage'ı düşüğe zorlar
            pump_fade_take_profit_pct="0.25",
        )
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert len(result["opened"]) == 1
        opened = result["opened"][0]
        assert opened["leverage"] < 3.0  # %30 stopla leverage düşük olmalı (eski 1/leverage ~%45 hedef verirdi)

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions(limit=50)
        row = next(r for r in rows if r["symbol"] == symbol)
        entry = row["entry_price"]
        expected_tp = entry * (1 - 0.25)
        assert row["take_profit_price"] == pytest.approx(expected_tp, rel=1e-6)
        # Eski formülle (1/leverage) hedef ~%45 olurdu — bunun ÇOK altında olmalı.
        old_formula_tp = entry * (1 - 1 / opened["leverage"])
        assert row["take_profit_price"] > old_formula_tp
    finally:
        _cleanup_symbol(symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_does_not_open_a_second_position_for_a_symbol_already_open(monkeypatch):
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})
        strategy = PumpFadeStrategy(data_provider=provider)

        first = strategy.run_cycle()
        second = strategy.run_cycle()

        assert len(first["opened"]) == 1
        assert len(second["opened"]) == 0
    finally:
        _cleanup_symbol(symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_does_not_raise_target_leverage_when_safety_lock_would_allow_more(monkeypatch):
    """AI'daki AYNI ilke: configured/hedef kaldıraç sadece bir TAVAN,
    güvenlik kilidi daha yüksek bir kaldıraca asla izin vermek için
    kullanılmaz (sadece sıkılaştırır, asla gevşetmez)."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true", pump_fade_stop_distance_pct="0.01")
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert result["opened"][0]["leverage"] == pytest.approx(5.0)
    finally:
        _cleanup_symbol(symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_list_closed_trades_exclude_experiment_bucket_filters_out_that_bucket_only():
    from datetime import UTC, datetime, timedelta

    from contracts.decision_event import DecisionEvent

    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    far_future = datetime.now(UTC) + timedelta(days=3650, hours=26)
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            ai_event = DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
            )
            repo.persist(ai_event)
            repo.close_position(decision_id=str(ai_event.id), exit_price=105.0, pnl=5.0, closed_at=far_future)

            pf_event = DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="SHORT", final_action="SHORT",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            )
            repo.persist(pf_event)
            repo.close_position(
                decision_id=str(pf_event.id), exit_price=90.0, pnl=10.0, closed_at=far_future + timedelta(seconds=1)
            )

            unfiltered = repo.list_closed_trades(limit=10)
            filtered = repo.list_closed_trades(limit=10, exclude_experiment_bucket=EXPERIMENT_BUCKET)

        unfiltered_symbols_ids = {str(r["id"]) for r in unfiltered if r["symbol"] == symbol}
        filtered_ids = {str(r["id"]) for r in filtered if r["symbol"] == symbol}
        assert unfiltered_symbols_ids == {str(ai_event.id), str(pf_event.id)}
        assert filtered_ids == {str(ai_event.id)}
    finally:
        _cleanup_symbol(symbol)


def test_has_open_position_for_experiment_reflects_real_open_positions():
    from contracts.decision_event import DecisionEvent

    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            assert repo.has_open_position_for_experiment(symbol, EXPERIMENT_BUCKET) is False
            repo.persist(DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="SHORT", final_action="SHORT",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            ))
            assert repo.has_open_position_for_experiment(symbol, EXPERIMENT_BUCKET) is True
            assert repo.has_open_position_for_experiment(symbol, "some_other_experiment") is False
    finally:
        _cleanup_symbol(symbol)


# Faz 295 — kullanıcı isteği (2026-08-19): gerçek geri-testte kayıpların
# çok sayıda sembolün AYNI ANDA pompalandığı haftalarda belirgin arttığı
# bulundu (BTC yönünden bağımsız). Kendi geçmişine göre (yüzdelik dilim)
# anormal yoğun cycle'larda margin otomatik küçülüyor.

def test_density_multiplier_is_1_when_history_insufficient():
    _cleanup_density_events()
    try:
        with SessionFactory.get_session() as session:
            multiplier = _compute_density_size_multiplier(session, candidates_found=500)
        assert multiplier == 1.0
    finally:
        _cleanup_density_events()


def test_density_event_records_btc_dominance_for_future_correlation_study():
    """Faz 306 — kullanıcı isteği: dominans/altseason verisi her cycle'da
    yoğunluk olayına EKLENİYOR (gözlem amaçlı) ama çarpan formülü henüz
    bunu KULLANMIYOR — bu test sadece kaydın gerçekten olduğunu doğruluyor.
    Ağ erişimi olmasa bile fail-closed None kabul edilebilir; anahtarın
    KENDİSİ her zaman payload'da bulunmalı."""
    from database.repositories.event_log_repository import EventLogRepository

    _cleanup_density_events()
    try:
        with SessionFactory.get_session() as session:
            _compute_density_size_multiplier(session, candidates_found=3)
            events = EventLogRepository(session).list_events(
                event_type="pump_fade_candidate_density", limit=1
            )
        assert len(events) == 1
        payload = events[0]["payload"]
        assert "btc_dominance_pct" in payload
        if payload["btc_dominance_pct"] is not None:
            assert 20.0 < payload["btc_dominance_pct"] < 95.0
    finally:
        _cleanup_density_events()


def test_density_multiplier_is_1_for_typical_density_with_sufficient_history():
    _cleanup_density_events()
    try:
        with SessionFactory.get_session() as session:
            for _ in range(60):
                _compute_density_size_multiplier(session, candidates_found=5)
            # Bu son çağrı hem kendi geçmişine ekleniyor hem de değerlendiriliyor —
            # tipik (5) bir değer, geçmişin üst %10'unda DEĞİL.
            multiplier = _compute_density_size_multiplier(session, candidates_found=5)
        assert multiplier == 1.0
    finally:
        _cleanup_density_events()


def test_density_multiplier_shrinks_at_extreme_density_relative_to_own_history():
    _cleanup_density_events()
    try:
        with SessionFactory.get_session() as session:
            for _ in range(60):
                _compute_density_size_multiplier(session, candidates_found=5)
            # Geçmişin TAMAMINDAN çok daha yüksek bir değer -> ~p99, tabana (0.5) yakın düşmeli.
            multiplier = _compute_density_size_multiplier(session, candidates_found=500)
        assert 0.5 <= multiplier < 0.6
    finally:
        _cleanup_density_events()


def test_density_multiplier_never_exceeds_1():
    _cleanup_density_events()
    try:
        with SessionFactory.get_session() as session:
            for _ in range(60):
                _compute_density_size_multiplier(session, candidates_found=50)
            # Geçmişin ortasında bir değer -> asla 1.0'ı aşmamalı (sadece küçültür).
            multiplier = _compute_density_size_multiplier(session, candidates_found=50)
        assert multiplier <= 1.0
    finally:
        _cleanup_density_events()


def test_try_open_applies_density_multiplier_to_margin(monkeypatch):
    """_try_open'a doğrudan verilen density_size_multiplier, açılan
    pozisyonun notional'ını orantılı küçültmeli."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        strategy = PumpFadeStrategy(data_provider=_FakeProvider({}))
        candidate = {
            "symbol": symbol, "current_price": 10.0, "gain_pct": 1.2,
            "pullback_from_peak_pct": 0.0, "momentum_pct": 0.0,
        }

        full = strategy._try_open(candidate, 0.05, 5.0, 0.15, 0.25, 1000.0, 48, density_size_multiplier=1.0)
        with SessionFactory.get_session() as session:
            row_full = DecisionPersistor(session).list_open_positions(limit=50)
        notional_full = next(r for r in row_full if r["symbol"] == symbol)["quantity"] * full["entry_price"]
        _cleanup_symbol(symbol)

        half = strategy._try_open(candidate, 0.05, 5.0, 0.15, 0.25, 1000.0, 48, density_size_multiplier=0.5)
        with SessionFactory.get_session() as session:
            row_half = DecisionPersistor(session).list_open_positions(limit=50)
        notional_half = next(r for r in row_half if r["symbol"] == symbol)["quantity"] * half["entry_price"]

        assert notional_half == pytest.approx(notional_full * 0.5, rel=1e-6)
    finally:
        _cleanup_symbol(symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_scales_margin_down_during_extreme_density(monkeypatch):
    """Uçtan uca: run_cycle, yüksek yoğunluk geçmişi varken küçültülmüş
    margin ile pozisyon açmalı ve density_size_multiplier'ı sonuçta
    raporlamalı."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    _cleanup_density_events()
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        # Geçmişi "her zaman tek aday" olacak şekilde doldur (tipik/düşük yoğunluk).
        with SessionFactory.get_session() as session:
            for _ in range(60):
                _compute_density_size_multiplier(session, candidates_found=1)

        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols",
            lambda: [symbol, f"OTHER{uuid4().hex[:6]}USDT"],
        )
        # 2 aday birden -> bu sembolün kendi geçmişine göre (hep 1 aday) anormal
        # yoğun sayılmayabilir (p90 eşiği), o yüzden burada asıl amaç sadece
        # density_size_multiplier alanının gerçekten raporlandığını doğrulamak.
        provider = _FakeProvider({
            symbol: _pump_then_settled_bars(10.0, 22.0),
            f"OTHER{uuid4().hex[:6]}USDT": _pump_then_settled_bars(10.0, 22.0),
        })

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert "density_size_multiplier" in result
        assert 0.5 <= result["density_size_multiplier"] <= 1.0
    finally:
        _cleanup_symbol(symbol)
        _cleanup_density_events()
        _set_pump_fade_settings(pump_fade_enabled="false")
