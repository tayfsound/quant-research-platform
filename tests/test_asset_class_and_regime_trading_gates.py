"""analytics/asset_class_trading_gate.py + analytics/regime_trading_gate.py
— kullanıcı isteği (2026-08-27)."""
from analytics.asset_class_trading_gate import is_asset_class_trading_blocked
from analytics.regime_trading_gate import is_regime_trading_blocked


def test_asset_class_blocked_when_explicitly_false():
    assert is_asset_class_trading_blocked("crypto", {"crypto": False}) is True


def test_asset_class_not_blocked_when_true():
    assert is_asset_class_trading_blocked("crypto", {"crypto": True}) is False


def test_asset_class_fail_open_for_unmapped_category():
    """Yeni bir kategori eklenip enabled_map henüz güncellenmemişse
    varsayılan AÇIK — kullanıcı tercihi kapısı, güvenlik kapısı değil."""
    assert is_asset_class_trading_blocked("equity", {}) is False


def test_asset_class_none_category_never_blocked():
    assert is_asset_class_trading_blocked(None, {"crypto": False}) is False


def test_regime_blocked_when_explicitly_false():
    assert is_regime_trading_blocked("bearish_low", {"bearish_low": False}) is True


def test_regime_not_blocked_when_true():
    assert is_regime_trading_blocked("bearish_low", {"bearish_low": True}) is False


def test_regime_fail_open_for_unmapped_regime():
    assert is_regime_trading_blocked("bullish_high", {}) is False


def test_regime_none_never_blocked():
    assert is_regime_trading_blocked(None, {"bearish_low": False}) is False


def test_long_override_lets_long_through_a_blocked_regime():
    """Faz 420 — kullanıcı bulgusu: bearish_normal'da LONG GÜÇLÜ kârlıydı
    (+$620,65, %88,9, n=225) SHORT aynı rejimde -$5.728 kaybediyordu.
    Rejim kapalı olsa bile LONG, override kümesindeyse geçmeli."""
    assert is_regime_trading_blocked(
        "bearish_normal", {"bearish_normal": False}, direction="LONG",
        long_override_regimes={"bearish_normal"},
    ) is False


def test_long_override_does_not_help_short():
    """SADECE LONG — override kümesinde olsa bile SHORT hâlâ tam engelli."""
    assert is_regime_trading_blocked(
        "bearish_normal", {"bearish_normal": False}, direction="SHORT",
        long_override_regimes={"bearish_normal"},
    ) is True


def test_long_override_only_applies_to_listed_regimes():
    """Kanıt SADECE bearish_normal için yeterliydi — bearish_low override
    kümesinde DEĞİLSE, LONG orada hâlâ tam engelli kalmalı."""
    assert is_regime_trading_blocked(
        "bearish_low", {"bearish_low": False}, direction="LONG",
        long_override_regimes={"bearish_normal"},
    ) is True


def test_long_override_irrelevant_when_regime_not_blocked():
    """Rejim zaten açıksa override'ın hiçbir etkisi olmamalı — hâlâ
    engellenmemeli (aynı sonuç, farklı yoldan)."""
    assert is_regime_trading_blocked(
        "bearish_normal", {"bearish_normal": True}, direction="LONG",
        long_override_regimes={"bearish_normal"},
    ) is False
