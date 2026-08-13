"""Stress Testing ve Robustness — Faz 694-718 (Cognitive Core 2.0 / M8).

risk/predictive/monte_carlo.py SENTETİK (simüle edilmiş) senaryolar
üretiyor; backtest/red_team.py de sentetik whipsaw/flash-crash senaryoları
kullanıyor. Bu modül GERÇEK geçmiş fiyat hareketlerini kullanan standart
bir stres testi tekniği ekliyor: Historical Simulation — bir varlığın
KENDİ gerçek geçmişindeki EN KÖTÜ N-dönemlik getiri dizisini bulup mevcut
pozisyon notional'ına uygulayarak gerçek bir "bu tam olarak yeniden
yaşansaydı ne olurdu" senaryosu üretiyor. İcat edilmiş bir kriz senaryosu
değil — piyasanın KENDİ gerçek tarihinden.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir pozisyon/risk kararını burada
otomatik değiştirmiyor."""

MIN_WINDOWS = 2


def compute_worst_historical_drawdown(returns: list[float], window: int) -> dict | None:
    """returns: GERÇEK, kronolojik sıralı dönemsel getiri serisi.
    window: stres testi penceresi (kaç dönem ardışık bileşik getiri
    hesaplanacak). Seride en az MIN_WINDOWS farklı `window`-uzunluklu
    pencere olmalı (yani len(returns) >= window + MIN_WINDOWS - 1);
    aksi halde tek bir pencereden "en kötü" seçmek anlamsız olur —
    fail-closed None döner."""
    n = len(returns)
    if window < 1 or n < window + MIN_WINDOWS - 1:
        return None

    worst_return = None
    worst_start_idx = None
    for start in range(0, n - window + 1):
        window_returns = returns[start:start + window]
        compounded = 1.0
        for r in window_returns:
            compounded *= (1.0 + r)
        cumulative_return = compounded - 1.0
        if worst_return is None or cumulative_return < worst_return:
            worst_return = cumulative_return
            worst_start_idx = start

    return {
        "worst_cumulative_return_pct": round(worst_return, 6),
        "window": window,
        "worst_window_start_index": worst_start_idx,
        "sample_size": n,
    }


def apply_stress_scenario_to_notional(worst_cumulative_return_pct: float, notional: float) -> dict:
    """Bir stres senaryosunun (compute_worst_historical_drawdown'ın
    ürettiği) GERÇEK dolar/birim etkisini mevcut notional'a uygular —
    ekstra bir varsayım eklemeden, doğrudan çarpım."""
    dollar_impact = worst_cumulative_return_pct * notional
    return {
        "notional": round(notional, 2),
        "worst_cumulative_return_pct": round(worst_cumulative_return_pct, 6),
        "dollar_impact": round(dollar_impact, 2),
    }
