"""analytics/mae_mfe_bucket_trading_gate.py — kullanıcı isteği (2026-08-28)."""
from analytics.mae_mfe_bucket_trading_gate import build_bucket_key, is_mae_mfe_bucket_trading_blocked


def test_blocked_when_explicitly_false():
    key = "direction=LONG|regime=bull_trend|volatility_regime=normal"
    assert is_mae_mfe_bucket_trading_blocked(key, {key: False}) is True


def test_not_blocked_when_true():
    key = "direction=LONG|regime=bull_trend|volatility_regime=normal"
    assert is_mae_mfe_bucket_trading_blocked(key, {key: True}) is False


def test_fail_open_for_unmapped_bucket():
    """Yeni bir kova (örneklem eşiğini yeni geçmiş bir kombinasyon)
    henüz enabled_map'te yoksa varsayılan AÇIK — kullanıcı tercihi
    kapısı, güvenlik kapısı değil."""
    assert is_mae_mfe_bucket_trading_blocked("direction=SHORT|regime=transition|volatility_regime=high", {}) is False


def test_none_bucket_never_blocked():
    key = "direction=LONG|regime=bull_trend|volatility_regime=normal"
    assert is_mae_mfe_bucket_trading_blocked(None, {key: False}) is False


def test_build_bucket_key_matches_mae_mfe_label_format():
    """analytics/mae_mfe.py::compute_conditional_mae_distribution'ın
    "|".join(f"{field}={value}"...) ürettiği etiketle BİREBİR aynı olmalı
    — dashboard'daki "Kova" sütunundaki metin doğrudan ayar anahtarı."""
    assert (
        build_bucket_key("LONG", "bull_trend", "normal", "crypto")
        == "direction=LONG|regime=bull_trend|volatility_regime=normal|asset_class=crypto"
    )


def test_build_bucket_key_defaults_asset_class_to_unknown():
    assert (
        build_bucket_key("LONG", "bull_trend", "normal")
        == "direction=LONG|regime=bull_trend|volatility_regime=normal|asset_class=unknown"
    )


def test_build_bucket_key_reflects_group_by_order():
    from analytics.barrier_table_repository import GROUP_BY

    key = build_bucket_key("SHORT", "insufficient_data", "high", "equity")
    parts = key.split("|")
    assert [p.split("=")[0] for p in parts] == list(GROUP_BY)
