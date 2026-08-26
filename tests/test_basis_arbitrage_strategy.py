"""Faz 344: Cross-Asset Arbitrage Engine v1 (spot-perpetual basis
arbitrajı) testleri — bkz. services/basis_arbitrage_strategy.py."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.risk_limit_repository import RiskLimitRepository
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.basis_arbitrage_strategy import EXPERIMENT_BUCKET, BasisArbitrageStrategy


def _cleanup_symbol(symbol: str) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
        session.commit()


def _seed_max_position_size(value: float = 1_000_000.0) -> None:
    """Faz 344 — gerçek bulgu: RiskEngine, max_position_size limiti hiç
    TANIMLI değilse (silinmişse) MISSING_LIMIT ile fail-closed reddediyor
    — pump_fade'in KENDİ opsiyonel kontrolünün aksine (get_active None
    dönerse sessizce atlar), RiskEngine bunu ZORUNLU sayıyor. Bu yüzden
    (pump_fade'in testlerinin aksine) silmek yerine bol bir limit
    tohumlamak gerekiyor."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from database.repositories.risk_limit_repository import RiskLimitModel

    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM risk_limits WHERE limit_type = 'max_position_size'"))
        RiskLimitRepository(session).save(RiskLimitModel(
            id=uuid4(), scope="global", limit_type="max_position_size",
            value=value, hash="", created_by="test", created_at=datetime.now(UTC),
        ))


def _set_basis_arb_settings(**overrides) -> None:
    defaults = {
        "basis_arbitrage_enabled": "false",
        "basis_arbitrage_min_basis_pct": "0.002",
        "basis_arbitrage_min_funding_rate": "0.0003",
        "basis_arbitrage_leg_capital_usd": "100",
        "basis_arbitrage_max_open_pairs": "1000",
        "basis_arbitrage_max_hold_hours": "72",
        "ai_enabled": "true",
        "trading_mode": "test",
        # pairs_trader.py'nin testleriyle AYNI gerekçe: paylaşılan test
        # DB'sinde biriken açık pozisyonlar kasa limitlerini gerçekçi
        # olmayan şekilde doldurabiliyor — bu testler kointegrasyon/basis
        # mantığını doğruluyor, kasa muhasebesini değil.
        "max_capital_pct": "1000000",
        "max_concurrent_positions": "100000",
        "kill_switch_consecutive_losses": "0",
    }
    defaults.update(overrides)
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key, value in defaults.items():
            repo.set(key, value, updated_by="test")
    _seed_max_position_size()


class _FakeProvider:
    def __init__(self, price: float = 100.0):
        self.price = price

    def get_ohlcv(self, symbol, timeframe, limit=100):
        return [OHLCV(timestamp=datetime.now(UTC), open=self.price, high=self.price, low=self.price, close=self.price, volume=1.0)]


def _basis_data(basis_pct: float = 0.005, funding_rate: float = 0.0005, index_price: float = 100.0) -> dict:
    return {
        "basis_pct": basis_pct,
        "funding_rate": funding_rate,
        "mark_price": index_price * (1 + basis_pct),
        "index_price": index_price,
    }


def test_run_cycle_skipped_when_disabled():
    _set_basis_arb_settings(basis_arbitrage_enabled="false")
    result = BasisArbitrageStrategy(data_provider=_FakeProvider()).run_cycle()
    assert result == {"skipped": "basis_arbitrage_disabled"}


def test_try_open_pair_opens_both_legs_when_thresholds_met(monkeypatch):
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true")
        monkeypatch.setattr(
            "services.basis_arbitrage_strategy.fetch_perp_basis",
            lambda s: _basis_data(basis_pct=0.005, funding_rate=0.0005),
        )
        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())

        result = strategy._try_open_pair(symbol, 0.002, 0.0003, 100.0, 1000)

        assert result is not None
        assert result["opened_legs"] == ["LONG_spot", "SHORT_perp"]

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions_for_experiment(EXPERIMENT_BUCKET)
        symbol_rows = [r for r in rows if r["symbol"] == symbol]
        assert len(symbol_rows) == 2
        assert {r["direction"] for r in symbol_rows} == {"LONG", "SHORT"}
    finally:
        _cleanup_symbol(symbol)


