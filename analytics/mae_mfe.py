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
#
# Faz 359 — "breakeven_stop" etiketi kullanıcı isteğiyle "reduced_loss_
# stop" olarak yeniden adlandırıldı (bkz. services/position_closer.py) —
# eski etiket yanıltıcıydı (gerçek $0 değil, azaltılmış-ama-hâlâ-zarar
# anlamına geliyordu). Kavramsal olarak AYNI kategori — burada ikisi de
# kararlı sayılıyor (eski satırlar hâlâ "breakeven_stop" taşıyor, geriye
# dönük değiştirilmedi).
DECISIVE_EXIT_REASONS = ("take_profit", "stop_loss", "breakeven_stop", "reduced_loss_stop")


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
        breakeven_count = sum(1 for t in decisive if t["exit_reason"] in ("breakeven_stop", "reduced_loss_stop"))
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


# Faz 268-sonrası: EV-tabanlı SL/TP ortak optimizasyonu — "Optimal Barrier
# Surface." simulator/fee_engine.py'deki GERÇEK maker/taker oranları
# (icat edilmiş değil).
ENTRY_FEE_PCT = 0.0005   # taker (giriş her zaman taker — market emri)
TP_EXIT_FEE_PCT = 0.0002  # maker
SL_EXIT_FEE_PCT = 0.0005  # taker
_BARRIER_QUANTILE_LEVELS = (0.5, 0.6, 0.7, 0.8, 0.9)


def _counterfactual_barrier_outcome(trade: dict, sl_pct: float, tp_pct: float) -> str:
    """Bu trade'in GERÇEKTEN ölçülmüş mae_pct/mfe_pct'sine (ve hangi
    ekstremuma ÖNCE ulaşıldığına — time_to_mae/time_to_mfe) bakarak, aday
    bir (sl_pct, tp_pct) çiftiyle hangi bariyerin önce vurulacağını yeniden
    türetir. Bu, finansal ML literatüründeki 'path relabeling/meta-
    labeling' tekniği — icat edilmiş bir fiyat yolu değil, zaten ölçülmüş
    gerçek ekstremum DEĞER ve ZAMANLARI kullanılıyor. mae_pct/mfe_pct
    None ise 'unknown' (fail-closed, sayılmaz)."""
    mae = trade.get("mae_pct")
    mfe = trade.get("mfe_pct")
    if mae is None or mfe is None:
        return "unknown"
    hit_sl = abs(mae) >= sl_pct
    hit_tp = mfe >= tp_pct
    if hit_sl and hit_tp:
        t_mae = trade.get("time_to_mae_seconds") or 0.0
        t_mfe = trade.get("time_to_mfe_seconds") or 0.0
        return "stop_loss" if t_mae <= t_mfe else "take_profit"
    if hit_sl:
        return "stop_loss"
    if hit_tp:
        return "take_profit"
    return "neither"


