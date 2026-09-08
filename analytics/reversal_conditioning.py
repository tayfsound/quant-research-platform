"""Dönüş-Koşullu Yön Değeri — Faz 459 (2026-09-09).

Faz 458 şunu kesinleştirdi: yön becerimiz sistematik NEGATİF (LONG
−6,4pp, SHORT −11,9pp; 6 yoğun günün 6'sında da negatif, p=0,031). Ama
"negatif beceri" tek başına ne yapılacağını söylemiyor. İki çok farklı
dünya aynı sayıyı üretebilir:

  (a) Council gerçekten piyasa hakkında ters bir şey öğrenmiş, ya da
  (b) Council'in kendi yön çıktısı hiçbir şey taşımıyor ve gözlenen
      negatiflik tamamen GİRİŞ ZAMANLAMASI artefaktı — sistem, kripto
      için iyi belgelenmiş KISA VADELİ DÖNÜŞ (short-term reversal)
      etkisine karşı çalıştığı için kaybediyor.

Bu ikisi taban tabana zıt mimari sonuçlar doğurur: (a) ise sinyalin
işareti kurtarılabilir; (b) ise Council'i düzeltmenin anlamı yok, yerine
doğrudan bir dönüş katmanı gerekir.

AYIRT EDİCİ ÖLÇÜM: kararın hemen ÖNCESİNDEKİ getiriye göre tabakalayıp,
HER TABAKANIN İÇİNDE şunu sor — Council'in LONG mu SHORT mu dediğini
bilmek, ileri yükseliş olasılığını DEĞİŞTİRİYOR MU?

    separation(tabaka) = P(UP | tabaka, LONG) − P(UP | tabaka, SHORT)

  separation > 0  -> Council'de GERÇEK, doğru işaretli bilgi var
  separation < 0  -> bilgi var ama İŞARETİ TERS (kurtarılabilir)
  separation ~ 0  -> Council, dönüş etkisinin ötesinde HİÇBİR ŞEY
                     taşımıyor (pahalı bir gürültü üreteci)

Bu, `historical_analog_engine.py`'nin `conditioning_incremental_value`
fikrinin (Faz 427) yön hedefine uyarlanmış hâli: "bu edge'in ne kadarı
zaten bilinen bir bağlamdan geliyor?"

DÜRÜSTLÜK NOTU: tabakalama gözlenen bir değişkene göre yapıldığı için bu
NEDENSEL bir ayrıştırma değil, koşullu bir tanımlama. Council'in kendisi
önceki getiriye bakarak karar veriyorsa (ki muhtemelen bakıyor), tabaka
içi karşılaştırma yine de geçerlidir — sorduğumuz şey tam olarak "aynı
dönüş bağlamında, Council'in tercihi bir fark yaratıyor mu".

Kasıtlı olarak SADECE ölçüm — hiçbir canlı kararı etkilemiyor.
"""
MIN_SAMPLE_SIZE = 100
MIN_PER_CELL = 25
# %0,1 -- Faz 441'in %0,05'lik yön eşiğinin iki katı. Bilinçli olarak
# daha geniş: burada "fiyat hareket etti mi" değil, "anlamlı bir ön
# hareket VAR MI" sorusu var; çok dar bir eşik neredeyse her kararı
# YUKARI/AŞAĞI kovasına atıp tabakalamayı anlamsızlaştırırdı.
DEFAULT_PRIOR_THRESHOLD_PCT = 0.001


def bucket_prior_return(
    prior_return: float | None, threshold_pct: float = DEFAULT_PRIOR_THRESHOLD_PCT,
) -> str | None:
    """prior_return: kararın HEMEN ÖNCESİNDEKİ pencerede gerçekleşmiş
    getiri (ör. son 15 dakika), oran olarak. None/eksik veri -> None
    (fail-closed, uydurma tabaka üretilmez)."""
    if prior_return is None:
        return None
    if prior_return > threshold_pct:
        return "PRIOR_UP"
    if prior_return < -threshold_pct:
        return "PRIOR_DOWN"
    return "PRIOR_FLAT"