def test_try_open_pair_rejects_when_basis_below_threshold(monkeypatch):
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true")
        monkeypatch.setattr(
            "services.basis_arbitrage_strategy.fetch_perp_basis",
            lambda s: _basis_data(basis_pct=0.001, funding_rate=0.0005),
        )
        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())

        result = strategy._try_open_pair(symbol, 0.002, 0.0003, 100.0, 1000)

        assert result is None
    finally:
        _cleanup_symbol(symbol)


def test_try_open_pair_rejects_when_funding_below_threshold(monkeypatch):
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true")
        monkeypatch.setattr(
            "services.basis_arbitrage_strategy.fetch_perp_basis",
            lambda s: _basis_data(basis_pct=0.005, funding_rate=0.0001),
        )
        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())

        result = strategy._try_open_pair(symbol, 0.002, 0.0003, 100.0, 1000)

        assert result is None
    finally:
        _cleanup_symbol(symbol)


def test_try_open_pair_skips_when_basis_data_unavailable(monkeypatch):
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true")
        monkeypatch.setattr("services.basis_arbitrage_strategy.fetch_perp_basis", lambda s: None)
        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())

        result = strategy._try_open_pair(symbol, 0.002, 0.0003, 100.0, 1000)

        assert result is None
    finally:
        _cleanup_symbol(symbol)


def test_try_open_pair_refuses_second_pair_on_symbol_with_open_leg(monkeypatch):
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true")
        monkeypatch.setattr(
            "services.basis_arbitrage_strategy.fetch_perp_basis",
            lambda s: _basis_data(basis_pct=0.005, funding_rate=0.0005),
        )
        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())

        first = strategy._try_open_pair(symbol, 0.002, 0.0003, 100.0, 1000)
        second = strategy._try_open_pair(symbol, 0.002, 0.0003, 100.0, 1000)

        assert first is not None
        assert second is None
    finally:
        _cleanup_symbol(symbol)


def test_try_open_pair_refuses_when_max_open_pairs_reached(monkeypatch):
    symbol_a = f"BASISARB{uuid4().hex[:8]}USDT"
    symbol_b = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true")
        monkeypatch.setattr(
            "services.basis_arbitrage_strategy.fetch_perp_basis",
            lambda s: _basis_data(basis_pct=0.005, funding_rate=0.0005),
        )
        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())

        first = strategy._try_open_pair(symbol_a, 0.002, 0.0003, 100.0, max_open_pairs=1)
        second = strategy._try_open_pair(symbol_b, 0.002, 0.0003, 100.0, max_open_pairs=1)

        assert first is not None
        assert second is None
    finally:
        _cleanup_symbol(symbol_a)
        _cleanup_symbol(symbol_b)


def test_close_due_pairs_does_not_close_before_max_hold(monkeypatch):
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true", basis_arbitrage_max_hold_hours="72")
        monkeypatch.setattr(
            "services.basis_arbitrage_strategy.fetch_perp_basis",
            lambda s: _basis_data(basis_pct=0.005, funding_rate=0.0005),
        )
        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())
        strategy._try_open_pair(symbol, 0.002, 0.0003, 100.0, 1000)

        closed = strategy.close_due_pairs()

        assert not any(c["symbol"] == symbol for c in closed)
        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions_for_experiment(EXPERIMENT_BUCKET)
        assert len([r for r in rows if r["symbol"] == symbol]) == 2
    finally:
        _cleanup_symbol(symbol)


def test_close_due_pairs_closes_both_legs_together_after_max_hold(monkeypatch):
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true", basis_arbitrage_max_hold_hours="1")
        monkeypatch.setattr(
            "services.basis_arbitrage_strategy.fetch_perp_basis",
            lambda s: _basis_data(basis_pct=0.005, funding_rate=0.0005),
        )
        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())
        strategy._try_open_pair(symbol, 0.002, 0.0003, 100.0, 1000)

        # Bacakları geçmişte açılmış gibi işaretle (max_hold_hours=1'i aşacak şekilde).
        with SessionFactory.get_session() as session:
            session.execute(
                text("UPDATE decisions SET opened_at = :opened_at WHERE symbol = :symbol"),
                {"opened_at": datetime.now(UTC) - timedelta(hours=2), "symbol": symbol},
            )
            session.commit()

        closed = strategy.close_due_pairs()

        matching = [c for c in closed if c["symbol"] == symbol]
        assert len(matching) == 1
        assert matching[0]["legs_closed"] == 2

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions_for_experiment(EXPERIMENT_BUCKET)
        assert len([r for r in rows if r["symbol"] == symbol]) == 0
    finally:
        _cleanup_symbol(symbol)