def compute_optimal_barrier(
    trades: list[dict],
    group_by: tuple[str, ...] = ("direction", "regime", "volatility_regime"),
    quantile_levels: tuple[float, ...] = _BARRIER_QUANTILE_LEVELS,
    min_group_size: int = MIN_GROUP_SIZE,
    min_decisive_count: int = MIN_GROUP_SIZE,
) -> dict:
    """Her koşul kovası için, o kovanın GERÇEK MAE/MFE dağılımından türetilen
    aday SL/TP mesafeleri (empirik yüzdelikler — quantile_levels) üzerinde
    ızgara taraması yapıp, gerçek trade'lerin path-relabeling ile yeniden
    türetilmiş sonuçlarına göre en yüksek beklenen değeri (EV, fee dahil)
    veren çifti döndürür.

    'neither' (ne SL ne TP'ye ulaşılan) trade'ler EV hesabına DAHİL
    edilmiyor (censored, fail-closed) — ama decisive_fraction ile şeffaf
    raporlanıyor. Bir (sl,tp) çifti için karar sayısı min_decisive_count
    altındaysa o çift değerlendirilmiyor (küçük örneklemden EV icat
    edilmiyor). Hiçbir aday çift bu eşiği geçemezse kova sonuç
    döndürmüyor.

    Kasıtlı olarak SADECE öneri/rapor — hiçbir SL/TP kararını burada
    UYGULAMIYOR, gerçek pozisyonlara otomatik yansımıyor."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for t in trades:
        if t.get("mae_pct") is None or t.get("mfe_pct") is None:
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
        sl_candidates = sorted({round(float(np.quantile(mae_abs, q)), 6) for q in quantile_levels})
        tp_candidates = sorted({round(float(np.quantile(mfe_vals, q)), 6) for q in quantile_levels})

        best = None
        for sl_pct in sl_candidates:
            if sl_pct <= 0:
                continue
            for tp_pct in tp_candidates:
                if tp_pct <= 0:
                    continue
                pnls = []
                for t in group_trades:
                    outcome = _counterfactual_barrier_outcome(t, sl_pct, tp_pct)
                    if outcome == "take_profit":
                        pnls.append(tp_pct - ENTRY_FEE_PCT - TP_EXIT_FEE_PCT)
                    elif outcome == "stop_loss":
                        pnls.append(-sl_pct - ENTRY_FEE_PCT - SL_EXIT_FEE_PCT)
                    # "neither"/"unknown" -> censored, EV hesabına girmiyor.
                if len(pnls) < min_decisive_count:
                    continue
                ev = sum(pnls) / len(pnls)
                if best is None or ev > best["expected_value_pct"]:
                    best = {
                        "sl_pct": sl_pct,
                        "tp_pct": tp_pct,
                        "expected_value_pct": round(ev, 6),
                        "decisive_sample_size": len(pnls),
                        "decisive_fraction": round(len(pnls) / len(group_trades), 4),
                    }

        # Kullanıcı bulgusu (2026-08-28): gerçek canlı örnek — SHORT|
        # bear_trend kovalarının İKİSİNDE de en iyi bulunan (sl,tp) çifti
        # bile NEGATİF EV'liydi (-%9.7/-%8.1), ama önceden buraya kadar
        # gelen HER şey (örneklem eşiğini geçen her şey) döndürülüyordu —
        # ızgara taramasının bulabildiği "en az kötü" tp_pct neredeyse
        # sıfıra (ör. %0.04) yakın çıkınca, RiskTargetStage'in EV kapısı
        # (services/decision_fusion.py) bu kovaya düşen HER kararı
        # (confidence ne olursa olsun, %90+ dahil) yapısal olarak
        # reddediyordu — SHORT, piyasa gerçekten düşüşe geçtiğinde bile
        # fiilen tamamen kilitlenmiş oluyordu. Artık bu fonksiyon da
        # (örneklem eşiği kontrolüyle AYNI fail-closed ilke) negatif EV'li
        # bir kova için hiç sonuç döndürmüyor — çağıran (RiskTargetStage)
        # None alıp zaten var olan, her zaman geçilebilir statik ATR
        # oranına (2.5/1.4) düşüyor.
        if best is not None and best["expected_value_pct"] > 0:
            label = "|".join(f"{field}={value}" for field, value in zip(group_by, key))
            best["total_sample_size"] = len(group_trades)
            results[label] = best
    return results


# Faz 268-sonrası: confidence'ı ikiye ayırma. Tek bir "confidence" sayısı
# İKİ farklı gerçek olasılığı karıştırıyor: (1) yön doğru muydu — fiyat
# en azından bir an lehte anlamlı hareket etti mi (direction_probability),
# (2) yön doğruysa GERÇEKTEN TP'ye mi ulaştı yoksa (breakeven_stop/
# stop_loss ile) mi kayboldu (barrier_probability). Kullanıcının canlı
# breakeven_stop gözlemi tam olarak bunun bir örneği: yön doğruydu (mfe_pct
# pozitifti) ama bariyer (TP mesafesi) kötü kalibreliydi. Confidence
# yüksek + barrier_probability düşük bir kova = "AI yönü doğru biliyor
# ama SL/TP mesafeleri kötü kalibre" — actionable, farklı bir sorun.
DIRECTION_CORRECT_MFE_THRESHOLD = 0.001  # entry+exit fee toplamından küçük — altı gürültü.


def compute_confidence_decomposition(
    trades: list[dict],
    group_by: tuple[str, ...] = ("direction", "regime", "volatility_regime"),
    direction_threshold: float = DIRECTION_CORRECT_MFE_THRESHOLD,
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """P(win) ≈ direction_probability × barrier_probability şeklinde
    ayrıştırır. Sadece kararlı (take_profit/stop_loss/breakeven_stop)
    trade'ler sayılır — yarışın sonuçlanmadığı trade'ler dahil edilmez.
    Bir kovada hiç 'yön doğru' (mfe_pct > threshold) trade yoksa
    barrier_probability None döner (fail-closed — sıfır örneklemden
    oran icat edilmez)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for t in trades:
        if t.get("mfe_pct") is None or t.get("exit_reason") not in DECISIVE_EXIT_REASONS:
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
        n = len(group_trades)
        if n < min_group_size:
            continue

        direction_correct = [t for t in group_trades if t["mfe_pct"] > direction_threshold]
        direction_probability = len(direction_correct) / n

        if direction_correct:
            tp_given_correct = sum(1 for t in direction_correct if t["exit_reason"] == "take_profit")
            barrier_probability = round(tp_given_correct / len(direction_correct), 4)
        else:
            barrier_probability = None

        avg_confidence = sum(t.get("confidence") or 0.0 for t in group_trades) / n
        label = "|".join(f"{field}={value}" for field, value in zip(group_by, key))
        results[label] = {
            "sample_size": n,
            "avg_reported_confidence": round(avg_confidence, 4),
            "direction_probability": round(direction_probability, 4),
            "direction_correct_sample_size": len(direction_correct),
            "barrier_probability": barrier_probability,
        }
    return results


