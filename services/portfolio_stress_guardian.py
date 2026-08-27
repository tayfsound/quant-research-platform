"""Backlog #13 (2026-08-26) — kullanıcı örneği: "100 pozisyonum var, 70'i
+20k kârda, 30'u riskli — kötüye giderse -50k olabilir, şimdi hepsini
kapatıp +2k'da kalmak -50k'dan iyidir." analytics/stress_testing.py (Faz
694-718, hiç bağlanmamıştı) zaten "gerçek tarihteki en kötü N-günlük
hareket şu an tekrar olsaydı ne olurdu" hesabını yapıyor — burası bunu
MEVCUT TÜM açık pozisyonların toplam notional'ına uygulayıp, stres
senaryosu net kârı net zarara çevirecekse SİSTEM GENELİNDE (tüm
experiment_bucket'lar — gerçek bir çöküş her şeyi birlikte vurur) hepsini
defansif kapatıyor.

Regime Reversal Guardian (Faz 352) ile AYNI mimari (periyodik tarama +
close_partial), iki temel farkla: (1) tetikleyici bir ardışık-stop
sayacı değil, GERÇEK tarihsel bir stres projeksiyonu; (2) SADECE kârdaki
pozisyonları değil TÜM açık pozisyonları kapatır — amaç yön-bazlı değil
sistemik: gerçek bir çöküş hem kazananları hem kaybedenleri birlikte
kötüleştirir, mevcut NET durumu şimdi kilitlemek daha güvenli."""
import structlog

logger = structlog.get_logger()


def _load_settings() -> tuple[bool, int, str, int]:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        enabled = repo.get("portfolio_stress_guardian_enabled") == "true"
        window_days = int(repo.get("portfolio_stress_guardian_window_days"))
        reference_symbol = repo.get("portfolio_stress_guardian_reference_symbol")
        history_days = int(repo.get("portfolio_stress_guardian_history_days"))
    return enabled, window_days, reference_symbol, history_days


def compute_portfolio_stress_projection() -> dict | None:
    """GERÇEK açık pozisyonlardan toplam notional (yön bazlı) + mark-to-
    market gerçekleşmemiş kâr/zarar; GERÇEK referans sembol (varsayılan
    BTCUSDT) geçmişinden en kötü N-günlük DÜŞÜŞ (LONG kitabına) ve en
    kötü N-günlük YÜKSELİŞ (SHORT kitabına) ayrı ayrı uygulanır — ikisi
    AYNI ANDA olamayacağı için (piyasa ya çöker ya patlar, ikisi birden
    değil) TOPLANMAZ, ikisinin arasından DAHA KÖTÜ olan projeksiyon
    alınır. Veri yetersizse (fail-closed) None döner."""
    from analytics.stress_testing import compute_worst_historical_drawdown
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import get_ohlcv_provider
    from services.position_closer import fetch_current_prices_by_symbol, gross_unrealized_pnl

    _, window_days, reference_symbol, history_days = _load_settings()

    with SessionFactory.get_session() as session:
        positions = DecisionPersistor(session).list_open_positions(limit=None)
    if not positions:
        return None

    prices = fetch_current_prices_by_symbol({p["symbol"] for p in positions})

    current_unrealized_pnl = 0.0
    long_notional = 0.0
    short_notional = 0.0
    for p in positions:
        price = prices.get(p["symbol"])
        pnl = gross_unrealized_pnl(p, price)
        if pnl is not None:
            current_unrealized_pnl += pnl
        entry_price = p.get("entry_price") or 0.0
        quantity = p.get("quantity") or 0.0
        notional = entry_price * quantity
        direction = (p.get("direction") or "").upper()
        if direction == "LONG":
            long_notional += notional
        elif direction == "SHORT":
            short_notional += notional

    try:
        bars = get_ohlcv_provider().get_ohlcv(reference_symbol, "1d", limit=history_days)
    except Exception:
        return None
    if len(bars) < 2:
        return None
    returns = [
        (bars[i].close - bars[i - 1].close) / bars[i - 1].close
        for i in range(1, len(bars))
        if bars[i - 1].close
    ]

    crash = compute_worst_historical_drawdown(returns, window_days)
    # SHORT kitabı icin en kotu senaryo bir DUSUS degil YUKSELIS —
    # getirileri negatize edip AYNI "en kotu N-gunluk" fonksiyonunu
    # calistirmak, orijinal serideki en BUYUK yukselisi verir (isareti
    # geri cevrilir) — ikinci, ayrı bir saf fonksiyon icat edilmiyor.
    pump = compute_worst_historical_drawdown([-r for r in returns], window_days)
    if crash is None or pump is None:
        return None
    worst_down_pct = crash["worst_cumulative_return_pct"]
    worst_up_pct = -pump["worst_cumulative_return_pct"]

    scenario_crash_pnl = current_unrealized_pnl + (worst_down_pct * long_notional)
    scenario_pump_pnl = current_unrealized_pnl + (worst_up_pct * short_notional)
    worst_case_projected_pnl = min(scenario_crash_pnl, scenario_pump_pnl)
    worse_scenario = "crash" if scenario_crash_pnl <= scenario_pump_pnl else "pump"

    return {
        "current_unrealized_pnl": round(current_unrealized_pnl, 2),
        "long_notional": round(long_notional, 2),
        "short_notional": round(short_notional, 2),
        "reference_symbol": reference_symbol,
        "window_days": window_days,
        "worst_down_pct": worst_down_pct,
        "worst_up_pct": worst_up_pct,
        "scenario_crash_pnl": round(scenario_crash_pnl, 2),
        "scenario_pump_pnl": round(scenario_pump_pnl, 2),
        "worst_case_projected_pnl": round(worst_case_projected_pnl, 2),
        "worse_scenario": worse_scenario,
    }


