"""Faz 352 — Regime Reversal Guardian.

Kullanıcı fikri (2026-08-22): "piyasa her an dönüş yapabilir... bir yönde
art arda pozisyonlar stop olmaya başlarsa sistem yön değişikliği
konusunda şüphelenmeye başlamalı." GERÇEK, o anda yaşanan bir olayla
doğrulandı: LONG'da art arda 14 stop-loss (birbirinden bağımsız birçok
sembolde, ~2 saatlik bir pencerede), aynı anda 275 açık LONG'un 170'i
zararda — kullanıcı onayıyla 107 kârdaki LONG elle kapatıldı (+$1566.70
kilitlendi), bu modül aynı tepkiyi KALICI/OTOMATİK hale getiriyor.

İki parça:
1. Ölçüm: bir yönün son kapanışlarında ardışık stop-loss sayısı (bkz.
   analytics/regime_reversal.py::consecutive_stop_streak) — kill switch'in
   GLOBAL sayacının YÖN-bazlı hali. Stateless: hiçbir "duraklatıldı"
   bayrağı persiste edilmiyor, her zaman GERÇEK kapanmış işlem
   geçmişinden taze hesaplanıyor — bir kazanç gelince streak sıfırlanır,
   duraklama kendiliğinden kalkar.
2. Aksiyon (SADECE bu iki tanesi, üçüncüsü yok — yön kararını hiç
   etkilemiyor): (a) o yöndeki KÂRDAKİ açık pozisyonlar TAZE fiyattan
   defensif kapatılır (services/position_closer.py::close_partial ile
   AYNI, zaten üretimde kanıtlanmış primitif — /positions/close-profitable
   endpoint'iyle AYNI mantık, sadece TEK bir yöne filtrelenmiş).
   (b) MetaStage'e eklenen bir gate (bkz. engines/cognitive_pipeline.py)
   streak eşiği aşan yönde yeni pozisyon açılmasını WAIT'e zorluyor —
   Faz 342'nin bearish_low SHORT gate'iyle AYNI desen."""
import time

import structlog

logger = structlog.get_logger()

_STREAK_CACHE_TTL_SECONDS = 60.0
_streak_cache: tuple[float, dict[str, int]] | None = None

# Faz 352 — kill switch'in kendi exclude_experiment_bucket kullanımıyla
# AYNI gerekçe: mekanik stratejiler (pump_fade/basis_arb) AI'ın karar/
# confidence sisteminden tamamen yalıtık, kendi risk yönetimlerine sahip
# — bunların kapanışları council'in GERÇEKTEN yön konusunda haklı çıkıp
# çıkmadığını yansıtmıyor, streak'e karışırsa yanlış bir alarm/sessizlik
# üretebilir. position_pool_v1 İSTİSNA: o da council kararı, sadece
# GECİKMELİ açılmış — dahil edilmeli.
_MECHANICAL_EXPERIMENT_BUCKETS = {"pump_fade_v1", "basis_arb_v1"}

_STREAK_FETCH_LIMIT = 100


def _load_settings() -> tuple[bool, int]:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        enabled = repo.get("reversal_guardian_enabled") == "true"
        threshold = int(repo.get("reversal_guardian_consecutive_stop_threshold"))
    return enabled, threshold


def compute_direction_stop_streaks() -> dict[str, int]:
    """GERÇEK kapanmış işlemlerden (council path, mekanik stratejiler
    hariç) LONG/SHORT için ayrı ayrı ardışık stop-loss sayısı."""
    from analytics.regime_reversal import consecutive_stop_streak
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    streaks: dict[str, int] = {}
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        for direction in ("LONG", "SHORT"):
            trades = persistor.list_closed_trades(limit=_STREAK_FETCH_LIMIT, direction=direction)
            filtered = [
                t for t in trades
                if t.get("experiment_bucket") not in _MECHANICAL_EXPERIMENT_BUCKETS
            ]
            streaks[direction] = consecutive_stop_streak(filtered)
    return streaks


