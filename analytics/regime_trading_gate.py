"""Rejim Aç/Kapa Kapısı — kullanıcı isteği (2026-08-27): "sistemin
işlem aldığı rejimleri de aç kapa yapabilirsek süper olur."
market_regime = "{trend}_{volatility_regime}" (pyramid_regime_gate.py/
strategy_regime_gate.py ile AYNI format, services/position_closer.py::
_extract_market_regime ile tutarlı) — yeni bir rejim tanımı icat
edilmiyor."""


def is_regime_trading_blocked(market_regime: str | None, enabled_map: dict) -> bool:
    """True dönerse bu rejimde yeni giriş engellenmeli. market_regime
    None/bilinmiyorsa hiç engellenmez (bu kapının kapsamı dışında —
    "bilinmeyen rejim" ayrı, kasıtlı olarak farklı disiplinli bir
    problem, bkz. pyramid_regime_gate.py'nin fail-closed'ı). enabled_
    map'te hiç kaydı olmayan bir rejim varsayılan AÇIK sayılır (fail-
    open — asset_class_trading_gate.py ile AYNI gerekçe, bu bir
    kullanıcı tercihi kapısı, güvenlik kapısı değil)."""
    if market_regime is None:
        return False
    return enabled_map.get(market_regime, True) is False
