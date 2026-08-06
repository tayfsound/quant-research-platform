"""Faz 236: kullanıcı isteği — "Backtests'i gerçek veri ile çalışır hale
getirelim." Bu oturumda scratchpad'de doğrulanan gerçek metodolojinin
(shadow_backtest.py) repo'ya taşınmış, kalıcı hali.

Mevcut backtest/cognitive_backtest_runner.py'den (dashboard'un "Run
Backtest" butonunun kullandığı, MockOHLCVAdapter ile sahte fiyat üreten
yol) KASITLI OLARAK farklı ve AYRI tutuluyor:
- O runner `ctx.market.features`'ı hiç doldurmuyor (dokümante edilmiş bir
  sınırlama) — ATR=0 olduğu için RiskTargetStage/DecisionFusion HER zaman
  reddediyor, 9 ajan council'i kör çalışıyor. Üstüne yön için gerçek
  council yerine sabit bir "close[-1]>=close[0]" sezgisi kullanıyor.
- Burası gerçek Binance geçmiş verisiyle, market_data/features/
  signal_engine.py'nin GERÇEK (üretimde de kullanılan) fonksiyonlarıyla,
  walk-forward (lookahead yok) çalışıyor. Gerçek CognitiveEngine council'i
  gerçek yönü belirliyor. Çıkış, services/position_closer.py::
  _exit_reason ile BİREBİR AYNI mantıkla simüle ediliyor — sabit bir
  ufuk fiyatı değil, gerçek stop/target hangisi önce gerçekleşirse.
  Faz 223a'nın maker/taker ücret ayrımı (take_profit=maker, stop_loss=
  taker) da uygulanıyor.

Risk state'i (üretimdeki gibi DB'den GERÇEK/CANLI okumak yerine) burada
kasıtlı olarak backtest'e özel, izole/gevşek değerlerle kuruluyor —
gerçek üretimin "şu an kaç pozisyon açık" gibi CANLI durumunu bir geçmiş
simülasyonuna sızdırmamak için (services/orchestrator.py::
build_cognitive_context()'i DOĞRUDAN çağırmıyoruz, ama AYNI signal_engine
fonksiyonlarını kullanıyoruz — "iki beyin" riski sinyal hesaplamasında
yok, sadece risk-context kurulumunda kasıtlı bir ayrım var)."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.risk import RiskLimitEntry
from exchange_gateway.binance.adapter import BinanceAdapter
# Faz 236: kritik bulgu — asyncio.run() zaten çalışan bir event loop
# içinden (ör. bu backtest'i tetikleyen async FastAPI endpoint'i, ya da
# celery task_always_eager modu) çağrılırsa RuntimeError fırlatır — aynı,
# önceden market_data/ingestion/data_provider.py'de bulunup düzeltilen bug.
# Aynı paylaşılan çözüm burada da kullanılıyor.
from market_data.ingestion.data_provider import _run_coroutine_sync
from market_data.features.signal_engine import (
    compute_pattern_signals,
    compute_quant_signals,
    compute_technical_signals,
)
from market_data.ingestion.ohlcv import OHLCV, from_binance_klines
from services.cognitive_engine import CognitiveEngine
from simulator.fee_engine import FeeEngine

DEFAULT_LOOKBACK = 100
DEFAULT_MAX_FORWARD_BARS = 200


async def fetch_real_history(symbol: str, timeframe: str, limit: int) -> list[OHLCV]:
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        raw = await adapter.fetch_ohlcv(symbol, timeframe, limit=limit)
    finally:
        await adapter.disconnect()
    return from_binance_klines(raw)


def _build_backtest_context(
    symbol: str, timeframe: str, window: list[OHLCV], capital_per_trade: float
) -> CognitiveCycleContext:
    """services/orchestrator.py::build_cognitive_context()'in sinyal-
    hesaplama kısmıyla (gerçek technical/quant/pattern) AYNI, ama risk
    state'i backtest'e özel — üretimin canlı DB durumunu (şu an kaç
    pozisyon açık, gerçek starting_capital vb.) bir geçmiş simülasyonuna
    karıştırmıyoruz."""
    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.market.timeframe = timeframe

    technical = compute_technical_signals(window)
    quant = compute_quant_signals(window)
    pattern = compute_pattern_signals(window)
    ctx.market.features = {**technical, **quant}
    ctx.market.raw_snapshot = {
        "close": window[-1].close,
        "volume": window[-1].volume,
        "high": window[-1].high,
        "low": window[-1].low,
        **pattern,
    }

    ctx.risk.limits = {
        "max_position_size": RiskLimitEntry(value=capital_per_trade * 10, hash=""),
        "max_drawdown": RiskLimitEntry(value=0.5, hash=""),
    }
    ctx.risk.trading_mode = "test"
    ctx.risk.ai_enabled = True
    ctx.risk.max_concurrent_positions = 1000
    ctx.risk.open_position_count = 0
    ctx.risk.capital_used_pct = 0.0
    ctx.risk.max_capital_pct = 1.0
    ctx.decision.proposed_size = capital_per_trade / window[-1].close if window[-1].close else 0.0

    return ctx


def _simulate_real_exit(
    bars: list[OHLCV],
    entry_idx: int,
    direction: str,
    stop_price: float | None,
    target_price: float | None,
    max_forward_bars: int,
) -> tuple[float | None, str | None, int | None]:
    """services/position_closer.py::_exit_reason ile BİREBİR AYNI mantık —
    backtest'te "zaman geçmesi" yerine sonraki gerçek bar'lara bakılıyor.
    max_forward_bars içinde stop/target'a hiç ulaşmazsa (None, None, None)
    döner — Faz 216 (vade dolunca kapatma yasak) ile tutarlı olarak,
    sonsuza dek açık kalmış sayılır, uydurma bir kapanış fiyatı İCAT
    EDİLMEZ, işlem sonuçlara dahil edilmez."""
    for fb in range(1, max_forward_bars + 1):
        idx = entry_idx + fb
        if idx >= len(bars):
            break
        bar = bars[idx]
        if direction == "LONG":
            if stop_price is not None and bar.low <= stop_price:
                return stop_price, "stop_loss", idx
            if target_price is not None and bar.high >= target_price:
                return target_price, "take_profit", idx
        else:
            if stop_price is not None and bar.high >= stop_price:
                return stop_price, "stop_loss", idx
            if target_price is not None and bar.low <= target_price:
                return target_price, "take_profit", idx
    return None, None, None


def run_real_backtest(
    symbol: str,
    timeframe: str = "15m",
    bars_count: int = 1000,
    lookback: int = DEFAULT_LOOKBACK,
    max_forward_bars: int = DEFAULT_MAX_FORWARD_BARS,
    capital_per_trade: float = 1000.0,
    engine: CognitiveEngine | None = None,
) -> dict:
    """Tek sembol için gerçek Binance geçmiş verisiyle walk-forward
    backtest. Dönen dict, api/rest/backtest.py'nin BacktestRun.metrics'e
    yazdığı gerçek bulgular — icat edilmiş bir sayı yok, açık pozisyonda
    (stop/target'a hiç ulaşmayan) işlemler sonuçlara dahil edilmiyor."""
    engine = engine or CognitiveEngine()
    bars = _run_coroutine_sync(fetch_real_history(symbol, timeframe, bars_count))
    fee_engine = FeeEngine()

    trades = []
    open_positions_never_closed = 0

    for t in range(lookback, len(bars) - 1):
        window = bars[max(0, t - lookback): t + 1]
        ctx = _build_backtest_context(symbol, timeframe, window, capital_per_trade)
        result_ctx = engine.run(ctx, persist=False)

        direction = result_ctx.decision.proposed_direction or "WAIT"
        size = result_ctx.decision.final_size or 0.0
        if direction not in ("LONG", "SHORT") or size <= 0:
            continue

        entry_price = bars[t].close
        risk_mag = result_ctx.decision.stop_loss
        reward_mag = result_ctx.decision.take_profit
        if not risk_mag or not reward_mag:
            continue

        if direction == "LONG":
            stop_price = entry_price - risk_mag
            target_price = entry_price + reward_mag
        else:
            stop_price = entry_price + risk_mag
            target_price = entry_price - reward_mag

        exit_price, exit_reason, exit_idx = _simulate_real_exit(
            bars, t, direction, stop_price, target_price, max_forward_bars
        )
        if exit_price is None:
            open_positions_never_closed += 1
            continue

        if direction == "LONG":
            gross_pnl_pct = (exit_price - entry_price) / entry_price
        else:
            gross_pnl_pct = (entry_price - exit_price) / entry_price

        # Faz 223a: take_profit = maker (%0.02), stop_loss = taker (%0.05).
        exit_is_maker = exit_reason == "take_profit"
        entry_fee_pct = fee_engine.config.taker_rate
        exit_fee_pct = fee_engine.config.maker_rate if exit_is_maker else fee_engine.config.taker_rate
        net_pnl_pct = gross_pnl_pct - entry_fee_pct - exit_fee_pct
        net_pnl_usd = net_pnl_pct * capital_per_trade

        trades.append({
            "symbol": symbol,
            "bar_index": t,
            "direction": direction,
            "confidence": result_ctx.decision.confidence or 0.0,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "net_return_pct": net_pnl_pct,
            "net_pnl_usd": net_pnl_usd,
            "win": net_pnl_pct > 0,
            "bars_held": exit_idx - t,
            "entry_time": bars[t].timestamp.isoformat(),
            "exit_time": bars[exit_idx].timestamp.isoformat(),
        })

    return _summarize(symbol, timeframe, bars, trades, open_positions_never_closed, capital_per_trade)


def _summarize(
    symbol: str, timeframe: str, bars: list[OHLCV], trades: list[dict],
    open_positions_never_closed: int, capital_per_trade: float,
) -> dict:
    from collections import Counter

    from analytics.metrics.engine import MetricsEngine

    if not trades:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "num_bars": len(bars),
            "trade_count": 0,
            "open_positions_never_closed": open_positions_never_closed,
            "total_pnl_usd": 0.0,
            "metrics": {},
            "equity_curve": [capital_per_trade],
        }

    wins = sum(1 for t in trades if t["win"])
    total_pnl_usd = sum(t["net_pnl_usd"] for t in trades)
    returns = [t["net_return_pct"] for t in trades]
    equity = [capital_per_trade]
    for t in trades:
        equity.append(equity[-1] + t["net_pnl_usd"])

    metrics = {
        "win_rate": wins / len(trades),
        "avg_return_pct": sum(returns) / len(returns),
        # numpy skalerleri JSON/Postgres JSON kolonuna sessizce yazılamıyor
        # (FastAPI/pydantic serileştirmesi patlıyor) — düz Python float'a
        # çeviriliyor.
        "sharpe_ratio": float(MetricsEngine.sharpe_ratio(returns)),
        "sortino_ratio": float(MetricsEngine.sortino_ratio(returns)),
        "max_drawdown": float(MetricsEngine.max_drawdown(equity)),
        "avg_bars_held": sum(t["bars_held"] for t in trades) / len(trades),
        "exit_reason_distribution": dict(Counter(t["exit_reason"] for t in trades)),
        "open_positions_never_closed": open_positions_never_closed,
    }

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "num_bars": len(bars),
        "trade_count": len(trades),
        "open_positions_never_closed": open_positions_never_closed,
        "total_pnl_usd": total_pnl_usd,
        "metrics": metrics,
        "equity_curve": equity,
        "trades": trades,
    }


