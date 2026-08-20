"""TP/SL Confluence'ın girdisini GERÇEK piyasa verisinden toplayan tek
kaynak — Faz 299. analytics/tp_sl_confluence.py saf (pure) kalıyor,
gerçek veriye dokunan kod burada. Mevcut ATR-tabanlı (engines/
cognitive_pipeline.py::RiskTargetStage'in statik fallback formülüyle
BİREBİR AYNI) stop/target'ın gerçek bir yapısal confluence bölgesine
yakın olup olmadığını ölçer — RiskTargetStage'in kendisini DEĞİŞTİRMEZ."""
from analytics.tp_sl_confluence import compute_confluence_zones, compute_price_levels, find_nearby_confluence_zone
from market_data.features.signal_engine import compute_daily_atr_pct
from market_data.ingestion.data_provider import RoutingProvider

DEFAULT_STOP_ATR_MULT_LONG = 2.5
DEFAULT_TARGET_ATR_MULT_LONG = 6.89
DEFAULT_STOP_ATR_MULT_SHORT = 2.5
DEFAULT_TARGET_ATR_MULT_SHORT = 1.4
DEFAULT_MIN_STOP_PCT = 0.045


def _analyze_symbol(
    provider: RoutingProvider, symbol: str,
    stop_mult_long: float, target_mult_long: float,
    stop_mult_short: float, target_mult_short: float,
    min_stop_pct: float,
) -> dict | None:
    try:
        hourly = provider.get_ohlcv(symbol, "1h", limit=200)
        daily = provider.get_ohlcv(symbol, "1d", limit=30)
    except Exception:
        return None
    if len(hourly) < 20 or len(daily) < 15:
        return None

    current_price = hourly[-1].close
    daily_atr_pct = compute_daily_atr_pct(daily, period=14)
    if not daily_atr_pct or current_price <= 0:
        return None

    levels = compute_price_levels(hourly, daily, current_price)
    zones = compute_confluence_zones(levels)
    strong_zones = [z for z in zones if z["method_count"] >= 2]

    def _distances(stop_mult: float, target_mult: float) -> tuple[float, float]:
        stop_pct = stop_mult * daily_atr_pct
        target_pct = target_mult * daily_atr_pct
        if stop_pct < min_stop_pct:
            scale = min_stop_pct / stop_pct
            stop_pct *= scale
            target_pct *= scale
        return stop_pct, target_pct

    # Faz 320 — target_atr_mult artık yöne göre farklı (RiskTargetStage
    # ile AYNI), bu yüzden LONG/SHORT mesafeleri artık BAĞIMSIZ hesaplanıyor
    # (eskiden tek bir stop_pct/target_pct ikisi için de kullanılıyordu).
    long_stop_pct, long_target_pct = _distances(stop_mult_long, target_mult_long)
    short_stop_pct, short_target_pct = _distances(stop_mult_short, target_mult_short)

    long_stop = current_price * (1 - long_stop_pct)
    long_target = current_price * (1 + long_target_pct)
    short_stop = current_price * (1 + short_stop_pct)
    short_target = current_price * (1 - short_target_pct)

    return {
        "symbol": symbol,
        "confluence_zone_count": len(strong_zones),
        "long_stop_near_confluence": find_nearby_confluence_zone(long_stop, zones) is not None,
        "long_target_near_confluence": find_nearby_confluence_zone(long_target, zones) is not None,
        "short_stop_near_confluence": find_nearby_confluence_zone(short_stop, zones) is not None,
        "short_target_near_confluence": find_nearby_confluence_zone(short_target, zones) is not None,
    }


def gather_tp_sl_confluence() -> dict:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        watchlist_raw = repo.get("watchlist") or ""
        stop_mult_long = float(repo.get("stop_atr_mult_long") or DEFAULT_STOP_ATR_MULT_LONG)
        target_mult_long = float(repo.get("target_atr_mult_long") or DEFAULT_TARGET_ATR_MULT_LONG)
        stop_mult_short = float(repo.get("stop_atr_mult_short") or DEFAULT_STOP_ATR_MULT_SHORT)
        target_mult_short = float(repo.get("target_atr_mult_short") or DEFAULT_TARGET_ATR_MULT_SHORT)
        min_stop_pct = float(repo.get("min_stop_pct") or DEFAULT_MIN_STOP_PCT)

    symbols = [s.strip() for s in watchlist_raw.split(",") if s.strip()]
    provider = RoutingProvider()

    results = []
    for symbol in symbols:
        result = _analyze_symbol(
            provider, symbol, stop_mult_long, target_mult_long,
            stop_mult_short, target_mult_short, min_stop_pct,
        )
        if result is not None:
            results.append(result)

    n = len(results)
    if n == 0:
        return {
            "symbols_analyzed": 0,
            "avg_confluence_zones_per_symbol": 0.0,
            "pct_long_stop_near_confluence": 0.0,
            "pct_long_target_near_confluence": 0.0,
            "pct_short_stop_near_confluence": 0.0,
            "pct_short_target_near_confluence": 0.0,
            "by_symbol": [],
        }

    return {
        "symbols_analyzed": n,
        "avg_confluence_zones_per_symbol": round(
            sum(r["confluence_zone_count"] for r in results) / n, 2
        ),
        "pct_long_stop_near_confluence": round(
            sum(r["long_stop_near_confluence"] for r in results) / n, 4
        ),
        "pct_long_target_near_confluence": round(
            sum(r["long_target_near_confluence"] for r in results) / n, 4
        ),
        "pct_short_stop_near_confluence": round(
            sum(r["short_stop_near_confluence"] for r in results) / n, 4
        ),
        "pct_short_target_near_confluence": round(
            sum(r["short_target_near_confluence"] for r in results) / n, 4
        ),
        "by_symbol": results,
    }