def get_cached_direction_stop_streaks() -> dict[str, int]:
    """MetaStage'in (yüksek frekanslı karar hattı) çağırdığı TTL'li
    önbellekli sürüm — services/self_model_gatherer.py::get_cached_
    self_reliability_snapshot ile AYNI desen. Periyodik guardian görevi
    hâlâ taze compute_direction_stop_streaks()'i doğrudan kullanıyor."""
    global _streak_cache
    now = time.monotonic()
    if _streak_cache is not None and (now - _streak_cache[0]) < _STREAK_CACHE_TTL_SECONDS:
        return _streak_cache[1]
    streaks = compute_direction_stop_streaks()
    _streak_cache = (now, streaks)
    return streaks


def is_direction_paused(direction: str) -> bool:
    """MetaStage'in çağırdığı fail-closed kontrol — herhangi bir hata/
    eksik ayar durumunda "duraklatılmamış" varsayılır (mevcut davranış
    hiç bozulmaz), asla icat edilmiş bir duraklama uygulanmaz."""
    try:
        enabled, threshold = _load_settings()
        if not enabled:
            return False
        streaks = get_cached_direction_stop_streaks()
        return streaks.get(direction, 0) >= threshold
    except Exception as exc:
        logger.warning("regime_reversal_guardian_check_failed", error=str(exc))
        return False


def sweep_close_profitable_positions(direction: str) -> dict:
    """api/rest/positions.py::close_profitable_positions ile AYNI, zaten
    üretimde kanıtlanmış mantık (önce net kâr tahmini, SADECE pozitif
    çıkanlar kapatılır) — SADECE tek bir yöne filtrelenmiş."""
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider
    from services.position_closer import PositionCloser, fetch_current_prices_by_symbol

    closer = PositionCloser(RoutingProvider())
    with SessionFactory.get_session() as session:
        positions = DecisionPersistor(session).list_open_positions(limit=None)

    direction_positions = [p for p in positions if (p.get("direction") or "").upper() == direction]
    prices = fetch_current_prices_by_symbol({p["symbol"] for p in direction_positions})

    closed = []
    for pos in direction_positions:
        price = prices.get(pos["symbol"])
        if price is None:
            continue
        estimated_net_pnl = closer.estimate_net_pnl_if_closed_now(pos, price)
        if estimated_net_pnl <= 0:
            continue
        with SessionFactory.get_session() as session:
            try:
                result = closer.close_partial(
                    DecisionPersistor(session), str(pos["id"]), 1.0,
                    exit_reason="regime_reversal_guardian",
                )
            except ValueError:
                continue
        closed.append({"symbol": pos["symbol"], "pnl": result["pnl"]})

    return {"direction": direction, "closed_count": len(closed), "closed": closed}


def run_guardian_sweep() -> dict:
    """Periyodik Celery görevinden çağrılır (bkz. services/tasks.py::
    regime_reversal_guardian_task). Kapalıyken (varsayılan durum
    korunuyor) ya da hiçbir yön eşiği aşmamışken sıfır maliyetli no-op —
    idempotent: zaten kapatılmış pozisyonlar için tekrar çağrılması
    zararsız (list_open_positions zaten kapananları döndürmez)."""
    enabled, threshold = _load_settings()
    if not enabled:
        return {"enabled": False}

    streaks = compute_direction_stop_streaks()
    result: dict = {"enabled": True, "threshold": threshold, "streaks": streaks, "actions": []}
    for direction, streak in streaks.items():
        if streak >= threshold:
            sweep = sweep_close_profitable_positions(direction)
            result["actions"].append(sweep)
            if sweep["closed_count"] > 0:
                logger.warning(
                    "regime_reversal_guardian_triggered",
                    direction=direction, streak=streak, threshold=threshold,
                    closed_count=sweep["closed_count"],
                )
    return result
