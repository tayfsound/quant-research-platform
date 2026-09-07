"""analytics/short_scalp_only_gate.py — Faz 426 (2026-09-07). Faz 425'in
ızgara taraması: swing-mesafeli SHORT'ta hiçbir stop/hedef çifti pozitif
EV vermiyor, scalp-mesafeli SHORT'ta gerçek kenar var — "scalp only kapı
ayarlayalım." bkz. analytics/confidence_gate.py ile AYNI fail-open ilke."""
from analytics.short_scalp_only_gate import is_short_swing_blocked


def test_blocked_when_short_and_swing_and_enabled():
    assert is_short_swing_blocked("SHORT", "swing", True) is True


def test_not_blocked_when_short_and_scalp():
    assert is_short_swing_blocked("SHORT", "scalp", True) is False


def test_long_never_blocked_regardless_of_trade_type():
    assert is_short_swing_blocked("LONG", "swing", True) is False
    assert is_short_swing_blocked("LONG", "scalp", True) is False


def test_not_blocked_when_gate_disabled():
    assert is_short_swing_blocked("SHORT", "swing", False) is False


def test_not_blocked_when_trade_type_unknown():
    """entry_price/stop_loss_price henüz hesaplanmamışsa trade_type None
    olur — fail-open, icat edilmiş bir ret üretilmez."""
    assert is_short_swing_blocked("SHORT", None, True) is False
