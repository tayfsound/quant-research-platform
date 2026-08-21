"""Faz 188: kullanıcının kendi risk/mod ayarlarını gerçekten kontrol
edebilmesi için API — bkz. database/repositories/app_settings_repository.py."""
from fastapi import APIRouter, Depends, HTTPException

from contracts.auth import Role
from database.repositories.app_settings_repository import (
    CANDLE_TIMEFRAMES,
    DEFAULTS,
    DISPLAY_CURRENCIES,
    AppSettingsRepository,
)
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user, require_role

router = APIRouter(prefix="/settings", tags=["settings"])


def _validate(key: str, value: str) -> None:
    if key == "trading_mode":
        if value not in ("test", "live"):
            raise HTTPException(400, "trading_mode must be 'test' or 'live'")
    elif key == "max_concurrent_positions":
        try:
            if int(value) < 1:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "max_concurrent_positions must be a positive integer")
    elif key == "max_capital_pct":
        try:
            v = float(value)
            if not (0 < v <= 1):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "max_capital_pct must be a number in (0, 1]")
    elif key == "starting_capital":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "starting_capital must be a positive number")
    elif key == "min_seconds_between_trades":
        try:
            if int(value) < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "min_seconds_between_trades must be a non-negative integer")
    elif key == "ai_enabled":
        if value not in ("true", "false"):
            raise HTTPException(400, "ai_enabled must be 'true' or 'false'")
    elif key == "kill_switch_consecutive_losses":
        try:
            if int(value) < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "kill_switch_consecutive_losses must be a non-negative integer (0 = disabled)")
    elif key in ("drawdown_sizing_start_after_losses", "drawdown_sizing_full_reduction_at_losses"):
        try:
            if int(value) < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, f"{key} must be a non-negative integer")
    elif key == "watchlist":
        symbols = [s.strip() for s in value.split(",") if s.strip()]
        if not symbols:
            raise HTTPException(400, "watchlist must be a non-empty comma-separated symbol list")
    elif key == "max_portfolio_var_pct":
        try:
            v = float(value)
            if not (0 < v <= 1):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "max_portfolio_var_pct must be a number in (0, 1]")
    elif key in ("act_threshold", "reduce_threshold"):
        try:
            v = float(value)
            if not (0 < v <= 1):
                raise ValueError
        except ValueError:
            raise HTTPException(400, f"{key} must be a number in (0, 1]")
    elif key == "min_profit_target_pct":
        try:
            v = float(value)
            if not (0 <= v < 1):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "min_profit_target_pct must be a number in [0, 1)")
    elif key == "candle_timeframe":
        if value not in CANDLE_TIMEFRAMES:
            raise HTTPException(400, f"candle_timeframe must be one of {list(CANDLE_TIMEFRAMES)}")
    elif key == "candle_lookback":
        # Faz 222: kullanıcı bulgusu — "20-1000 arası çok yetersiz." Eski
        # 1000 tavanı keyfi değildi, Binance'in TEK istekteki gerçek API
        # tavanıydı (doğrulandı: limit=1001 istense bile 1000 döner).
        # BinanceAdapter.fetch_ohlcv artık limit>1000 için pagination
        # yapıyor (art arda 1000'er mumluk istekler), bu yüzden tavan
        # yükseltildi. 5000 üst sınırı: 15m'de ~52 gün geçmiş (yeni
        # long_term_trend_regime göstergesi için anlamlı), ama tek
        # cycle'da sembol başına en fazla 5 art arda Binance isteğiyle
        # sınırlı kalıyor (watchlist geneli için makul gecikme/yük).
        try:
            if not (20 <= int(value) <= 5000):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "candle_lookback must be an integer in [20, 5000]")
    elif key == "display_currency":
        if value not in DISPLAY_CURRENCIES:
            raise HTTPException(400, f"display_currency must be one of {list(DISPLAY_CURRENCIES)}")
    elif key == "symbol_leverage":
        # Faz 255: kullanıcı isteği — token bazlı kaldıraç. JSON dict,
        # {"BTCUSDT": 10, "XAUTUSDT": 25} gibi. 1-125 aralığı Binance'in
        # gerçek futures kaldıraç sınırına (max_leverage=125,
        # exchange_gateway/binance/adapter.py) dayanıyor — icat edilmiş
        # bir tavan değil.
        import json as _json
        try:
            mapping = _json.loads(value)
            if not isinstance(mapping, dict):
                raise ValueError
            for lev in mapping.values():
                lev_f = float(lev)
                if not (1.0 <= lev_f <= 125.0):
                    raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(400, "symbol_leverage must be a JSON object of {symbol: leverage in [1, 125]}")
    elif key == "medium_term_enabled":
        if value not in ("true", "false"):
            raise HTTPException(400, "medium_term_enabled must be 'true' or 'false'")
    elif key == "execution_mode":
        # Faz 315 — "trading_mode" ile KARIŞTIRILMASIN, tamamen ayrı bir
        # kavram (bkz. DEFAULTS'taki not).
        if value not in ("simulated", "testnet"):
            raise HTTPException(400, "execution_mode must be 'simulated' or 'testnet'")
    elif key == "execution_mode_symbols":
        # symbol_leverage ile AYNI desen — JSON dict, {"BTCUSDT": "testnet"}.
        import json as _json
        try:
            mapping = _json.loads(value)
            if not isinstance(mapping, dict):
                raise ValueError
            for mode in mapping.values():
                if mode not in ("simulated", "testnet"):
                    raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(
                400, "execution_mode_symbols must be a JSON object of {symbol: 'simulated'|'testnet'}"
            )
    elif key == "medium_term_capital_pct":
        try:
            v = float(value)
            if not (0 < v <= 1):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "medium_term_capital_pct must be a number in (0, 1]")
    elif key == "medium_term_timeframe":
        # Faz 259: kullanıcı isteği "günlük/4 saatlik" — kısa-vadeli
        # candle_timeframe'in aksine (1m/5m gibi gürültülü değerler dahil
        # olabilir) burası kasıtlı olarak sadece "sakin" iki seçenekle
        # sınırlı.
        if value not in ("4h", "1d"):
            raise HTTPException(400, "medium_term_timeframe must be '4h' or '1d'")
    elif key == "medium_term_max_concurrent":
        try:
            if int(value) < 1:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "medium_term_max_concurrent must be a positive integer")
    elif key == "multi_timeframe_cascade_enabled":
        # Faz 268-sonrası — kullanıcı isteği: her işlemden önce en az
        # 15dk/4h/1g'nin AYRI AYRI değerlendirilmesi ("her biri farklı bir
        # hikaye anlatıyor olabilir"). Mekanizma (services/orchestrator.py
        # ::propose()) zaten vardı ama hem varsayılan kapalıydı hem de
        # Settings API'sinde hiç doğrulanmıyordu (kullanıcı bunu API'den
        # HİÇ değiştiremezdi).
        if value not in ("true", "false"):
            raise HTTPException(400, "multi_timeframe_cascade_enabled must be 'true' or 'false'")
    elif key == "multi_timeframe_cascade_timeframes":
        timeframes = [tf.strip() for tf in value.split(",") if tf.strip()]
        if not timeframes or any(tf not in CANDLE_TIMEFRAMES for tf in timeframes):
            raise HTTPException(400, f"multi_timeframe_cascade_timeframes must be a comma-separated subset of {list(CANDLE_TIMEFRAMES)}")
    elif key == "adaptive_barrier_enabled":
        if value not in ("true", "false"):
            raise HTTPException(400, "adaptive_barrier_enabled must be 'true' or 'false'")
    elif key == "pump_fade_enabled":
        if value not in ("true", "false"):
            raise HTTPException(400, "pump_fade_enabled must be 'true' or 'false'")
    elif key == "pump_fade_max_loss_per_trade_usd":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_max_loss_per_trade_usd must be a positive number")
    elif key == "pump_fade_max_open_positions":
        try:
            if int(value) < 1:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_max_open_positions must be a positive integer")
    elif key == "pump_fade_max_loss_circuit_breaker_usd":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_max_loss_circuit_breaker_usd must be a positive number")
    elif key == "pump_fade_max_total_capital_pct":
        try:
            v = float(value)
            if not (0 < v <= 1):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_max_total_capital_pct must be a number in (0, 1]")
    elif key == "pump_fade_leverage":
        try:
            v = float(value)
            if not (1.0 <= v <= 125.0):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_leverage must be a number in [1, 125]")
    elif key == "pump_fade_min_gain_pct":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_min_gain_pct must be a positive number (1.0 = %100)")
    elif key == "pump_fade_reentry_min_gain_pct":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_reentry_min_gain_pct must be a positive number (1.0 = %100)")
    elif key == "pump_fade_lookback_hours":
        try:
            if int(value) < 1:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_lookback_hours must be a positive integer")
    elif key == "pump_fade_stop_distance_pct":
        try:
            v = float(value)
            if not (0 < v < 1):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_stop_distance_pct must be a number in (0, 1)")
    elif key == "pump_fade_take_profit_pct":
        try:
            v = float(value)
            if not (0 < v < 1):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pump_fade_take_profit_pct must be a number in (0, 1)")
    elif key == "pairs_trading_leg_capital_usd":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "pairs_trading_leg_capital_usd must be a positive number")
    elif key == "basis_arbitrage_enabled":
        if value not in ("true", "false"):
            raise HTTPException(400, "basis_arbitrage_enabled must be 'true' or 'false'")
    elif key == "basis_arbitrage_min_basis_pct":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "basis_arbitrage_min_basis_pct must be a positive number")
    elif key == "basis_arbitrage_min_funding_rate":
        try:
            float(value)
        except ValueError:
            raise HTTPException(400, "basis_arbitrage_min_funding_rate must be a number")
    elif key == "basis_arbitrage_leg_capital_usd":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "basis_arbitrage_leg_capital_usd must be a positive number")
    elif key == "basis_arbitrage_max_open_pairs":
        try:
            if int(value) < 1:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "basis_arbitrage_max_open_pairs must be a positive integer")
    elif key == "basis_arbitrage_max_hold_hours":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "basis_arbitrage_max_hold_hours must be a positive number")
    elif key == "max_open_positions_per_symbol_direction":
        # Faz 268-sonrası: gerçek olaydan (54 XAUTUSDT SHORT aynı anda
        # açık bulundu) eklenen kontrol — kullanıcı Settings sayfasından
        # kendi ayarlayabilsin diye eklendi, önceden sadece koddaki
        # varsayılana (5) sabitliydi.
        try:
            if int(value) < 1:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "max_open_positions_per_symbol_direction must be a positive integer")
    else:
        raise HTTPException(400, f"unknown setting key: {key}")