def run_real_backtest_multi(
    symbols: list[str],
    timeframe: str = "15m",
    bars_count: int = 1000,
    lookback: int = DEFAULT_LOOKBACK,
    max_forward_bars: int = DEFAULT_MAX_FORWARD_BARS,
    capital_per_trade: float = 1000.0,
) -> dict:
    """Birden fazla sembol için ayrı ayrı çalıştırıp birleştirir — her
    sembolün kendi gerçek geçmiş verisi, kendi walk-forward'u var (ortak
    bir zaman ekseni ZORUNLU değil, cognitive_backtest_runner.py'nin
    aksine — o yüzden VectorizedBacktestEngine'in "tüm semboller aynı
    sayıda bar" kısıtına burada gerek yok)."""
    engine = CognitiveEngine()
    per_symbol = {}
    for symbol in symbols:
        per_symbol[symbol] = run_real_backtest(
            symbol, timeframe, bars_count, lookback, max_forward_bars, capital_per_trade, engine=engine
        )

    total_pnl_usd = sum(r["total_pnl_usd"] for r in per_symbol.values())
    total_trades = sum(r["trade_count"] for r in per_symbol.values())
    all_trades = [t for r in per_symbol.values() for t in r.get("trades", [])]
    all_wins = sum(1 for t in all_trades if t["win"])

    # Sembol bazlı equity curve'ler kendi bar indekslerine göre — ortak bir
    # zaman ekseni yok. Gerçek, birleşik bir eşitlik eğrisi için tüm
    # işlemleri GERÇEK giriş zamanına göre sıralayıp kümülatif pnl'i
    # hesaplıyoruz — kaç sembol olursa olsun tek, tutarlı bir eğri.
    all_trades_sorted = sorted(all_trades, key=lambda t: t["entry_time"])
    combined_equity = [capital_per_trade * len(symbols)]
    for t in all_trades_sorted:
        combined_equity.append(combined_equity[-1] + t["net_pnl_usd"])

    return {
        "symbols": symbols,
        "timeframe": timeframe,
        "total_trades": total_trades,
        "total_pnl_usd": total_pnl_usd,
        "overall_win_rate": (all_wins / total_trades) if total_trades else 0.0,
        "combined_equity_curve": combined_equity,
        "per_symbol": per_symbol,
    }


