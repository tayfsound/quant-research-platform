"""Faz 188: kullanıcının kendi risk/mod ayarlarını gerçekten kontrol
edebilmesi için API — bkz. database/repositories/app_settings_repository.py."""
from fastapi import APIRouter, Depends, HTTPException

from contracts.auth import Role
from database.repositories.app_settings_repository import (
    CANDLE_TIMEFRAME_SECONDS,
    CANDLE_TIMEFRAMES,
    DEFAULTS,
    DISPLAY_CURRENCIES,
    TRADE_HORIZON_SECONDS,
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
    elif key == "trade_horizon":
        if value not in TRADE_HORIZON_SECONDS:
            raise HTTPException(400, f"trade_horizon must be one of {list(TRADE_HORIZON_SECONDS)}")
    elif key == "min_seconds_between_trades":
        try:
            if int(value) < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "min_seconds_between_trades must be a non-negative integer")
    elif key == "ai_enabled":
        if value not in ("true", "false"):
            raise HTTPException(400, "ai_enabled must be 'true' or 'false'")
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
    else:
        raise HTTPException(400, f"unknown setting key: {key}")


def _validate_horizon_timeframe_consistency(key: str, value: str, session) -> None:
    """Faz 224 review bulgusu (B): trade_horizon ve candle_timeframe
    bağımsız ayarlar olduğu için kullanıcı Settings'ten ikisini de ayrı
    ayrı değiştirebilir — tam olarak Faz 215'teki gerçek bug'a (pozisyon,
    sinyalin üretildiği mum bile tamamlanmadan kapanıyordu) yol açan
    kombinasyona tekrar düşülebilir. trade_horizon_seconds, candle_
    timeframe_seconds'ın en az 2 katı olmalı — sinyal en az bir kez
    tazelenene kadar pozisyonun kapanmaması için."""
    repo = AppSettingsRepository(session)
    if key == "trade_horizon":
        horizon_seconds = TRADE_HORIZON_SECONDS[value]
        candle_seconds = CANDLE_TIMEFRAME_SECONDS[repo.get("candle_timeframe")]
    elif key == "candle_timeframe":
        horizon_seconds = TRADE_HORIZON_SECONDS[repo.get("trade_horizon")]
        candle_seconds = CANDLE_TIMEFRAME_SECONDS[value]
    else:
        return

    if horizon_seconds < candle_seconds * 2:
        raise HTTPException(
            400,
            f"trade_horizon ({horizon_seconds}s) candle_timeframe'in ({candle_seconds}s) en az "
            "2 katı olmalı — yoksa pozisyon, sinyalin üretildiği mum tamamlanmadan kapanabilir "
            "(bkz. Faz 215).",
        )


@router.get("/")
async def get_settings_(user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        return {"settings": AppSettingsRepository(session).get_all()}


@router.get("/defaults")
async def get_defaults(user: AuthContext = Depends(get_current_user)):
    return {"defaults": DEFAULTS, "trade_horizon_seconds": TRADE_HORIZON_SECONDS}


@router.get("/currency-rates")
async def get_currency_rates(user: AuthContext = Depends(get_current_user)):
    """Faz 224: kullanıcı isteği — PnL/fiyatları USD dışında (BTC/TRY)
    görebilme. Gerçek, canlı oranlar — Binance'in kendi piyasalarından
    (BTCUSDT, USDTTRY), ayrı bir FX API'sine gerek yok."""
    from market_data.fx.currency_provider import fetch_currency_rates
    return fetch_currency_rates()


@router.post("/reset-defaults")
async def reset_to_defaults(user: AuthContext = Depends(require_role(Role.OPERATOR))):
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
async def set_setting(key: str, value: str, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    # Faz 192 düzeltmesi: bunlar risk_limits.py'deki hash-imzalı, çok
    # kullanıcılı onay gerektiren eşiklerden farklı — Dashboard'daki
    # Start/Stop ve Test/Live gibi günlük operasyonel anahtarlar. ADMIN
    # zorunluluğu tek kullanıcılı yerel kurulumda gereksiz sürtünmeydi
    # (gerçek bulgu: kullanıcı Dashboard'da "insufficient_role" hatası aldı).
    _validate(key, value)
    with SessionFactory.get_session() as session:
        _validate_horizon_timeframe_consistency(key, value, session)
        AppSettingsRepository(session).set(key, value, updated_by=user.username)
        return {"key": key, "value": value, "updated_by": user.username}
