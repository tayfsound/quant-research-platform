"""MAE/MFE ölçüm katmanı — Predictive Decision Architecture'ın ilk, somut
dilimi (davranış değişikliği yok, sadece ölçüm).

Kullanıcının önerisi: sadece entry/exit/pnl saklamak yetmez — işlem
açıldıktan kapanana kadar fiyatın yaptığı GERÇEK maksimum olumlu
(MFE — Maximum Favorable Excursion) ve olumsuz (MAE — Maximum Adverse
Excursion) hareketi ölçmeliyiz. Bu, "SL neden oluyor?" sorusunu
parçalamanın ilk adımı: SL olan ama MFE'si yüksek bir işlem ("aslında
TP'ye gidecek potansiyeli vardı, SL çok dardı") ile MAE'si zaten büyük
bir işlem ("giriş kötüydü, SL'nin suçu yok") arasındaki fark, ancak bu
ölçümle ayırt edilebilir.

Kasıtlı olarak SADECE ölçüm — hiçbir SL/TP/pozisyon büyüklüğü kararını
otomatik değiştirmiyor. Competing-risks modeli ve EV-tabanlı bariyer
optimizasyonu ayrı, sonraki adımlar (bkz. todo listesi)."""
import math
from collections import defaultdict

import numpy as np

from market_data.ingestion.ohlcv import OHLCV


def compute_mae_mfe(direction: str, entry_price: float, bars: list[OHLCV]) -> dict:
    """bars: pozisyonun GERÇEKTEN açık kaldığı süre boyunca (entry bar'ı
    dahil, exit bar'ına kadar) gerçek OHLCV geçmişi — walk-forward
    backtest'in zaten bellekte tuttuğu dilim, ekstra bir ağ isteği
    gerekmiyor.

    MAE: pozisyon ALEYHİNE en kötü anlık (unrealized) hareket — LONG için
    en düşük low, SHORT için en yüksek high, entry'ye göre yüzde.
    MFE: pozisyon LEHİNE en iyi anlık hareket — LONG için en yüksek high,
    SHORT için en düşük low.

    time_to_mae_seconds/time_to_mfe_seconds: bu ekstremum'a ulaşılan
    bar'ın entry'den ne kadar süre sonra gerçekleştiği — "kayıp hemen mi
    oldu yoksa uzun süre mi dayandı" sorusunu ayırt etmek için.

    entry_price<=0 ya da bars boşsa dürüstçe None'lar döner — icat
    edilmiş bir sayı üretilmez (fail-closed)."""
    if entry_price <= 0 or not bars:
        return {
            "mae_pct": None, "mfe_pct": None,
            "time_to_mae_seconds": None, "time_to_mfe_seconds": None,
        }

    entry_time = bars[0].timestamp
    worst_pct = 0.0
    best_pct = 0.0
    time_to_mae = 0.0
    time_to_mfe = 0.0

    for bar in bars:
        if direction == "LONG":
            adverse_pct = (bar.low - entry_price) / entry_price   # negatif = zararda
            favorable_pct = (bar.high - entry_price) / entry_price  # pozitif = kârda
        else:
            adverse_pct = (entry_price - bar.high) / entry_price
            favorable_pct = (entry_price - bar.low) / entry_price

        elapsed = (bar.timestamp - entry_time).total_seconds()

        if adverse_pct < worst_pct:
            worst_pct = adverse_pct
            time_to_mae = elapsed
        if favorable_pct > best_pct:
            best_pct = favorable_pct
            time_to_mfe = elapsed

    return {
        "mae_pct": round(worst_pct, 6),
        "mfe_pct": round(best_pct, 6),
        "time_to_mae_seconds": time_to_mae,
        "time_to_mfe_seconds": time_to_mfe,
    }


DEFAULT_QUANTILES = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
MIN_GROUP_SIZE = 20


def _confidence_bucket(confidence: float) -> str:
    """0.1'lik ayrık kovalar (0.5-0.6, 0.6-0.7, ...) — kullanıcının kendi
    örneğindeki gibi yorumlanabilir, sabit genişlikte kovalar."""
    lower = math.floor(confidence * 10) / 10
    upper = round(lower + 0.1, 1)
    return f"{lower:.1f}-{upper:.1f}"