def test_close_due_pairs_never_closes_a_lone_unhedged_leg(monkeypatch):
    """Faz 344 — kritik güvenlik testi: sadece BİR bacak açıksa (hedge
    başarısız olmuş), close_due_pairs onu YALNIZ başına kapatmamalı —
    v1'de bilerek dokunulmuyor (bkz. modülün kendi notu), yanlışlıkla
    çıplak bir pozisyonu "birlikte kapatma" mantığıyla tek başına
    kapatmak asıl güvenlik ilkesini ihlal ederdi."""
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true", basis_arbitrage_max_hold_hours="1")
        monkeypatch.setattr(
            "services.basis_arbitrage_strategy.fetch_perp_basis",
            lambda s: _basis_data(basis_pct=0.005, funding_rate=0.0005),
        )
        from services.risk_state import load_position_risk_state

        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())
        strategy._open_leg(symbol, "LONG", 100.0, 100.0, _basis_data(), load_position_risk_state(symbol=symbol))

        with SessionFactory.get_session() as session:
            session.execute(
                text("UPDATE decisions SET opened_at = :opened_at WHERE symbol = :symbol"),
                {"opened_at": datetime.now(UTC) - timedelta(hours=2), "symbol": symbol},
            )
            session.commit()

        closed = strategy.close_due_pairs()

        assert not any(c["symbol"] == symbol for c in closed)
        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions_for_experiment(EXPERIMENT_BUCKET)
        assert len([r for r in rows if r["symbol"] == symbol]) == 1
    finally:
        _cleanup_symbol(symbol)


def test_long_spot_leg_is_never_leveraged_even_when_symbol_leverage_configured(monkeypatch):
    """Faz 363 — kritik bulgu: LONG (spot) bacağı decision_recorder'ın
    sembol-bazlı GENEL kaldıraç ayarını kullanıyordu — cash-and-carry
    arbitrajın "spot bacak likidasyon riski taşımaz" temel varsayımı
    ihlal ediliyordu (gerçek olay: SCRTUSDT'de hem LONG hem SHORT bacağı
    likide oldu). LONG bacağı artık her koşulda leverage=1.0 (liquidation
    riski yok), SHORT (perp) bacağı ise sembolün kendi kaldıraç ayarını
    (test için 5x) KULLANMAYA DEVAM ETMELİ — bu bilinçli bir farklılık,
    regresyon değil."""
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        _set_basis_arb_settings(basis_arbitrage_enabled="true")
        import json
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "symbol_leverage", json.dumps({symbol: 5}), updated_by="test",
            )
        from services.risk_state import load_position_risk_state

        strategy = BasisArbitrageStrategy(data_provider=_FakeProvider())
        risk_state = load_position_risk_state(symbol=symbol)
        strategy._open_leg(symbol, "LONG", 100.0, 100.0, _basis_data(), risk_state)
        strategy._open_leg(symbol, "SHORT", 100.0, 100.0, _basis_data(), risk_state)

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions_for_experiment(EXPERIMENT_BUCKET)
        symbol_rows = {r["direction"]: r for r in rows if r["symbol"] == symbol}

        assert symbol_rows["LONG"]["leverage"] == 1.0
        assert symbol_rows["LONG"]["liquidation_price"] is None
        assert symbol_rows["SHORT"]["leverage"] == 5.0
        assert symbol_rows["SHORT"]["liquidation_price"] is not None
    finally:
        _cleanup_symbol(symbol)
        with SessionFactory.get_session() as session:
            from database.repositories.app_settings_repository import DEFAULTS
            AppSettingsRepository(session).set(
                "symbol_leverage", DEFAULTS.get("symbol_leverage", "{}"), updated_by="test",
            )


def test_list_open_positions_for_experiment_scopes_to_bucket_and_status():
    symbol = f"BASISARB{uuid4().hex[:8]}USDT"
    try:
        from contracts.decision_event import DecisionEvent

        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            persistor.persist(DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            ))
            persistor.persist(DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                experiment_bucket="some_other_bucket",
            ))

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions_for_experiment(EXPERIMENT_BUCKET)
        assert len([r for r in rows if r["symbol"] == symbol]) == 1
    finally:
        _cleanup_symbol(symbol)