def persist_real_backtest_run(result: dict, session, lookback: int = DEFAULT_LOOKBACK):
    """run_real_backtest_multi()'nin çıktısını, mevcut BacktestRun
    contract'ına (Class 2, hiç silinmez) yazıyor — mock backtest'in
    kullandığı AYNI tablo/repository, sadece metrics.mode ile ayırt
    ediliyor."""
    from contracts.backtest_run import BacktestRun
    from contracts.experiment_registry import ExperimentRegistry
    from database.repositories.backtest_run_repository import BacktestRunRepository
    from simulator.fee_engine import FeeEngine

    per_symbol_pnl = {sym: r["total_pnl_usd"] for sym, r in result["per_symbol"].items()}
    per_symbol_metrics = {sym: r["metrics"] for sym, r in result["per_symbol"].items()}
    num_bars = sum(r["num_bars"] for r in result["per_symbol"].values())

    run = BacktestRun(
        symbols=result["symbols"],
        git_sha=ExperimentRegistry.get_git_sha(),
        fee=FeeEngine().config.taker_rate,
        lookback=lookback,
        num_bars=num_bars,
        total_pnl=result["total_pnl_usd"],
        per_symbol_pnl=per_symbol_pnl,
        metrics={
            "mode": "real_historical",
            "timeframe": result["timeframe"],
            "total_trades": result["total_trades"],
            "overall_win_rate": result["overall_win_rate"],
            "per_symbol": per_symbol_metrics,
        },
        equity_curve=result["combined_equity_curve"],
    )
    return BacktestRunRepository(session).save(run)
