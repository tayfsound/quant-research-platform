"""Faz 362 — sinyal tutarlılığı (signal persistence) kapısı, saf hesaplama
katmanı.

Kullanıcı bulgusu (2026-08-24): "council'in ara sıra bir cycle'da tersine
dönmesi çoğunlukla gerçek bir trend değişimi değil, gürültü — bu gürültüye
güvenerek yeni pozisyonlara da giriyor olabiliriz." Gerçek 3619 kapanmış
pozisyonla (10-24 Ağustos, mekanik stratejiler hariç) ölçüldü: bir sembolde
girişten HEMEN ÖNCE, o sembol/yönde kaç ardışık cycle'dır AYNI yönde sinyal
vardı (0 = "taze dönüş", tam o an flip etmiş) diye kırılınca:

  run=0: n=1495  win_rate=%48.3  ort.pnl=-$4.96   (TEK BAŞINA zararlı)
  run=1: n=373   win_rate=%54.2  ort.pnl=-$7.10   (hâlâ zararlı)
  run=2: n=235   win_rate=%63.0  ort.pnl=-$13.27  (hâlâ zararlı)
  run=3: n=187   win_rate=%66.8  ort.pnl=-$11.89  (hâlâ zararlı)
  run=4: n=140   win_rate=%66.4  ort.pnl=+$5.03   (İLK net pozitif)
  run=5+: genelde pozitif

Sadece işlem-başı ortalamaya bakmak yanlış eşiği seçtirir (yüksek N'de
küçük örneklemler yapay olarak yüksek ortalama gösterir) — doğru amaç
fonksiyonu TOPLAM kâr: mean_pnl(>=N) × count(>=N). Bu eğri N=4'te tepe
yapıyor ($116,335), N=5-7 istatistiksel ayırt edilemez şekilde platoluyor,
sonrasında hacim kaybı kalite kazancını geçtiği için sürekli düşüyor.
find_optimal_persistence_threshold() bu optimizasyonu ANLIK veriyle
tekrar üretebilsin diye buraya taşındı — eşik ileride yeniden ölçülmek
istendiğinde (daha büyük örneklem, farklı rejim) sıfırdan script yazmaya
gerek kalmasın."""


def consistent_direction_run_length(prior_decisions_desc: list[dict], direction: str) -> int:
    """prior_decisions_desc: bu sembol için, en yeniden en eskiye sıralı,
    her biri 'direction' alanı içeren ÖNCEKİ kararlar (mevcut/aday kararı
    İÇERMEZ — henüz persist edilmeden önce okunur). En son karardan geriye
    doğru, `direction` ile EŞLEŞMEYEN ilk karara kadar ardışık sayıyı
    döner. Boş listede/ilk kayıt eşleşmiyorsa 0 — icat edilmiş bir run
    asla üretilmez (consecutive_stop_streak, analytics/regime_reversal.py,
    ile AYNI desen)."""
    run = 0
    for d in prior_decisions_desc:
        if d.get("direction") == direction:
            run += 1
        else:
            break
    return run


def is_fresh_signal_blocked(consistent_run_length: int, min_required_cycles: int) -> bool:
    """True dönerse bu giriş, sinyal henüz yeterince tutarlı/sürdürülmüş
    olmadığı için (taze dönüş, gürültü olma ihtimali yüksek) engellenmeli."""
    return consistent_run_length < min_required_cycles


def find_optimal_persistence_threshold(
    run_length_and_pnl: list[tuple[int, float]], max_n: int = 20
) -> dict:
    """Her kapanmış pozisyon için (girişten önceki tutarlı-cycle sayısı,
    gerçekleşen pnl) çiftlerinden, TOPLAM kârı (mean_pnl(>=N) × count(>=N)
    — hacim/kalite dengesini doğru yakalayan tek metrik) maksimize eden N
    eşiğini bulur. Yeterli veri yoksa (fail-closed) None döner — çağıran
    taraf mevcut/varsayılan eşiği korumalı, gürültüden yeni bir eşik asla
    üretilmemeli."""
    if not run_length_and_pnl:
        return {"optimal_n": None, "table": []}

    table = []
    best_n = None
    best_total = None
    for n in range(0, max_n + 1):
        cum = [pnl for run, pnl in run_length_and_pnl if run >= n]
        if not cum:
            break
        total = sum(cum)
        count = len(cum)
        mean = total / count
        win_rate = sum(1 for pnl in cum if pnl > 0) / count
        table.append({
            "n": n, "count": count, "total_pnl": round(total, 2),
            "mean_pnl": round(mean, 2), "win_rate": round(win_rate, 4),
        })
        if best_total is None or total > best_total:
            best_total = total
            best_n = n

    return {"optimal_n": best_n, "table": table}