def is_triage_triggered(projection: dict) -> bool:
    """Kullanıcının kendi kararı: şu an net kârdaysam AMA stres senaryosu
    bunu net zarara çevirecekse, şimdi kilitle. Şu an zaten net zarardaysa
    (stres olmadan bile) bu mekanizma devreye girmez — o durum zaten
    kendi stop/hedeflerine bırakılmış demektir, farklı bir problem."""
    return projection["current_unrealized_pnl"] > 0 and projection["worst_case_projected_pnl"] < 0


def close_all_open_positions() -> dict:
    """Tetiklendiğinde TÜM açık pozisyonlar (yön/experiment_bucket fark
    etmeksizin) TAZE fiyattan kapatılır."""
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider
    from services.position_closer import PositionCloser, fetch_current_prices_by_symbol

    closer = PositionCloser(RoutingProvider())
    with SessionFactory.get_session() as session:
        positions = DecisionPersistor(session).list_open_positions(limit=None)

    prices = fetch_current_prices_by_symbol({p["symbol"] for p in positions})

    closed = []
    for pos in positions:
        if prices.get(pos["symbol"]) is None:
            continue
        with SessionFactory.get_session() as session:
            try:
                result = closer.close_partial(
                    DecisionPersistor(session), str(pos["id"]), 1.0,
                    exit_reason="portfolio_stress_guardian",
                )
            except ValueError:
                continue
        closed.append({"symbol": pos["symbol"], "pnl": result["pnl"]})
    return {"closed_count": len(closed), "closed": closed}


def run_portfolio_triage_sweep() -> dict:
    """Periyodik Celery görevinden çağrılır (bkz. services/tasks.py::
    portfolio_stress_guardian_task). Kapalıyken (varsayılan AÇIK — Regime
    Reversal Guardian ile AYNI gerekçe, koruyucu bir mekanizma) sıfır
    maliyetli no-op."""
    enabled, *_ = _load_settings()
    if not enabled:
        return {"enabled": False}

    projection = compute_portfolio_stress_projection()
    if projection is None:
        return {"enabled": True, "projection": None}

    triggered = is_triage_triggered(projection)
    result: dict = {"enabled": True, "projection": projection, "triggered": triggered}
    if triggered:
        sweep = close_all_open_positions()
        result["sweep"] = sweep
        if sweep["closed_count"] > 0:
            logger.warning(
                "portfolio_stress_guardian_triggered",
                projection=projection, closed_count=sweep["closed_count"],
            )
    return result
