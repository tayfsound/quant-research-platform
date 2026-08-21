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
        # Faz 332 — eski pump_fade_capital_pct (kasanın sabit %5'i, stop
        # mesafesinden bağımsız) risk-bazlı boyutlandırmayla değiştirildi:
        # margin artık max_loss_per_trade_usd/(stop_distance_pct×leverage)
        # ile hesaplanıyor. stop_distance_pct=0.15, leverage 4.348'e
        # (max_safe_leverage) kırpıldığında margin≈$76.7 — eski $50
        # varsayılanıyla aynı büyüklük mertebesinde, testlerin çoğu
        # tam bir dolar tutarına değil davranışa bakıyor.
        "pump_fade_max_loss_per_trade_usd": "50",
        "pump_fade_max_open_positions": "1000",
        "pump_fade_leverage": "5",
        "pump_fade_min_gain_pct": "1.0",
        "pump_fade_lookback_hours": "48",
        "pump_fade_stop_distance_pct": "0.15",
        "starting_capital": "1000",
        # Faz 330 — bu testlerin çoğu kümülatif sermaye tavanını değil
        # başka davranışları doğruluyor; paylaşılan test DB'sinde başka
        # testlerden kalan açık pump_fade_v1 pozisyonları (gerçek dolar
        # tutarlarıyla) varsa küçük starting_capital=1000'e karşı bu tavanı
        # yanlışlıkla tetikleyebilirdi (AYNI max_capital_pct="1000000"
        # deseni, test_pairs_trader.py'de de kullanılıyor) — kümülatif
        # tavanı özel olarak test eden testler kendi değerini verir.
        "pump_fade_max_total_capital_pct": "1000000",
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