# ---------------------------------------------------------------------------
# Faz 362-devam — AYNI sinyal-kalitesi sorusunun ÇIKIŞ tarafı: "elimde açık
# bir pozisyon varken council art arda güçlü şekilde tersine dönerse, bu
# gerçek mi gürültü mü?" İlk (dar, 4 günlük, n<=27) ölçüm "her zaman
# gürültü, asla tetikleme" sonucunu vermişti — kullanıcı haklı çıkarak bunu
# sorguladı, geniş pencerede (10-24 Ağustos, 3619 pozisyon) TAMAMEN FARKLI
# bir tablo ortaya çıktı:
#
#   N=1: n=1473  better=530  worse=528  toplam fark=-$56,787 (uç değerli, güvenilmez)
#   N=4: n=410   better=220  worse=144  toplam fark=-$8,046  (hâlâ negatif)
#   N=5: n=327   better=180  worse=117  toplam fark=+$138    (İLK pozitif)
#   N=6: n=187   better=147  worse=18   toplam fark=+$480    (uç değerler kayboluyor -- en kötü -$2.5)
#   N=8: n=126   better=106  worse=9    toplam fark=+$453
#
# N=6'da felaket boyutlu "tutmak çok daha iyiydi" uç değerleri (N<=4'te
# -$800'e varan) tamamen kayboluyor — TEK cycle'lık dönüşler gürültü, ama
# 6+ ardışık cycle boyunca SÜRDÜRÜLEN bir tersine dönüş gerçek bir sinyal.
# ---------------------------------------------------------------------------


def consecutive_reversal_run_length(
    prior_decisions_desc: list[dict], position_direction: str, min_confidence: float
) -> int:
    """prior_decisions_desc: bu sembol için, en yeniden en eskiye sıralı,
    her biri 'direction'/'confidence' alanı içeren ÖNCEKİ kararlar. En son
    karardan geriye doğru, position_direction'ın TERSİNE VE min_confidence
    üzerinde olan ilk karara kadar ardışık sayıyı döner (consistent_
    direction_run_length ile AYNI desen — sadece "aynı yön" değil "ters
    yön + yeterli güven" eşleşmesi arıyor)."""
    opposite = "SHORT" if position_direction == "LONG" else "LONG"
    run = 0
    for d in prior_decisions_desc:
        if d.get("direction") == opposite and (d.get("confidence") or 0) >= min_confidence:
            run += 1
        else:
            break
    return run


def is_belief_reversal_exit_triggered(consistent_reversal_run_length: int, min_required_cycles: int) -> bool:
    """True dönerse council, bu pozisyonun yönüne art arda yeterince
    güçlü/sürdürülmüş şekilde ters düşüyor demektir — defansif çıkış
    tetiklenmeli."""
    return consistent_reversal_run_length >= min_required_cycles


def find_optimal_reversal_exit_threshold(
    diffs_by_n: dict[int, list[float]],
) -> dict:
    """diffs_by_n: {N: [pnl_erken_cikilsaydi - gercek_pnl, ...]} — her N
    için, o N'de İLK kez tetiklenen pozisyonların "erken çıksaydık ne
    olurdu" farkı. TOPLAM faydayı (sum of diffs) maksimize eden N'i bulur.
    Yeterli veri yoksa (fail-closed) None döner."""
    if not diffs_by_n:
        return {"optimal_n": None, "table": []}

    table = []
    best_n = None
    best_total = None
    for n in sorted(diffs_by_n):
        diffs = diffs_by_n[n]
        if not diffs:
            continue
        total = sum(diffs)
        count = len(diffs)
        better = sum(1 for d in diffs if d > 0.01)
        worse = sum(1 for d in diffs if d < -0.01)
        table.append({
            "n": n, "count": count, "total_benefit": round(total, 2),
            "mean_benefit": round(total / count, 2), "better": better, "worse": worse,
        })
        if best_total is None or total > best_total:
            best_total = total
            best_n = n

    return {"optimal_n": best_n, "table": table}
