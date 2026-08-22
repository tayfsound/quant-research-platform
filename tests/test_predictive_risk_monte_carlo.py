"""Faz 244-246: Predictive Risk — Regime-Switching Monte Carlo + CPPI."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from risk.predictive.cppi import (
    BREACH_PROBABILITY_THRESHOLD,
    MIN_EXPOSURE_MULTIPLIER,
    cppi_exposure_multiplier,
)
from risk.predictive.monte_carlo import (
    MIN_REGIME_SAMPLES,
    load_regime_conditioned_pnl_pct,
    simulate_regime_drawdown_risk,
)


def test_simulate_returns_none_when_fewer_than_min_samples():
    result = simulate_regime_drawdown_risk([0.01] * (MIN_REGIME_SAMPLES - 1))
    assert result["breach_probability"] is None
    assert result["worst_case_5th_percentile"] is None
    assert result["sample_count"] == MIN_REGIME_SAMPLES - 1


def test_simulate_all_positive_returns_never_breaches():
    """Hepsi kazandıran (pozitif) gerçek getirilerden bootstrap edilen
    yollar hiçbir zaman ruin eşiğini aşamaz — breach_probability tam 0.0
    olmalı."""
    pct_returns = [0.02] * 50
    result = simulate_regime_drawdown_risk(
        pct_returns, horizon_trades=10, num_simulations=500, seed=1,
    )
    assert result["breach_probability"] == 0.0
    assert result["median_terminal_return"] > 0


def test_simulate_all_severe_losses_always_breaches():
    """Hepsi ağır kayıp (-%25) veren getirilerden tek bir işlemlik bir
    yol bile ruin eşiğini (-%20) aşar — breach_probability tam 1.0."""
    pct_returns = [-0.25] * 50
    result = simulate_regime_drawdown_risk(
        pct_returns, horizon_trades=5, num_simulations=300,
        ruin_threshold_pct=-0.20, seed=2,
    )
    assert result["breach_probability"] == 1.0


def test_simulate_is_deterministic_with_a_fixed_seed():
    pct_returns = [0.03, -0.02, 0.01, -0.05, 0.04] * 10
    result_a = simulate_regime_drawdown_risk(pct_returns, seed=42)
    result_b = simulate_regime_drawdown_risk(pct_returns, seed=42)
    assert result_a == result_b


def test_cppi_multiplier_is_full_size_without_enough_data():
    result = {"sample_count": 5, "breach_probability": None}
    assert cppi_exposure_multiplier(result) == 1.0


def test_cppi_multiplier_is_full_size_below_threshold():
    result = {"breach_probability": BREACH_PROBABILITY_THRESHOLD - 0.01}
    assert cppi_exposure_multiplier(result) == 1.0


def test_cppi_multiplier_shrinks_proportionally_above_threshold():
    low = cppi_exposure_multiplier({"breach_probability": 0.10})
    high = cppi_exposure_multiplier({"breach_probability": 0.50})
    assert low < 1.0
    assert high < low  # daha yüksek risk -> daha küçük çarpan


def test_cppi_multiplier_never_goes_below_the_floor():
    result = cppi_exposure_multiplier({"breach_probability": 1.0})
    assert result == MIN_EXPOSURE_MULTIPLIER


def test_cppi_multiplier_never_exceeds_one():
    for p in (0.0, 0.05, 0.3, 0.7, 1.0):
        assert cppi_exposure_multiplier({"breach_probability": p}) <= 1.0


def test_load_regime_conditioned_pnl_pct_reflects_real_closed_trades():
    """Gerçek DB'ye karşı: aynı rejime etiketlenmiş, gerçek margin/pnl'e
    sahip kapanmış kararlardan doğru yüzde getiri hesaplandığını
    doğruluyor."""
    regime = f"bullish_normal_test_{uuid4().hex[:8]}"
    symbol = f"MCTEST{uuid4().hex[:6]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        # entry=100, qty=10, leverage=2 -> margin=500; pnl=+50 -> %10 getiri
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
            final_size=1.0, confidence=0.7, status="open", entry_price=100.0,
            quantity=10.0, leverage=2.0,
        )
        repo.persist(event)
        repo.close_position(
            decision_id=str(event.id), exit_price=105.0, pnl=50.0, closed_at=now,
            market_regime=regime,
        )

    pct_returns = load_regime_conditioned_pnl_pct(regime)
    assert len(pct_returns) == 1
    assert abs(pct_returns[0] - 0.10) < 1e-9


def test_load_regime_conditioned_pnl_pct_ignores_other_regimes():
    regime_a = f"regime_a_{uuid4().hex[:8]}"
    regime_b = f"regime_b_{uuid4().hex[:8]}"
    symbol = f"MCTEST{uuid4().hex[:6]}"
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
            final_size=1.0, confidence=0.7, status="open", entry_price=100.0, quantity=1.0,
        )
        repo.persist(event)
        repo.close_position(
            decision_id=str(event.id), exit_price=110.0, pnl=10.0, closed_at=now,
            market_regime=regime_a,
        )

    assert load_regime_conditioned_pnl_pct(regime_b) == []