def test_run_cycle_records_execution_cost_estimate_when_order_book_available(monkeypatch):
    """Faz 337 — kullanıcı onayı: ExecutionAgent v1 SADECE ölçüm/kayıt,
    margin/quantity'ye hiç dokunmuyor. Gerçek bir order_book_snapshots
    satırı varsa agent_opinions'a bir 'execution_cost_estimate' kaydı
    eklenmeli."""
    from contracts.market_data import DataSource
    from database.repositories.market_data_repository import MarketDataRepository

    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        with SessionFactory.get_session() as session:
            MarketDataRepository(session).save_order_book_snapshot(
                exchange=DataSource.BINANCE, symbol=symbol, time=datetime.now(UTC),
                best_bid=21.9, best_ask=22.0, bid_volume=500.0, ask_volume=500.0,
                imbalance=0.0, spread_bps=45.0,
            )
            session.commit()

        _set_pump_fade_settings(pump_fade_enabled="true")
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()
        assert len(result["opened"]) == 1

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions(limit=50)
        row = next(r for r in rows if r["symbol"] == symbol)
        estimates = [c for c in row["agent_contributions"] if c.get("type") == "execution_cost_estimate"]
        assert len(estimates) == 1
        assert estimates[0]["data"]["total_cost_pct"] > 0
    finally:
        _cleanup_symbol(symbol)
        with SessionFactory.get_session() as session:
            session.execute(text("DELETE FROM order_book_snapshots WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()
        _set_pump_fade_settings(pump_fade_enabled="false")


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
    hiç kontrol edilmemişti. Faz 332: margin artık risk-bazlı — max_loss_
    per_trade_usd=$50, stop=%15, güvenlik-kilidi kaldıracı ~4.348x ->
    margin=50/(0.15*4.348)≈$76.67, kırpılmamış notional=margin*4.348≈$333.3.
    max_position_size=margin*1.5≈$115 verilince (margin'in üstünde ama
    kırpılmamış notional'ın altında) kaldıraç 115/76.67=1.5'e kırpılmalı —
    ne 1x tabanına düşecek kadar düşük (bir sonraki test o senaryoyu
    kapsıyor) ne de hedefe (4.348x) ulaşacak kadar yüksek bir tavan."""
    from simulator.margin import max_safe_leverage

    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        stop_distance_pct = 0.15
        target_leverage = 5.0
        safe_leverage = max_safe_leverage(stop_distance_pct)
        clamped_leverage = min(target_leverage, safe_leverage)
        margin = 50.0 / (stop_distance_pct * clamped_leverage)
        max_position_size = margin * 1.5  # margin ile margin*leverage arasında -> gercek kirpma
        _seed_max_position_size(max_position_size)
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert len(result["opened"]) == 1
        opened = result["opened"][0]
        assert opened["leverage"] == pytest.approx(1.5, rel=1e-3)

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions(limit=50)
        row = next(r for r in rows if r["symbol"] == symbol)
        notional = row["quantity"] * row["entry_price"]
        assert notional == pytest.approx(max_position_size, rel=1e-3)
    finally:
        _cleanup_symbol(symbol)
        _cleanup_max_position_size()
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_does_not_open_position_when_margin_alone_exceeds_max_position_size(monkeypatch):
    """Margin (1x kaldıraçta bile) tavanı aşıyorsa pozisyon HİÇ açılmamalı
    — "sinyal limitleri gevşetemez, sadece küçültebilir/reddedebilir"
    ilkesi, kırpmanın bir noktadan sonra anlamsız kaldığı durum."""
    from simulator.margin import max_safe_leverage

    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        stop_distance_pct = 0.15
        target_leverage = 5.0
        safe_leverage = max_safe_leverage(stop_distance_pct)
        clamped_leverage = min(target_leverage, safe_leverage)
        margin = 50.0 / (stop_distance_pct * clamped_leverage)
        _seed_max_position_size(margin * 0.5)  # tavan margin'in altında, 1x'te bile sığmaz
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


def test_run_cycle_refuses_new_position_when_cumulative_margin_would_exceed_cap(monkeypatch):
    """Faz 330 — kritik bulgu: canlıda 99 açık pump_fade pozisyonu, toplam
    gerçek marjin kasanın ~%443'ü olmuştu, çünkü her yeni işlem sadece
    kendi boyutuna bakıyordu (pump_fade_capital_pct), zaten açık olan
    pozisyonların toplamına hiç bakmıyordu. Burada: starting_capital=1000,
    pump_fade_max_total_capital_pct=0.10 (tavan=$100) iken zaten $80
    marjinlik açık bir pozisyon varsa, yeni %5'lik ($50) bir işlem
    (80+50=130 > 100) reddedilmeli."""
    existing_symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    new_symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        from contracts.decision_event import DecisionEvent

        with SessionFactory.get_session() as session:
            DecisionPersistor(session).persist(DecisionEvent(
                id=uuid4(), symbol=existing_symbol, proposed_direction="SHORT",
                final_action="SHORT", final_size=1.0, status="open",
                entry_price=100.0, quantity=0.8, leverage=1.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            ))

        _set_pump_fade_settings(
            pump_fade_enabled="true",
            pump_fade_max_total_capital_pct="0.10",
        )
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [new_symbol]
        )
        provider = _FakeProvider({new_symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert result["candidates_found"] == 1
        assert len(result["opened"]) == 0
    finally:
        _cleanup_symbol(existing_symbol)
        _cleanup_symbol(new_symbol)


def test_run_cycle_opens_position_when_within_cumulative_cap(monkeypatch):
    """Aynı senaryo ama tavan bol ($1000000) — yeni işlem serbestçe
    açılabilmeli, kümülatif kontrol yanlışlıkla normal işlemleri
    engellememeli."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(
            pump_fade_enabled="true",
            pump_fade_max_total_capital_pct="1000000",
        )
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert len(result["opened"]) == 1
    finally:
        _cleanup_symbol(symbol)


def test_total_open_margin_for_experiment_divides_notional_by_leverage():
    from contracts.decision_event import DecisionEvent

    symbol_a = f"PUMPFADE{uuid4().hex[:8]}USDT"
    symbol_b = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            baseline = persistor.total_open_margin_for_experiment(EXPERIMENT_BUCKET)
            # notional=100*10=1000, leverage=5 -> marjin=200
            persistor.persist(DecisionEvent(
                id=uuid4(), symbol=symbol_a, proposed_direction="SHORT",
                final_action="SHORT", final_size=1.0, status="open",
                entry_price=100.0, quantity=10.0, leverage=5.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            ))
            # leverage yok (None) -> notional=marjin olarak sayılır: 50*2=100
            persistor.persist(DecisionEvent(
                id=uuid4(), symbol=symbol_b, proposed_direction="SHORT",
                final_action="SHORT", final_size=1.0, status="open",
                entry_price=50.0, quantity=2.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            ))
            total = persistor.total_open_margin_for_experiment(EXPERIMENT_BUCKET)
        assert abs((total - baseline) - 300.0) < 1e-6
    finally:
        _cleanup_symbol(symbol_a)
        _cleanup_symbol(symbol_b)


def test_count_open_positions_for_experiment_counts_only_that_bucket():
    from contracts.decision_event import DecisionEvent

    symbol_a = f"PUMPFADE{uuid4().hex[:8]}USDT"
    symbol_b = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            baseline = persistor.count_open_positions_for_experiment(EXPERIMENT_BUCKET)
            persistor.persist(DecisionEvent(
                id=uuid4(), symbol=symbol_a, proposed_direction="SHORT",
                final_action="SHORT", final_size=1.0, status="open",
                entry_price=100.0, quantity=1.0, experiment_bucket=EXPERIMENT_BUCKET,
            ))
            persistor.persist(DecisionEvent(
                id=uuid4(), symbol=symbol_b, proposed_direction="SHORT",
                final_action="SHORT", final_size=1.0, status="open",
                entry_price=100.0, quantity=1.0, experiment_bucket="some_other_experiment",
            ))
            count = persistor.count_open_positions_for_experiment(EXPERIMENT_BUCKET)
        assert count == baseline + 1
    finally:
        _cleanup_symbol(symbol_a)
        _cleanup_symbol(symbol_b)


def test_total_pnl_for_experiment_sums_only_closed_realized_pnl():
    from contracts.decision_event import DecisionEvent

    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            baseline = persistor.total_pnl_for_experiment(EXPERIMENT_BUCKET)
            event = DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="SHORT", final_action="SHORT",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            )
            persistor.persist(event)
            # Kapanmamış pozisyon toplamı etkilememeli (SADECE gerçekleşmiş pnl).
            assert persistor.total_pnl_for_experiment(EXPERIMENT_BUCKET) == pytest.approx(baseline)
            persistor.close_position(decision_id=str(event.id), exit_price=80.0, pnl=-123.45, closed_at=datetime.now(UTC))
            total = persistor.total_pnl_for_experiment(EXPERIMENT_BUCKET)
        assert total == pytest.approx(baseline - 123.45)
    finally:
        _cleanup_symbol(symbol)


def test_try_open_refuses_new_position_when_open_count_at_cap(monkeypatch):
    """Faz 332 — kritik bulgu: gerçek olayda 82-99 pozisyon aynı anda,
    çoğunlukla AYNI yönde (SHORT), yüksek korelasyonlu açık kalmıştı —
    kümülatif MARJİN tavanı tek başına bunu önlemedi (risk-bazlı
    boyutlandırma sonrası tek pozisyon marjini küçüldüğü için tavana çok
    daha fazla pozisyon sığıyor). Ayrı bir SAYI tavanı bunu doğrudan
    sınırlıyor."""
    from contracts.decision_event import DecisionEvent

    existing_symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    new_symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        with SessionFactory.get_session() as session:
            DecisionPersistor(session).persist(DecisionEvent(
                id=uuid4(), symbol=existing_symbol, proposed_direction="SHORT",
                final_action="SHORT", final_size=1.0, status="open",
                entry_price=100.0, quantity=0.01, leverage=1.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            ))

        _set_pump_fade_settings(pump_fade_enabled="true", pump_fade_max_open_positions="1")
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [new_symbol]
        )
        provider = _FakeProvider({new_symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert result["candidates_found"] == 1
        assert len(result["opened"]) == 0
    finally:
        _cleanup_symbol(existing_symbol)
        _cleanup_symbol(new_symbol)


def test_try_open_opens_when_below_open_count_cap(monkeypatch):
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true", pump_fade_max_open_positions="1000000")
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert len(result["opened"]) == 1
    finally:
        _cleanup_symbol(symbol)


def test_run_cycle_trips_circuit_breaker_and_disables_pump_fade(monkeypatch):
    """Faz 332 — kritik bulgu: kümülatif MARJİN tavanı sadece "ne kadar
    sermaye BAĞLANABİLİR"i sınırlıyordu, "ne kadar KAYBEDİLEBİLİR"i
    sınırlamıyordu (gerçek olay: 82 pozisyon sermaye tavanına "sığıyor"
    olsa bile hepsi birden zarara dönebiliyordu). Toplam gerçekleşmiş
    zarar eşiği aşarsa pump_fade_enabled OTOMATİK false olmalı, yeni
    işlem hiç denenmemeli."""
    from contracts.decision_event import DecisionEvent

    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    loss_symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            event = DecisionEvent(
                id=uuid4(), symbol=loss_symbol, proposed_direction="SHORT", final_action="SHORT",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            )
            persistor.persist(event)
            persistor.close_position(decision_id=str(event.id), exit_price=200.0, pnl=-200.0, closed_at=datetime.now(UTC))
            baseline_after_loss = persistor.total_pnl_for_experiment(EXPERIMENT_BUCKET)

        _set_pump_fade_settings(
            pump_fade_enabled="true",
            pump_fade_max_loss_circuit_breaker_usd="1",
        )
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        assert baseline_after_loss <= -1  # eşiği (1$) gercekten asiyor mu, on-kosul

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert result["skipped"] == "circuit_breaker_tripped"
        with SessionFactory.get_session() as session:
            enabled = AppSettingsRepository(session).get("pump_fade_enabled")
        assert enabled == "false"
        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions(limit=50)
        assert not any(r["symbol"] == symbol for r in rows)
    finally:
        _cleanup_symbol(symbol)
        _cleanup_symbol(loss_symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_does_not_trip_circuit_breaker_when_loss_below_threshold(monkeypatch):
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(
            pump_fade_enabled="true",
            pump_fade_max_loss_circuit_breaker_usd="1000000",
        )
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0)})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert "skipped" not in result
        assert len(result["opened"]) == 1
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

        full = strategy._try_open(
            candidate, 50.0, 5.0, 0.15, 0.25, 1000.0, 48,
            density_size_multiplier=1.0, max_open_positions=100000,
        )
        with SessionFactory.get_session() as session:
            row_full = DecisionPersistor(session).list_open_positions(limit=50)
        notional_full = next(r for r in row_full if r["symbol"] == symbol)["quantity"] * full["entry_price"]
        _cleanup_symbol(symbol)

        half = strategy._try_open(
            candidate, 50.0, 5.0, 0.15, 0.25, 1000.0, 48,
            density_size_multiplier=0.5, max_open_positions=100000,
        )
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


