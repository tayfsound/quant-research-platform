"""Faz 268-sonrası: Drawdown-Based Position Sizing (gambler's ruin
koruması)."""
from risk.drawdown_sizing import MIN_MULTIPLIER, drawdown_size_multiplier


def test_full_size_below_the_start_threshold():
    assert drawdown_size_multiplier(0, start_after_losses=3, full_reduction_at_losses=10) == 1.0
    assert drawdown_size_multiplier(2, start_after_losses=3, full_reduction_at_losses=10) == 1.0


def test_full_size_exactly_at_start_threshold_minus_one():
    assert drawdown_size_multiplier(2, start_after_losses=3, full_reduction_at_losses=10) == 1.0


def test_reduces_linearly_between_thresholds():
    low = drawdown_size_multiplier(4, start_after_losses=3, full_reduction_at_losses=10)
    mid = drawdown_size_multiplier(6, start_after_losses=3, full_reduction_at_losses=10)
    high = drawdown_size_multiplier(9, start_after_losses=3, full_reduction_at_losses=10)
    assert 1.0 > low > mid > high > MIN_MULTIPLIER


def test_hits_floor_at_full_reduction_threshold_and_beyond():
    at_ceiling = drawdown_size_multiplier(10, start_after_losses=3, full_reduction_at_losses=10)
    beyond = drawdown_size_multiplier(50, start_after_losses=3, full_reduction_at_losses=10)
    assert at_ceiling == MIN_MULTIPLIER
    assert beyond == MIN_MULTIPLIER


def test_never_goes_below_the_floor_or_above_one():
    for losses in (0, 1, 3, 5, 8, 10, 20, 100):
        result = drawdown_size_multiplier(losses, start_after_losses=3, full_reduction_at_losses=10)
        assert MIN_MULTIPLIER <= result <= 1.0


def test_degenerate_ceiling_at_or_below_start_returns_floor_once_triggered():
    """full_reduction_at_losses <= start_after_losses — kademeli bir aralık
    yok, eşiğe ulaşınca direkt tabana düşer (fail-closed, hatalı/çakışan
    bir yapılandırmada asla tam boyutta kalınmaz)."""
    assert drawdown_size_multiplier(5, start_after_losses=5, full_reduction_at_losses=5) == MIN_MULTIPLIER
    assert drawdown_size_multiplier(5, start_after_losses=5, full_reduction_at_losses=2) == MIN_MULTIPLIER


def test_independent_of_kill_switch_being_disabled():
    """full_reduction_at_losses=0 (kill switch'in kendi eşiğinden TAMAMEN
    bağımsız bir ayar olduğu için) düşük ardışık kayıplarda hâlâ tam
    boyut vermeli, icat edilmiş bir erken küçültme uygulanmamalı."""
    assert drawdown_size_multiplier(0, start_after_losses=3, full_reduction_at_losses=0) == 1.0
    assert drawdown_size_multiplier(1, start_after_losses=3, full_reduction_at_losses=0) == 1.0