@router.get("/")
def get_settings_(user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        # Faz 268-sonrası: kullanıcı isteği — dashboard'un kill switch'in
        # GERÇEKTEN tetiklendiğini (updated_by='kill_switch') manuel
        # Durdur düğmesinden ayırt edip bildirim gösterebilmesi için.
        return {
            "settings": repo.get_all(),
            "ai_enabled_updated_by": repo.get_updated_by("ai_enabled"),
        }


@router.get("/defaults")
def get_defaults(user: AuthContext = Depends(get_current_user)):
    return {"defaults": DEFAULTS}


@router.get("/currency-rates")
def get_currency_rates(user: AuthContext = Depends(get_current_user)):
    """Faz 224: kullanıcı isteği — PnL/fiyatları USD dışında (BTC/TRY)
    görebilme. Gerçek, canlı oranlar — Binance'in kendi piyasalarından
    (BTCUSDT, USDTTRY), ayrı bir FX API'sine gerek yok."""
    from market_data.fx.currency_provider import fetch_currency_rates
    return fetch_currency_rates()


@router.post("/reset-defaults")
def reset_to_defaults(user: AuthContext = Depends(require_role(Role.OPERATOR))):
    """Faz 215: kullanıcı isteği — tek tuşla, komisyona ezilmeden $1-5
    net kâr hedefleyecek şekilde matematiksel olarak hesaplanmış
    varsayılanlara dönüş (bkz. DEFAULTS'taki gerekçe).

    Gerçek bulgu: bu route /{key} route'undan SONRA tanımlıysa, FastAPI
    kayıt sırasına göre eşleştirdiği için POST /settings/reset-defaults
    isteği set_setting(key="reset-defaults")'a düşüyordu (422 — value
    query param eksik). Route /{key}'den ÖNCE tanımlanmalı."""
    with SessionFactory.get_session() as session:
        reset = AppSettingsRepository(session).reset_to_defaults(updated_by=user.username)
        return {"reset": reset}


@router.post("/{key}")
def set_setting(key: str, value: str, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    # Faz 192 düzeltmesi: bunlar risk_limits.py'deki hash-imzalı, çok
    # kullanıcılı onay gerektiren eşiklerden farklı — Dashboard'daki
    # Start/Stop ve Test/Live gibi günlük operasyonel anahtarlar. ADMIN
    # zorunluluğu tek kullanıcılı yerel kurulumda gereksiz sürtünmeydi
    # (gerçek bulgu: kullanıcı Dashboard'da "insufficient_role" hatası aldı).
    _validate(key, value)
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(key, value, updated_by=user.username)
        return {"key": key, "value": value, "updated_by": user.username}