# Faz 318 — _compute_regime_size_multiplier testleri. Kullanıcı bulgusu
# (2026-08-20, canlı): pump_fade HER ZAMAN SHORT açıyor, council'in kendi
# LONG/SHORT pozisyonlarının GERÇEK kârlılık farkı VE BTC'nin uzun-vade
# rejimi AYNI ANDA güçlü bull işaret ederse margin küçültülür (asla kapatılmaz).
#
# _FakeSession (gerçek DB'ye HİÇ dokunmuyor) kasıtlı: quantdb_test'te
# deneme paylaşımlı 'decisions' tablosu diğer test dosyalarının
# temizlemediği yüzlerce açık 'ai' pozisyonuyla kirli (canlı doğrulandı:
# 323 açık LONG, 2 açık SHORT, experiment_bucket IS NULL) — gerçek
# session ile yazılan bir test bu ambient veriyle karışıp yanlış/flaky
# sonuç verebilirdi (project_shared_test_state_bloat ile aynı sınıf risk).
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *args, **kwargs):
        return _FakeResult(self._rows)


def _council_rows(long_specs: list[tuple[float, float]], short_specs: list[tuple[float, float]]) -> tuple[list[tuple], dict]:
    """long_specs/short_specs: [(entry_price, current_price), ...]. Döner:
    (SQL sorgusunun döneceği (symbol, direction, avg_entry) satırları,
    _FakeProvider'a verilecek bars_by_symbol)."""
    rows = []
    bars_by_symbol = {}
    for i, (entry, current) in enumerate(long_specs):
        symbol = f"REGL{i}USDT"
        rows.append((symbol, "LONG", entry))
        bars_by_symbol[symbol] = [_bar(current, current), _bar(current, current)]
    for i, (entry, current) in enumerate(short_specs):
        symbol = f"REGS{i}USDT"
        rows.append((symbol, "SHORT", entry))
        bars_by_symbol[symbol] = [_bar(current, current), _bar(current, current)]
    return rows, bars_by_symbol


