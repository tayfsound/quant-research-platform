"""Faz 211: kullanıcı bulgusu — quantity fiyattan bağımsız, hep "1.0 birim"
öneriliyordu (max_position_size limitinin ham değeri). Gerçek veriyle
doğrulandı: PAXGUSDT (~$4275/birim) 1.0 birim = $4275 notional açarken,
ADAUSDT (~$0.19/birim) 1.0 birim = $0.19 notional açıyordu — aynı "size"
aynı riski hiç temsil etmiyordu (komisyon pahalı varlıkta kârı yiyordu,
ucuz varlıkta pnl görünmeyecek kadar küçük kalıyordu). proposed_size artık
sermaye bütçesinin (starting_capital * max_capital_pct / max_concurrent_
positions) güncel fiyata bölünmesiyle hesaplanıyor — pahalı/ucuz varlıklar
artık aynı gerçek $ riskini taşıyor."""
from database.repositories.app_settings_repository import DEFAULTS, AppSettingsRepository
from database.session_factory import SessionFactory
from market_data.ingestion.mock_adapter import MockOHLCVAdapter
from services.orchestrator import CognitiveOrchestrator


def _reset_settings():
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key in ("starting_capital", "max_capital_pct", "max_concurrent_positions"):
            repo.set(key, DEFAULTS[key], updated_by="test")


def test_proposed_size_notional_is_consistent_across_wildly_different_prices():
    try:
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            repo.set("starting_capital", "10000", updated_by="test")
            repo.set("max_capital_pct", "0.3", updated_by="test")
            repo.set("max_concurrent_positions", "3", updated_by="test")

        expected_notional = 10000 * 0.3 / 3  # $1000

        orch = CognitiveOrchestrator()

        cheap_data = MockOHLCVAdapter(seed=1, base_price=0.19).generate(100)
        expensive_data = MockOHLCVAdapter(seed=2, base_price=4275.0).generate(100)

        cheap_ctx = orch._build_context("CHEAPUSDT", "1m", cheap_data)
        expensive_ctx = orch._build_context("EXPENSIVEUSDT", "1m", expensive_data)

        cheap_notional = cheap_ctx.decision.proposed_size * cheap_data[-1].close
        expensive_notional = expensive_ctx.decision.proposed_size * expensive_data[-1].close

        # İkisi de aynı $ bütçeyi hedeflemeli — fiyattan bağımsız.
        assert abs(cheap_notional - expected_notional) < 0.01
        assert abs(expensive_notional - expected_notional) < 0.01
        # Birim sayıları ise fiyatla ters orantılı olmalı (çok farklı).
        assert cheap_ctx.decision.proposed_size > expensive_ctx.decision.proposed_size * 1000
    finally:
        _reset_settings()