def compute_conditional_mae_distribution(
    trades: list[dict],
    group_by: tuple[str, ...] = ("direction", "regime", "volatility_regime"),
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """Kullanıcının önerisinin ikinci adımı: "sabit SL=2xATR yerine, bu
    KOŞULLARDA (rejim/volatilite/yön/güven kovası/sembol) MAE'nin gerçek
    empirik dağılımı ne?" trades: run_real_backtest()'in döndürdüğü GERÇEK
    işlem listesi (mae_pct/mfe_pct/regime/volatility_regime dahil).
    group_by alanlarından biri "confidence" ise otomatik 0.1'lik kovalara
    bölünür, "symbol" da doğrudan kullanılabilir.

    Her grup için |MAE|'nin empirik yüzdelikleri (varsayılan: kullanıcının
    kendi örneğindeki 50/60/70/80/90/95) + MFE medyanı + örneklem
    büyüklüğü + kazanma oranı dönüyor — "SL = Q_alpha(MAE|X)" için
    doğrudan kullanılabilir referans değerler. min_group_size altında
    kalan gruplar hiç dönmüyor (fail-closed, istatistiksel olarak anlamsız
    bir yüzdelik asla raporlanmaz).

    Kasıtlı olarak SADECE rapor — hiçbir SL kararını burada UYGULAMIYOR;
    gerçek bariyer optimizasyonu (EV-tabanlı SL/TP seçimi) ayrı, sonraki
    bir adım (bkz. modül docstring'i)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)

    for t in trades:
        if t.get("mae_pct") is None:
            continue
        key_parts = []
        for field in group_by:
            if field == "confidence":
                key_parts.append(_confidence_bucket(t.get("confidence") or 0.0))
            else:
                key_parts.append(str(t.get(field, "unknown")))
        groups[tuple(key_parts)].append(t)

    results: dict[str, dict] = {}
    for key, group_trades in groups.items():
        if len(group_trades) < min_group_size:
            continue
        mae_abs = np.array([abs(t["mae_pct"]) for t in group_trades])
        mfe_vals = np.array([t["mfe_pct"] for t in group_trades])
        label = "|".join(f"{field}={value}" for field, value in zip(group_by, key))
        results[label] = {
            "sample_size": len(group_trades),
            "mae_quantiles": {
                f"p{int(q * 100)}": round(float(np.quantile(mae_abs, q)), 6) for q in quantiles
            },
            "mfe_median": round(float(np.median(mfe_vals)), 6),
            "win_rate": round(sum(1 for t in group_trades if t["win"]) / len(group_trades), 4),
        }
    return results


# Faz 268-sonrası: kullanıcının canlı gözlemi — son 24 saatte 8 işlemin
# 5'i "breakeven_stop" (kâra geçip stop girişe çekildikten sonra tersine
# dönüp başabaşa yakın kapanmış), 3'ü gerçek stop_loss. Bu, klasik ikili
# "TP mi SL mi önce vurulur" yarışının EKSİK bir modeli olduğunu gösterdi:
# breakeven_stop de yarışın GERÇEKTEN sonuçlandığı üçüncü bir durum — "kâra
# geçti ama TP'ye ulaşamadan geri döndü." take_profit/stop_loss/
# breakeven_stop üçü de KARARLI (decisive) sonuç; manual_full/time_expired/
# liquidation gibi diğerleri CENSORED (yarış sonuçlanmadan kapandı, hangi
# bariyerin önce vurulacağı bilinmiyor, icat edilmiyor).
#
# ÖNEMLİ SINIRLAMA: real_historical_backtest.py'nin _simulate_real_exit'i
# ŞU AN breakeven-stop mekanizmasını simüle ETMİYOR (sadece stop_loss/
# take_profit) — yani bu fonksiyon backtest trade'leriyle çağrılırsa
# breakeven_stop hiç görünmez, SADECE gerçek (live) decisions.outcome
# verisiyle çağrıldığında anlamlı. Backtest'e bu mekanizmayı eklemek ayrı
# bir iş (henüz yapılmadı).
DECISIVE_EXIT_REASONS = ("take_profit", "stop_loss", "breakeven_stop")


def compute_competing_risk_probabilities(
    trades: list[dict],
    group_by: tuple[str, ...] = ("direction", "regime", "volatility_regime"),
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """Her koşul kovası için take_profit/stop_loss/breakeven_stop'un
    GERÇEKTEN hangi sıklıkla gerçekleştiğini (competing risks) hesaplar.
    trades'in exit_reason alanı olmalı (decisions.outcome->>'exit_reason'
    ile aynı sözlük). min_group_size altındaki kovalar fail-closed
    dışlanır. Sadece kararlı sonuçlar sayılır — censored (manual/
    time_expired/liquidation/vb.) trade'ler p hesabına DAHİL edilmez ama
    şeffaflık için censored_count olarak ayrıca raporlanır."""
    decisive_groups: dict[tuple, list[dict]] = defaultdict(list)
    censored_counts: dict[tuple, int] = defaultdict(int)

    for t in trades:
        key_parts = []
        for field in group_by:
            if field == "confidence":
                key_parts.append(_confidence_bucket(t.get("confidence") or 0.0))
            else:
                key_parts.append(str(t.get(field, "unknown")))
        key = tuple(key_parts)

        if t.get("exit_reason") in DECISIVE_EXIT_REASONS:
            decisive_groups[key].append(t)
        else:
            censored_counts[key] += 1

    results: dict[str, dict] = {}
    for key in set(decisive_groups) | set(censored_counts):
        decisive = decisive_groups.get(key, [])
        if len(decisive) < min_group_size:
            continue
        n = len(decisive)
        tp_count = sum(1 for t in decisive if t["exit_reason"] == "take_profit")
        sl_count = sum(1 for t in decisive if t["exit_reason"] == "stop_loss")
        breakeven_count = sum(1 for t in decisive if t["exit_reason"] == "breakeven_stop")
        label = "|".join(f"{field}={value}" for field, value in zip(group_by, key))
        results[label] = {
            "decisive_sample_size": n,
            "censored_count": censored_counts.get(key, 0),
            "tp_count": tp_count,
            "sl_count": sl_count,
            "breakeven_stop_count": breakeven_count,
            "p_take_profit": round(tp_count / n, 4),
            "p_stop_loss": round(sl_count / n, 4),
            "p_breakeven_stop": round(breakeven_count / n, 4),
        }
    return results