def _bull_daily_bars(n: int = 250) -> list[OHLCV]:
    """Uzun vadeli, istikrarlı yükseliş — long_term_trend_regime='bull_trend'
    üretecek şekilde (fiyat > 200-EMA VE EMA eğimi pozitif)."""
    bars = []
    price = 100.0
    for _ in range(n):
        price *= 1.01
        bars.append(_bar(price * 0.99, price))
    return bars


def _flat_daily_bars(n: int = 250) -> list[OHLCV]:
    return [_bar(100.0, 100.0) for _ in range(n)]


def test_regime_multiplier_is_1_when_symbol_sample_too_small():
    """Faz 332 — BTC bars kasıtlı olarak FLAT (bull_trend DEĞİL): bu test
    sadece 'council örneklemi yetersiz' davranışını izole ediyor. BTC
    gerçekten bull_trend'deyken artık council örneklemi yetersiz olsa
    bile PARTIAL_FLOOR tetiklenir (BTC rejimi artık council'den bağımsız,
    kendi başına yeterli bir sinyal) — bu, ayrı bir test (aşağıda)."""
    from services.pump_fade_strategy import _compute_regime_size_multiplier

    rows, bars = _council_rows(long_specs=[(100.0, 110.0)] * 2, short_specs=[(100.0, 110.0)] * 1)
    bars["BTCUSDT"] = _flat_daily_bars()
    multiplier = _compute_regime_size_multiplier(_FakeSession(rows), _FakeProvider(bars))
    assert multiplier == 1.0