def compute_conditional_direction_value(
    records: list[dict], threshold_pct: float = DEFAULT_PRIOR_THRESHOLD_PCT,
) -> dict | None:
    """records: [{"direction": "LONG"|"SHORT", "forward_label": "UP"|"DOWN",
    "prior_return": float}, ...]

    Döndürülenler:
      reversal_effect  — önceki getirinin TEK BAŞINA ileri yükseliş
                         olasılığını ne kadar oynattığı. Council'den
                         bağımsız, saf bağlam bilgisi.
      per_bucket       — her tabakada P(UP|LONG), P(UP|SHORT) ve ikisinin
                         farkı (separation).
      pooled_separation— tabaka büyüklükleriyle ağırlıklandırılmış
                         ortalama separation: dönüş etkisi SABİT
                         TUTULDUĞUNDA Council'in kendi katkısı.
      verdict          — "signal_correct_sign" / "signal_inverted" /
                         "no_incremental_information"

    Bir tabaka, iki hücresinden biri MIN_PER_CELL altındaysa separation
    hesabına KATILMAZ (ama raporda `usable: false` ile görünür — sessizce
    atılmaz)."""
    usable = []
    for r in records:
        if r.get("direction") not in ("LONG", "SHORT"):
            continue
        if r.get("forward_label") not in ("UP", "DOWN"):
            continue
        bucket = bucket_prior_return(r.get("prior_return"), threshold_pct)
        if bucket is None:
            continue
        usable.append({**r, "bucket": bucket})

    if len(usable) < MIN_SAMPLE_SIZE:
        return None

    overall_up_rate = sum(1 for r in usable if r["forward_label"] == "UP") / len(usable)

    per_bucket: dict[str, dict] = {}
    for bucket in ("PRIOR_DOWN", "PRIOR_FLAT", "PRIOR_UP"):
        members = [r for r in usable if r["bucket"] == bucket]
        if not members:
            continue
        cells: dict[str, dict] = {}
        for direction in ("LONG", "SHORT"):
            cell = [r for r in members if r["direction"] == direction]
            cells[direction] = {
                "n": len(cell),
                "p_up": (
                    round(sum(1 for r in cell if r["forward_label"] == "UP") / len(cell), 6)
                    if cell else None
                ),
            }
        both_cells_usable = all(
            cells[d]["n"] >= MIN_PER_CELL for d in ("LONG", "SHORT")
        )
        per_bucket[bucket] = {
            "n": len(members),
            "p_up_overall": round(
                sum(1 for r in members if r["forward_label"] == "UP") / len(members), 6,
            ),
            "long": cells["LONG"],
            "short": cells["SHORT"],
            "separation": (
                round(cells["LONG"]["p_up"] - cells["SHORT"]["p_up"], 6)
                if both_cells_usable else None
            ),
            "usable": both_cells_usable,
        }

    # Dönüş etkisi: önceki getiri TEK BAŞINA ne kadar bilgi taşıyor?
    down_bucket = per_bucket.get("PRIOR_DOWN")
    up_bucket = per_bucket.get("PRIOR_UP")
    reversal_effect = None
    if down_bucket and up_bucket:
        reversal_effect = round(
            down_bucket["p_up_overall"] - up_bucket["p_up_overall"], 6,
        )

    usable_buckets = [b for b in per_bucket.values() if b["usable"]]
    pooled_separation = None
    if usable_buckets:
        total = sum(b["n"] for b in usable_buckets)
        pooled_separation = round(
            sum(b["separation"] * b["n"] for b in usable_buckets) / total, 6,
        )

    verdict = "insufficient_data"
    if pooled_separation is not None:
        # ±0,02 (2 puan) altı, bu örneklem büyüklüğünde gürültüden
        # ayırt edilemez -- "sıfır" demek için bir eşik gerekiyor,
        # keyfi olduğu açıkça belirtiliyor.
        if pooled_separation > 0.02:
            verdict = "signal_correct_sign"
        elif pooled_separation < -0.02:
            verdict = "signal_inverted"
        else:
            verdict = "no_incremental_information"

    return {
        "sample_size": len(usable),
        "overall_up_rate": round(overall_up_rate, 6),
        "reversal_effect": reversal_effect,
        "per_bucket": per_bucket,
        "pooled_separation": pooled_separation,
        "verdict": verdict,
        "prior_threshold_pct": threshold_pct,
    }