def _group_trades(trades: list[dict], group_by: tuple[str, ...]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for t in trades:
        key_parts = []
        for field in group_by:
            if field == "confidence":
                key_parts.append(_confidence_bucket(t.get("confidence") or 0.0))
            else:
                key_parts.append(str(t.get(field, "unknown")))
        groups[tuple(key_parts)].append(t)
    return groups


def compute_selection_bias_correction(
    taken_trades: list[dict],
    rejected_trades: list[dict],
    group_by: tuple[str, ...] = ("direction", "regime", "volatility_regime"),
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """AI'nin GERÇEKTEN aldığı işlemlerin MAE/MFE'sini, ALMADIĞI ama yönlü
    bir çağrı yaptığı (decisions.status='no_trade', direction IN
    (LONG, SHORT)) fırsatların HİPOTETİK MAE/MFE'siyle karşılaştırır —
    execution filtresinin (act_threshold, risk kapıları) gerçekten kötü
    fırsatları eleyip elemediğini ölçmek için. taken_trades AVANTAJLI
    olmalı (daha yüksek MFE, daha düşük |MAE|) — aksi halde seçim gerçek
    bir değer katmıyor, gürültüyü eliyor gibi görünüp aslında rastgele
    davranıyor olabilir.

    ÖNEMLİ SINIRLAMA: bu fonksiyon SADECE karşılaştırmayı yapar.
    rejected_trades'in mae_pct/mfe_pct'sini doldurmak ayrı, henüz
    yapılmamış bir backfill işi — no_trade kararlarının entry_price'ı
    kayıtlı değil (622 LONG + 437 SHORT gerçek yönlü-ama-reddedilmiş karar
    var, DB'de doğrulandı), sembol+timestamp'ten GERÇEK geçmiş bar
    verisiyle yeniden inşa edilmesi gerekiyor."""
    taken_groups = _group_trades(
        [t for t in taken_trades if t.get("mae_pct") is not None], group_by,
    )
    rejected_groups = _group_trades(
        [t for t in rejected_trades if t.get("mae_pct") is not None], group_by,
    )

    results: dict[str, dict] = {}
    for key in set(taken_groups) | set(rejected_groups):
        taken = taken_groups.get(key, [])
        rejected = rejected_groups.get(key, [])
        if len(taken) < min_group_size or len(rejected) < min_group_size:
            continue

        taken_mfe = float(np.median([t["mfe_pct"] for t in taken]))
        rejected_mfe = float(np.median([t["mfe_pct"] for t in rejected]))
        taken_mae = float(np.median([abs(t["mae_pct"]) for t in taken]))
        rejected_mae = float(np.median([abs(t["mae_pct"]) for t in rejected]))

        label = "|".join(f"{field}={value}" for field, value in zip(group_by, key))
        results[label] = {
            "taken_sample_size": len(taken),
            "rejected_sample_size": len(rejected),
            "taken_mfe_median": round(taken_mfe, 6),
            "rejected_mfe_median": round(rejected_mfe, 6),
            "taken_mae_median": round(taken_mae, 6),
            "rejected_mae_median": round(rejected_mae, 6),
            "selection_adds_value": bool(taken_mfe > rejected_mfe and taken_mae < rejected_mae),
        }
    return results
