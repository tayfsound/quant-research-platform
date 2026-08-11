"""Sprint 4: metrics engine — every metric checked against a hand-computed
reference value on a known synthetic equity curve, not just "code produces X,
assert X". analytics/metrics/{engine,equity}.py existed already but had zero
tests and zero callers anywhere in the codebase — a pure island."""
import numpy as np
import pytest

from analytics.metrics.engine import MetricsEngine
from analytics.metrics.equity import EquityAnalytics


# equity = [100, 200, 100, 400] chosen so every ratio comes out to a clean
# number by hand:
#   peak            = [100, 200, 200, 400]
#   drawdown_pct    = [0, 0, -0.5, 0]        (dip from 200 to 100)
#   max_drawdown    = -0.5
#   drawdown_dollar = [0, 0, 100, 0]
CLEAN_EQUITY = [100.0, 200.0, 100.0, 400.0]


def test_max_drawdown_matches_hand_computed_value():
    assert MetricsEngine.max_drawdown(CLEAN_EQUITY) == pytest.approx(-0.5)


def test_drawdown_series_matches_hand_computed_values():
    assert EquityAnalytics.drawdown_series(CLEAN_EQUITY) == pytest.approx([0.0, 0.0, -0.5, 0.0])


def test_ulcer_index_matches_hand_computed_value():
    # sqrt(mean([0, 0, 0.25, 0])) = sqrt(0.0625) = 0.25
    assert MetricsEngine.ulcer_index(CLEAN_EQUITY) == pytest.approx(0.25)


def test_recovery_factor_matches_hand_computed_value():
    # total_profit = 400 - 100 = 300; max_dd_dollar = 100 -> 300 / 100 = 3
    assert MetricsEngine.recovery_factor(CLEAN_EQUITY) == pytest.approx(3.0)


def test_calmar_ratio_matches_hand_computed_value_with_matching_annualization():
    # periods_per_year == n (3 bar-steps) so the annualization exponent is 1:
    # cagr = (400/100)^(3/3) - 1 = 3.0 ; calmar = 3.0 / 0.5 = 6.0
    assert MetricsEngine.calmar_ratio([], CLEAN_EQUITY, periods_per_year=3) == pytest.approx(6.0)


def test_mar_ratio_is_the_same_formula_as_calmar():
    assert MetricsEngine.mar_ratio([], CLEAN_EQUITY, periods_per_year=3) == pytest.approx(6.0)


def test_calmar_ratio_default_annualization_differs_from_raw_bar_count():
    """Regression guard: the old implementation used 1/len(equity) as the
    exponent, silently treating every bar as a full year. With the default
    periods_per_year=252 the two must diverge for a short equity curve."""
    old_wrong_formula = (CLEAN_EQUITY[-1] / CLEAN_EQUITY[0]) ** (1 / len(CLEAN_EQUITY)) - 1
    result = MetricsEngine.calmar_ratio([], CLEAN_EQUITY)
    correct_cagr = (CLEAN_EQUITY[-1] / CLEAN_EQUITY[0]) ** (252 / (len(CLEAN_EQUITY) - 1)) - 1
    assert result == pytest.approx(correct_cagr / 0.5)
    assert result != pytest.approx(old_wrong_formula / 0.5)


def test_sharpe_ratio_matches_hand_computed_value():
    returns = [0.01, 0.02, -0.01, 0.03]
    # mean = 0.0125, population std (ddof=0):
    mean = sum(returns) / 4
    variance = sum((r - mean) ** 2 for r in returns) / 4
    expected = mean / variance**0.5
    assert MetricsEngine.sharpe_ratio(returns) == pytest.approx(expected)


def test_sortino_ratio_matches_hand_computed_value():
    returns = [0.01, 0.02, -0.01, 0.03, -0.02]
    downside = [-0.01, -0.02]
    mean = sum(returns) / len(returns)
    std_down = np.std(downside)
    expected = mean / std_down
    assert MetricsEngine.sortino_ratio(returns) == pytest.approx(expected)


def test_sortino_ratio_with_single_losing_trade_is_finite_not_infinity():
    """Faz 268an — gerçek bulgu: TEK kayıp içeren bir dönüşte (ör.
    tek-işlemlik bir backtest) downside dizisi tek elemanlı oluyor,
    np.std([tek_değer]) matematiksel olarak tam 0.0 — önceki kod bunu
    sadece downside HİÇ yoksa koruyordu (0.0001 sabit payda), tek
    elemanlı gerçek-sıfır std'yi kaçırıyordu. Sonuç gerçek bir prod
    hatasıydı: backtest_runs.metrics'e (Postgres JSON) -Infinity
    yazılmaya çalışılınca DataError fırlıyordu."""
    result = MetricsEngine.sortino_ratio([-0.05])
    assert result == 0.0
    assert result not in (float("inf"), float("-inf"))


def test_sortino_ratio_with_no_losing_trades_is_finite_not_infinity():
    result = MetricsEngine.sortino_ratio([0.01, 0.02, 0.03])
    assert result == 0.0
    assert result not in (float("inf"), float("-inf"))


def test_win_rate_matches_hand_computed_value():
    fills = [{"pnl": 10}, {"pnl": -5}, {"pnl": 20}, {"pnl": -5}]
    assert MetricsEngine.win_rate(fills) == pytest.approx(0.5)


def test_profit_factor_matches_hand_computed_value():
    fills = [{"pnl": 10}, {"pnl": -5}, {"pnl": 20}, {"pnl": -5}]
    # gross_profit=30, gross_loss=10 -> 3.0
    assert MetricsEngine.profit_factor(fills) == pytest.approx(3.0)


def test_expectancy_matches_hand_computed_value():
    fills = [{"pnl": 10}, {"pnl": -5}, {"pnl": 20}, {"pnl": -5}]
    # win_rate=0.5, avg_win=15, loss_rate=0.5, avg_loss=5 -> 0.5*15 - 0.5*5 = 5.0
    assert MetricsEngine.expectancy(fills) == pytest.approx(5.0)
    # Must also equal the plain mean pnl per trade.
    assert MetricsEngine.expectancy(fills) == pytest.approx(sum(f["pnl"] for f in fills) / len(fills))


def test_recovery_factor_infinite_when_no_drawdown():
    assert MetricsEngine.recovery_factor([100.0, 110.0, 120.0]) == float("inf")


def test_expectancy_zero_on_empty_fills():
    assert MetricsEngine.expectancy([]) == 0.0


def test_metrics_engine_consumes_vectorized_backtest_equity_curve():
    """Prove Sprint 3's engine and Sprint 4's metrics actually fit together,
    instead of being two more disconnected pieces sitting next to each
    other."""
    from datetime import datetime, timezone, timedelta
    from backtest.vectorized_engine import VectorizedBacktestEngine
    from market_data.ingestion.ohlcv import OHLCV

    now = datetime.now(timezone.utc)
    closes = [100.0, 200.0, 100.0, 400.0]
    data = {
        "A": [
            OHLCV(timestamp=now + timedelta(minutes=i), open=c, high=c, low=c, close=c, volume=0.0)
            for i, c in enumerate(closes)
        ]
    }
    signals = np.array([[1.0, 1.0, 1.0, 1.0]])

    result = VectorizedBacktestEngine(fee=0.0).run(data, signals)
    equity = [100.0] + (100.0 + result.equity_curve).tolist()

    assert equity == pytest.approx(CLEAN_EQUITY)
    assert MetricsEngine.max_drawdown(equity) == pytest.approx(-0.5)
    assert MetricsEngine.ulcer_index(equity) == pytest.approx(0.25)