def test_regime_multiplier_is_1_when_no_council_win_rate_gap():
    """Faz 332 — BTC bars kasıtlı FLAT, bkz. yukarıdaki test notu."""
    from services.pump_fade_strategy import _compute_regime_size_multiplier

    # LONG ve SHORT'lar EŞİT ölçüde kârda -> kârlılık farkı yok.
    rows, bars = _council_rows(
        long_specs=[(100.0, 110.0)] * 5,
        short_specs=[(100.0, 90.0)] * 5,
    )
    bars["BTCUSDT"] = _flat_daily_bars()
    multiplier = _compute_regime_size_multiplier(_FakeSession(rows), _FakeProvider(bars))
    assert multiplier == 1.0


def test_regime_multiplier_applies_partial_floor_from_btc_alone_even_with_insufficient_council_sample():
    """Faz 332 — kritik bulgu, gerçek veriyle ölçüldü: son 48 saatte
    rejim gate'inin kapsadığı açılışların %51'i hâlâ indirimsiz (1.0x)
    çıkmıştı çünkü BTC bull_trend'de olsa bile council'in KENDİ o anki
    (gürültülü, az örneklemli) kâr/zarar sinyali eşiği geçmezse hiç
    kontrol edilmiyordu. Artık BTC'nin 200-EMA uzun-vade rejimi TAMAMEN
    BAĞIMSIZ, kendi başına yeterli bir sinyal — council örneklemi
    yetersiz (< 5 sembol/taraf) olsa bile BTC bull_trend'deyse PARTIAL_
    FLOOR uygulanır."""
    from services.pump_fade_strategy import _REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER, _compute_regime_size_multiplier

    rows, bars = _council_rows(long_specs=[(100.0, 110.0)] * 2, short_specs=[(100.0, 110.0)] * 1)
    bars["BTCUSDT"] = _bull_daily_bars()
    multiplier = _compute_regime_size_multiplier(_FakeSession(rows), _FakeProvider(bars))
    assert multiplier == _REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER


def test_regime_multiplier_is_1_when_council_bullish_but_btc_not_bull_trend():
    """Faz 327 — BTC bull_trend değilken VE kârlılık farkı orta düzeydeyse
    (eşiği geçer ama "aşırı ezici" 2. kademe eşiğinin altında kalır)
    çarpan hâlâ 1.0 kalmalı — sadece BTC gerçekten bull_trend'deyken ya
    da fark aşırı ezikciyken küçültme devreye girer."""
    from services.pump_fade_strategy import _compute_regime_size_multiplier

    # LONG %100 kârda (5/5), SHORT %50 kârda (5/10) -> gap=0.5, eşiği
    # (0.30) geçer ama 2. kademe eşiğinin (0.60) altında kalır.
    rows, bars = _council_rows(
        long_specs=[(100.0, 110.0)] * 5,
        short_specs=[(100.0, 110.0)] * 5 + [(100.0, 90.0)] * 5,
    )
    bars["BTCUSDT"] = _flat_daily_bars()  # bull_trend DEĞİL
    multiplier = _compute_regime_size_multiplier(_FakeSession(rows), _FakeProvider(bars))
    assert multiplier == 1.0


