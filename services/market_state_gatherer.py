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
from market_data.features.market_state_engine import compute_market_state
from market_data.features.signal_engine import compute_quant_signals, compute_technical_signals


def gather_market_state_cluster() -> dict:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        watchlist = [s.strip() for s in settings_repo.get("watchlist").split(",") if s.strip()]
        timeframe = settings_repo.get("candle_timeframe")
        lookback = int(settings_repo.get("candle_lookback"))

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
    return {"by_symbol": by_symbol, "n_symbols": len(by_symbol)}
