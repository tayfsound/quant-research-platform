"""Rejim Aç/Kapa Kapısı — kullanıcı isteği (2026-08-27): "sistemin
işlem aldığı rejimleri de aç kapa yapabilirsek süper olur."
market_regime = "{trend}_{volatility_regime}" (pyramid_regime_gate.py/
strategy_regime_gate.py ile AYNI format, services/position_closer.py::
_extract_market_regime ile tutarlı) — yeni bir rejim tanımı icat
edilmiyor."""


def is_regime_trading_blocked(
    market_regime: str | None,
    enabled_map: dict,
    direction: str | None = None,
    long_override_regimes: frozenset[str] | set[str] = frozenset(),
) -> bool:
    """True dönerse bu rejimde yeni giriş engellenmeli. market_regime
    None/bilinmiyorsa hiç engellenmez (bu kapının kapsamı dışında —
    "bilinmeyen rejim" ayrı, kasıtlı olarak farklı disiplinli bir
    problem, bkz. pyramid_regime_gate.py'nin fail-closed'ı). enabled_
    map'te hiç kaydı olmayan bir rejim varsayılan AÇIK sayılır (fail-
    open — asset_class_trading_gate.py ile AYNI gerekçe, bu bir
    kullanıcı tercihi kapısı, güvenlik kapısı değil).

    Faz 420 (2026-09-06) — kullanıcı bulgusu: kullanıcı 3 düşüş rejimini
    kapattı ama gerçek veri gösterdi ki kayıp neredeyse TAMAMEN SHORT'tan
    geliyordu — bearish_normal'da LONG aslında GÜÇLÜ kârlıydı (n=225,
    %88,9 kazanma, +$620,65) SHORT aynı rejimde -$5.728 kaybediyordu.
    `long_override_regimes` — bu KÜMEDEKİ bir rejimde LONG kararları,
    rejim kapalı olsa bile ASLA engellenmez (SADECE LONG, SHORT hâlâ
    tam engelli) — kanıt SADECE bearish_normal için yeterince güçlüydü
    (bearish_low başabaş, bearish_high n=4 önemsiz), bu yüzden varsayılan
    override kümesi SADECE bearish_normal içeriyor (bkz. app_settings_
    repository.py::DEFAULTS)."""
    if market_regime is None:
        return False
    blocked = enabled_map.get(market_regime, True) is False
    if not blocked:
        return False
    if direction and direction.upper() == "LONG" and market_regime in long_override_regimes:
        return False
    return True
