"""Adaptive Barrier Engine — Out-of-Sample Doğrulama (Faz 268-sonrası).

analytics/adaptive_barrier_engine.py'nin kendi docstring'i açıkça
söylüyor: "Canlıya alınması ayrı, gerçek OOS doğrulama + insan onayı
gerektiren bir karar." Bu modül tam olarak o doğrulamayı yapıyor —
hiçbir SL/TP kararını burada UYGULAMIYOR, hiçbir yere WIRE edilmiyor,
sadece "bu öneri motoru, hiç görmediği veride gerçekten işe yarıyor mu"
sorusuna dürüst bir cevap üretiyor.

Metodoloji:
1. Trades (run_real_backtest_multi()'nin çıktısı, birden fazla sembol
   birleşik) entry_time'a göre kronolojik sıralanır.
2. TRAIN (ilk %train_fraction) / TEST (kalan) olarak bölünür, aralarında
   embargo_count kadar işlem ATLANIR (sınırda sızıntı olmasın diye —
   walk-forward'ın kendi lookahead-yok garantisinden BAĞIMSIZ, ayrı bir
   OOS disiplini).
3. compute_optimal_barrier() SADECE train_trades ile bariyer tablosu
   üretir (test verisi bariyer seçimine hiç karışmaz).
4. Her test trade'i için recommend_barrier() ile bir SL/TP önerisi
   aranır; bulunursa, o trade'in GERÇEK ölçülmüş mae_pct/mfe_pct/
   time_to_mae/time_to_mfe'sine _counterfactual_barrier_outcome() ile
   (path-relabeling — icat edilmiş bir fiyat yolu değil) bakılıp "bu
   öneriyle ne olurdu" hesaplanır. Bu, GERÇEKTEN o trade'de kullanılan
   (baseline) sonuçla karşılaştırılır — aynı trade'ler, iki farklı
   bariyer varsayımı.
5. Deflated Sharpe Ratio (n_trials = train'de GERÇEKTEN denenen (sl,tp)
   aday sayısı — compute_optimal_barrier'ın kendi ızgara boyutuyla
   BİREBİR aynı formül) ile "bu iyileşme sadece ızgara taramasının şans
   eseri en iyisini seçmesinden mi, yoksa gerçek mi" sorgulanır.

min_group_size/min_decisive_count altındaki her şey fail-closed
"insufficient_*" status'üyle döner — küçük örneklemden bir sonuç icat
edilmez."""
from analytics.adaptive_barrier_engine import recommend_barrier
from analytics.backtest_validation import compute_deflated_sharpe_ratio
from analytics.mae_mfe import (
    _BARRIER_QUANTILE_LEVELS,
    ENTRY_FEE_PCT,
    MIN_GROUP_SIZE,
    SL_EXIT_FEE_PCT,
    TP_EXIT_FEE_PCT,
    _counterfactual_barrier_outcome,
    compute_optimal_barrier,
)


def run_oos_validation(
    trades: list[dict],
    group_by: tuple[str, ...] = ("direction", "regime", "volatility_regime"),
    train_fraction: float = 0.7,
    embargo_count: int = 10,
    min_group_size: int = MIN_GROUP_SIZE,
    min_decisive_count: int = MIN_GROUP_SIZE,
) -> dict:
    sorted_trades = sorted(trades, key=lambda t: t["entry_time"])
    n = len(sorted_trades)
    train_end = int(n * train_fraction)
    test_start = train_end + embargo_count
    train_trades = sorted_trades[:train_end]
    test_trades = sorted_trades[test_start:]

    if len(train_trades) < min_group_size or len(test_trades) < min_group_size:
        return {
            "status": "insufficient_data",
            "train_count": len(train_trades),
            "test_count": len(test_trades),
        }

    barrier_table = compute_optimal_barrier(
        train_trades, group_by=group_by,
        min_group_size=min_group_size, min_decisive_count=min_decisive_count,
    )
    if not barrier_table:
        return {
            "status": "no_barrier_groups_cleared_threshold",
            "train_count": len(train_trades),
            "test_count": len(test_trades),
        }

    baseline_returns: list[float] = []
    adaptive_returns: list[float] = []
    for t in test_trades:
        context = {
            "direction": t.get("direction"),
            "regime": t.get("regime"),
            "volatility_regime": t.get("volatility_regime"),
            "confidence": t.get("confidence"),
        }
        rec = recommend_barrier(context, barrier_table, group_by)
        if rec is None:
            continue
        outcome = _counterfactual_barrier_outcome(t, rec["sl_pct"], rec["tp_pct"])
        if outcome == "take_profit":
            adaptive_pnl = rec["tp_pct"] - ENTRY_FEE_PCT - TP_EXIT_FEE_PCT
        elif outcome == "stop_loss":
            adaptive_pnl = -rec["sl_pct"] - ENTRY_FEE_PCT - SL_EXIT_FEE_PCT
        else:
            continue  # "neither"/"unknown" -> censored, karşılaştırma dışı
        adaptive_returns.append(adaptive_pnl)
        baseline_returns.append(t["net_return_pct"])

    matched = len(adaptive_returns)
    if matched < min_decisive_count:
        return {
            "status": "insufficient_matched_test_trades",
            "matched_test_trades": matched,
            "train_count": len(train_trades),
            "test_count": len(test_trades),
            "barrier_groups_fitted": len(barrier_table),
        }

    baseline_ev = sum(baseline_returns) / matched
    adaptive_ev = sum(adaptive_returns) / matched
    baseline_win_rate = sum(1 for r in baseline_returns if r > 0) / matched
    adaptive_win_rate = sum(1 for r in adaptive_returns if r > 0) / matched

    n_quantiles = len(_BARRIER_QUANTILE_LEVELS)
    n_trials = len(barrier_table) * n_quantiles * n_quantiles

    return {
        "status": "ok",
        "train_count": len(train_trades),
        "test_count": len(test_trades),
        "matched_test_trades": matched,
        "barrier_groups_fitted": len(barrier_table),
        "baseline_ev_pct": round(baseline_ev, 6),
        "adaptive_ev_pct": round(adaptive_ev, 6),
        "improvement_pct": round(adaptive_ev - baseline_ev, 6),
        "baseline_win_rate": round(baseline_win_rate, 4),
        "adaptive_win_rate": round(adaptive_win_rate, 4),
        "dsr_adaptive": compute_deflated_sharpe_ratio(adaptive_returns, n_trials=n_trials),
        "dsr_baseline": compute_deflated_sharpe_ratio(baseline_returns, n_trials=1),
        "n_trials_used_for_dsr": n_trials,
    }
