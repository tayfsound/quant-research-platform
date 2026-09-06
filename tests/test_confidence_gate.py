"""analytics/confidence_gate.py — Faz 421 (2026-09-06). Kullanıcı isteği:
gerçek confidence kovası verisiyle LONG'da confidence≈0,7'nin hem
%85,2 kazanma HEM +$11,65/işlem gerçek pozitif PnL verdiği bulundu —
"canlıda sadece 0,7 confidence bulduğunda değerlendirsin."."""
from analytics.confidence_gate import is_confidence_trading_blocked


def test_blocked_when_below_threshold_and_enabled():
    assert is_confidence_trading_blocked(0.5, True, 0.7) is True


def test_not_blocked_when_at_or_above_threshold():
    assert is_confidence_trading_blocked(0.7, True, 0.7) is False
    assert is_confidence_trading_blocked(0.85, True, 0.7) is False


def test_not_blocked_when_gate_disabled():
    assert is_confidence_trading_blocked(0.1, False, 0.7) is False


def test_not_blocked_when_confidence_unknown():
    """confidence None ise (bilinmiyor) fail-open — icat edilmiş bir
    ret asla üretilmez, diğer kullanıcı-tercihi kapılarıyla AYNI ilke."""
    assert is_confidence_trading_blocked(None, True, 0.7) is False
