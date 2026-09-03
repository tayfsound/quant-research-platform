"""Market State Cluster Engine'in girdisini GERÇEK piyasa verisinden
toplayan tek kaynak — Faz 401 (Market State Katmanı Faz 1). analytics/
market_state_cluster_engine.py saf (pure) kalıyor, gerçek veriye dokunan
kod burada.

services/orchestrator.py::_apply_portfolio_fusion'ın AYNI ThreadPoolExecutor
paralel-çekim deseni (150+ sembolü sıralı çekmek onlarca saniye eklerdi) —
ama tek bir cycle'ın `directional` önerileriyle SINIRLI değil, watchlist'in
TAMAMI için periyodik olarak (5dk, refresh_market_state_cluster_task)
çalışıyor. candle_lookback ayarı (Faz 401'de 100'den 250'ye yükseltildi —
long_term_trend_regime'ın 200-EMA'sı için asgari 220 gerekiyor) ile AYNI
sembol/timeframe evreni kullanılıyor ki cluster hesabı, canlı karar
hattının GERÇEKTEN gördüğü rejimle tutarlı olsun."""
from concurrent.futures import ThreadPoolExecutor

from analytics.market_state_cluster_engine import compute_cluster_market_state
from analytics.measurement_stability import compute_stability
from market_data.features.market_state_engine import compute_market_state
from market_data.features.signal_engine import compute_quant_signals, compute_technical_signals
from risk.cross_symbol_correlation import describe_correlation_pairs

STABILITY_LOOKBACK_SNAPSHOTS = 12


def _attach_correlation_stability(pairs: list[dict], past_snapshots: list[dict]) -> None:
    """Faz 407 — bkz. risk/cross_symbol_correlation.py::describe_
    correlation_pairs docstring'i. Historical_analog/agent_combination_
    reliability gatherer'larıyla AYNI desen: SADECE gözlem, hiçbir çift
    filtrelenmiyor/reddedilmiyor, karar hattına hiç bağlanmıyor."""
    past_by_key: dict[str, list[float]] = {}
    for snap in past_snapshots:
        for p in (snap.get("result") or {}).get("pairs") or []:
            past_by_key.setdefault(p["pair"], []).append(p.get("correlation"))

    for p in pairs:
        series = [*past_by_key.get(p["pair"], []), p["correlation"]]
        p["correlation_stability"] = compute_stability(series)


def gather_market_state_cluster() -> dict:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.repositories.correlation_report_repository import CorrelationReportRepository
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        watchlist = [s.strip() for s in settings_repo.get("watchlist").split(",") if s.strip()]
        timeframe = settings_repo.get("candle_timeframe")
        lookback = int(settings_repo.get("candle_lookback"))
        past_correlation_snapshots = CorrelationReportRepository(session).get_recent(
            STABILITY_LOOKBACK_SNAPSHOTS
        )

    provider = RoutingProvider()

    def _fetch_one(symbol: str) -> tuple[str, list]:
        try:
            return symbol, provider.get_ohlcv(symbol, timeframe, limit=lookback) or []
        except Exception:
            return symbol, []

    with ThreadPoolExecutor(max_workers=min(len(watchlist), 16) or 1) as pool:
        fetched = dict(pool.map(_fetch_one, watchlist))

    returns: dict[str, list[float]] = {}
    per_symbol_states: dict[str, dict] = {}
    for symbol, bars in fetched.items():
        closes = [bar.close for bar in bars]
        rets = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes)) if closes[i - 1]
        ]
        if len(rets) < 2:
            continue
        returns[symbol] = rets

        features = {**compute_technical_signals(bars), **compute_quant_signals(bars)}
        per_symbol_states[symbol] = compute_market_state(features)

    by_symbol = compute_cluster_market_state(returns, per_symbol_states)

    # Faz 407 — AYNI zaten-çekilmiş `returns`i yeniden kullanıyor, ek bir
    # API çağrısı yok. market_state ile ayrı bir rapora kaydediliyor
    # (correlation_report_repository.py) — karar hattına hiç bağlanmıyor,
    # SADECE gözlem.
    correlation_pairs = describe_correlation_pairs(returns)
    _attach_correlation_stability(correlation_pairs, past_correlation_snapshots)

    return {
        "by_symbol": by_symbol, "n_symbols": len(by_symbol),
        "correlation_pairs": correlation_pairs,
    }