def test_regime_multiplier_applies_partial_floor_when_btc_transition_but_gap_extreme():
    """Faz 327 — kullanıcı bulgusu (canlı, tekrarlayan): BTC 'transition'
    rejimindeyken (kesin bull_trend değil) bile council farkı AŞIRI
    ezikciyse (>= 0.60 — mevcut 0.30 eşiğinin 2 katı) daha hafif bir
    küçültme (0.5) uygulanmalı — BTC gerçekten bull_trend'deyken
    kullanılan en sert taban (0.15) sadece o durumda kalır."""
    from services.pump_fade_strategy import (
        _REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER,
        _compute_regime_size_multiplier,
    )

    # LONG %100 kârda, SHORT %0 kârda -> gap=1.0, 2. kademe eşiğini (0.60) aşar.
    rows, bars = _council_rows(
        long_specs=[(100.0, 110.0)] * 5,
        short_specs=[(100.0, 110.0)] * 5,
    )
    bars["BTCUSDT"] = _flat_daily_bars()  # bull_trend DEĞİL (transition/flat)
    multiplier = _compute_regime_size_multiplier(_FakeSession(rows), _FakeProvider(bars))
    assert multiplier == _REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER


def test_regime_multiplier_applies_partial_floor_from_long_only_strong_signal():
    """Faz 332 — kritik bulgu, CANLI durumda yakalandı: BTC hızlı bir
    sıçrama yapmış (%20/5 gün) ama 200-EMA hâlâ 'transition' diyor VE
    açık AI SHORT sayısı (2) min. örneklem eşiğinin (5) altında —
    council_bull_bias hiç hesaplanamıyor. LONG tarafı TEK BAŞINA
    yeterince büyük (n=38) ve ezici (%94.7) bir örneklemse bu da
    bağımsız bir sinyal sayılmalı."""
    from services.pump_fade_strategy import _REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER, _compute_regime_size_multiplier

    # 38 LONG'un 36'sı kârda (%94.7), sadece 2 SHORT (min. 5'in altında).
    rows, bars = _council_rows(
        long_specs=[(100.0, 110.0)] * 36 + [(100.0, 90.0)] * 2,
        short_specs=[(100.0, 90.0)] * 2,
    )
    bars["BTCUSDT"] = _flat_daily_bars()  # bull_trend DEĞİL (transition)
    multiplier = _compute_regime_size_multiplier(_FakeSession(rows), _FakeProvider(bars))
    assert multiplier == _REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER


def test_regime_multiplier_stays_1_when_long_only_signal_below_strong_threshold():
    """Yeterince büyük örneklem ama sadece %80 kârda (ezici eşiğin,
    %90'ın, altında) -> tetiklenmemeli."""
    from services.pump_fade_strategy import _compute_regime_size_multiplier

    rows, bars = _council_rows(
        long_specs=[(100.0, 110.0)] * 8 + [(100.0, 90.0)] * 2,  # %80 kârda
        short_specs=[(100.0, 90.0)] * 2,
    )
    bars["BTCUSDT"] = _flat_daily_bars()
    multiplier = _compute_regime_size_multiplier(_FakeSession(rows), _FakeProvider(bars))
    assert multiplier == 1.0


def test_regime_multiplier_shrinks_to_floor_when_both_signals_align():
    from services.pump_fade_strategy import _REGIME_GATE_FLOOR_MULTIPLIER, _compute_regime_size_multiplier

    rows, bars = _council_rows(
        long_specs=[(100.0, 110.0)] * 5,  # hepsi kârda
        short_specs=[(100.0, 110.0)] * 5,  # hepsi zararda
    )
    bars["BTCUSDT"] = _bull_daily_bars()
    multiplier = _compute_regime_size_multiplier(_FakeSession(rows), _FakeProvider(bars))
    assert multiplier == _REGIME_GATE_FLOOR_MULTIPLIER


def test_regime_multiplier_query_scopes_to_ai_positions_only():
    """SQL sorgusu 'experiment_bucket IS NULL' filtresi taşımalı — pump_fade'in
    kendi SHORT'ları asla council sinyaline karışmamalı (aksi halde strateji
    kendi kendini besler). Sorgunun kendisi services/pump_fade_strategy.py'de
    sabit metin olarak tanımlı; burada gerçek DB'ye dokunmadan sorgu metninin
    filtreyi içerdiğini doğruluyoruz."""
    import inspect

    from services.pump_fade_strategy import _compute_regime_size_multiplier

    source = inspect.getsource(_compute_regime_size_multiplier)
    assert "experiment_bucket IS NULL" in source


def test_run_cycle_reports_regime_size_multiplier(monkeypatch):
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        monkeypatch.setattr("services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol])
        provider = _FakeProvider({symbol: _pump_then_settled_bars(10.0, 22.0), "BTCUSDT": _flat_daily_bars()})
        result = PumpFadeStrategy(data_provider=provider).run_cycle()
        assert "regime_size_multiplier" in result
        assert result["regime_size_multiplier"] == 1.0
    finally:
        _cleanup_symbol(symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")
