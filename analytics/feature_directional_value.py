"""Bağlam Özelliklerinin Yön Değeri — Faz 462 (2026-09-09).

Faz 460 ajanların OY'larını (`agent_contributions[].feature_contributions`)
ölçtü. Ama `ctx.market.features` sözlüğünde, hiçbir ajanın oyuna
girmeden, SADECE GÖZLEM olarak akan 40'tan fazla ham özellik daha var
(RSI, adx, atr, hurst_exponent, autocorrelation, zscore,
vwap_deviation_pct, bollinger_percent_b, atr_expansion_ratio, rsi_slope,
rsi_divergence, confluence_zones, onchain_*, order_flow_relationship_*,
liquidation_pressure_*, taker_flow_pressure_*...). Bunların bir kısmı
Faz 411/423/436/437/438/439/461'de "önce gözlemle, kanıtlanırsa wire et"
diye eklendi — ama gözlem verisi biriktiği hâlde HİÇ ÖLÇÜLMEDİ. Bu modül
o boşluğu kapatıyor.

TETİKLEYİCİ BULGU: Faz 436'nın `order_flow_relationship_category`'si elle
ölçüldüğünde (7 gün) şu çıktı —

    bullish_short_covering     P(UP)=0,373  (n=150)
    bullish_new_longs          P(UP)=0,398  (n=342)
    bearish_new_shorts         P(UP)=0,457  (n=94)
    bearish_long_capitulation  P(UP)=0,533  (n=315)

"bullish" kategorileri ile "bearish" arasında **16 puanlık ayrım** —
sistemde ölçtüğümüz en güçlü kategorik sinyal, ve Faz 460'ın genel
örüntüsüne uygun şekilde TERS işaretli ("yeni long'lar yığılıyor" ->
fiyat düşüyor; "long kapitülasyonu" -> fiyat yükseliyor). Bir yıl önce
kurulup hiç bağlanmamış, hiç ölçülmemiş bir sinyal.

Modül tipi KENDİ tespit ediyor:
  sayısal   -> çeyreklik ayrımı (üst %25 vs alt %25) + uç dilim (%10)
               kontrolüyle MONOTONLUK testi. Uçta güçlenmeyen bir ayrım
               büyük ihtimalle gürültüdür (Faz 461'de taker akışında
               kullanılan AYNI ölçüt).
  kategorik -> kategori başına P(UP) + yeterli örnekli kategoriler
               arasındaki en yüksek/en düşük farkı.

REJİM KIRILIMI (Faz 471, kullanıcı isteği: "Ölçtüğümüz her şeyi rejime
göre değerlendirmemiz lazım; hangi rejimde hangi verinin anlamlı
olduğunu anlayamayız yoksa."): bir özellik `bullish_normal`'da doğru
işaretliyken `bearish_low`'da ters olabilir ve havuzlanmış tek bir sayı
bunu ortalayıp yok eder. `by_regime` kırılımı bunu açıyor.

Kasıtlı olarak SADECE ölçüm — hiçbir canlı kararı etkilemiyor.
"""
import statistics

MIN_PER_SIDE = 200
MIN_PER_CATEGORY = 80
NEUTRAL_BAND = 0.02
MIN_PER_SIDE_DAILY = 60
# Bir ozelligin "kanitlanmis" sayilmasi icin gunlerin en az bu kadarinda
# AYNI yonde olmasi gerekiyor. Faz 462'de kullanici dogruladi: onchain
# ozellikleri (hash_rate_trend, network_activity_trend, solana_tps...)
# belirli bir anda TUM sembollerde ayni degeri aliyor, dolayisiyla
# olculen "ayrim"lari sembol-bazli bir edge degil, zaman ici piyasa
# dalgalanmasi olabilir. Gunluk tutarlilik, bu tur sahte ayrimlari
# eleyen tek ucuz filtre (Faz 458'in gunluk isaret testiyle AYNI ilke).
MIN_CONSISTENT_DAY_RATIO = 0.8
# Rejim kırılımı zorunlu olarak daha ince.
MIN_PER_SIDE_REGIME = 60
# Sembol-ici karsilastirma icin bir zaman kovasinda en az bu kadar
# gozlem olmali (aksi halde "yuksek/dusuk" bolmesi anlamsiz).
MIN_PER_TIME_BUCKET = 6


def _p_up(members: list[dict]) -> float:
    return sum(1 for r in members if r["forward_label"] == "UP") / len(members)


def _is_numeric(value) -> bool:
    # bool, Python'da int'in alt sinifi -- ama "True/False" kategorik bir
    # bayraktir, sayisal bir olcek degil.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric_separation(members: list[dict], upper_pct: float, lower_pct: float):
    values = sorted(r["value"] for r in members)
    if len(values) < 4:
        return None, 0, 0
    upper = values[min(len(values) - 1, int(len(values) * upper_pct))]
    lower = values[max(0, int(len(values) * lower_pct))]
    if upper <= lower:
        # Dagilim cok yigin (or. ozellik neredeyse sabit) -- ayrim
        # tanimsiz, uydurma bir sayi uretilmez.
        return None, 0, 0
    high = [r for r in members if r["value"] >= upper]
    low = [r for r in members if r["value"] <= lower]
    if not high or not low:
        return None, len(high), len(low)
    return _p_up(high) - _p_up(low), len(high), len(low)


def _daily_consistency(members: list[dict], evaluator) -> dict | None:
    """Ozelligin gunluk ayrimlarini hesaplar. `evaluator`, bir gunun
    kayitlarini alip ayrim (float | None) donduren fonksiyon."""
    by_day: dict[str, list[dict]] = {}
    for r in members:
        if r.get("day") is not None:
            by_day.setdefault(str(r["day"]), []).append(r)
    separations = []
    for day_members in by_day.values():
        day_sep = evaluator(day_members)
        if day_sep is not None:
            separations.append(day_sep)
    if len(separations) < 3:
        return None
    negative = sum(1 for x in separations if x < 0)
    positive = sum(1 for x in separations if x > 0)
    dominant = max(negative, positive)
    return {
        "days": len(separations),
        "negative_days": negative,
        "positive_days": positive,
        "consistency_ratio": round(dominant / len(separations), 4),
        "consistent": bool(dominant / len(separations) >= MIN_CONSISTENT_DAY_RATIO),
    }


def _within_bucket_categorical(members: list[dict], best: str, worst: str) -> dict | None:
    """Kategorik ozelliklerin SEMBOL-ICI testi. Bir kusurdan ogrenildi:
    ilk surumde bu test SADECE sayisal ozelliklere uygulaniyordu, bu
    yuzden `trend` ve `ema_alignment` gibi -- Faz 460'ta rejim etiketinin
    %100 kopyasi oldugu KANITLANMIS -- kategorik sinyaller dort sartin
    sadece ikisini gecerek "kanitlanmis" gorunuyordu.

    Ayni zaman kovasi icinde en yuksek ve en dusuk P(UP) kategorileri
    ARADA kaliyor mu? Piyasa geneli (ya da rejim kopyasi) bir alanda bir
    kovadaki tum semboller AYNI kategoriye duser -> karsilastirilacak
    ikinci grup yoktur -> None."""
    by_bucket: dict[str, list[dict]] = {}
    for r in members:
        bucket = r.get("time_bucket")
        if bucket is not None:
            by_bucket.setdefault(str(bucket), []).append(r)
    if not by_bucket:
        return None

    total_buckets = len(by_bucket)
    varying_buckets = 0
    weighted_sum = 0.0
    weight_total = 0
    for bucket_members in by_bucket.values():
        if len(bucket_members) < MIN_PER_TIME_BUCKET:
            continue
        if len({str(r["value"]) for r in bucket_members}) < 2:
            continue
        varying_buckets += 1
        high = [r for r in bucket_members if str(r["value"]) == best]
        low = [r for r in bucket_members if str(r["value"]) == worst]
        if not high or not low:
            continue
        n = len(high) + len(low)
        weighted_sum += (_p_up(high) - _p_up(low)) * n
        weight_total += n

    return {
        "buckets": total_buckets,
        "varying_buckets": varying_buckets,
        "symbol_specific": bool(varying_buckets >= 0.5 * total_buckets),
        "separation": (
            round(weighted_sum / weight_total, 6) if weight_total > 0 else None
        ),
    }


def _within_bucket_separation(members: list[dict]) -> dict | None:
    """SEMBOL-ICI (zaman-kovasi-ici) ayrim. Kullanici teshisi (2026-09-09):
    "butun sembollerde ayni degeri aliyor dediklerin onchain verisi."
    Dogru -- onchain ozellikleri belirli bir ANDA tum sembollerde AYNI
    degeri aliyor, dolayisiyla Faz 462'nin ham ayrimi onlarda sembol-bazli
    bir edge'i degil, sadece zaman ici piyasa dalgalanmasini olcuyor
    olabilir.

    Bu fonksiyon o soruyu kesin olarak cevapliyor: AYNI zaman kovasi
    icinde, ozellik sembolleri birbirinden ayirt edebiliyor mu? Piyasa
    geneli bir ozellikte kova ici varyans SIFIRDIR, dolayisiyla hicbir
    kova degerlendirilemez ve sonuc None doner -- yani "kanit yok".

    Faz 459'un donus tabakalamasiyla AYNI ilke: karistiran degiskeni
    (burada zaman) SABIT tutup geriye kalan sinyali olc."""
    by_bucket: dict[str, list[dict]] = {}
    for r in members:
        bucket = r.get("time_bucket")
        if bucket is not None:
            by_bucket.setdefault(str(bucket), []).append(r)
    if not by_bucket:
        return None

    total_buckets = len(by_bucket)
    varying_buckets = 0
    weighted_sum = 0.0
    weight_total = 0
    for bucket_members in by_bucket.values():
        values = [r["value"] for r in bucket_members if _is_numeric(r["value"])]
        if len(bucket_members) < MIN_PER_TIME_BUCKET or len(set(values)) < 2:
            continue
        varying_buckets += 1
        # GERCEK medyan (cift sayida gozlemde iki ortanin ortalamasi).
        # Bir testte yakalandi: sadece iki farkli degerin oldugu kovalarda
        # (or. [10,10,90,90]) `sorted(v)[n//2]` ust degeri secip
        # "yuksek" tarafi BOS birakiyor ve ayrim sessizce hesaplanamiyordu.
        median = statistics.median(values)
        high = [r for r in bucket_members if _is_numeric(r["value"]) and r["value"] > median]
        low = [r for r in bucket_members if _is_numeric(r["value"]) and r["value"] < median]
        if not high or not low:
            continue
        weighted_sum += (_p_up(high) - _p_up(low)) * len(bucket_members)
        weight_total += len(bucket_members)

    return {
        "buckets": total_buckets,
        "varying_buckets": varying_buckets,
        # Kovalarin cok azinda deger degisiyorsa ozellik PIYASA GENELI'dir
        # (klasik ornek: onchain hash_rate/network_activity/solana_tps).
        "symbol_specific": bool(varying_buckets >= 0.5 * total_buckets),
        "separation": (
            round(weighted_sum / weight_total, 6) if weight_total > 0 else None
        ),
    }


def compute_feature_directional_value(
    records: list[dict],
    min_per_side: int = MIN_PER_SIDE,
    min_per_category: int = MIN_PER_CATEGORY,
) -> dict | None:
    """records: [{"feature": str, "value": Any,
                  "forward_label": "UP"|"DOWN", "day": str}, ...]

    Her özellik için `kind` ("numeric"/"categorical"), `separation` ve
    `verdict` ("correct_sign"/"inverted"/"no_signal") döner. Sayısal
    özelliklerde ayrıca `extreme_separation` (üst/alt %10) ve
    `monotonic` bayrağı var — uçta güçlenmeyen bir ayrım gürültü
    şüphelisidir."""
    usable = [
        r for r in records
        if r.get("feature") and r.get("forward_label") in ("UP", "DOWN")
        and r.get("value") is not None
    ]
    if not usable:
        return None

    by_feature: dict[str, list[dict]] = {}
    for r in usable:
        by_feature.setdefault(r["feature"], []).append(r)

    features: dict[str, dict] = {}
    for feature, members in by_feature.items():
        numeric_members = [r for r in members if _is_numeric(r["value"])]
        # Karisik tipli bir alan (bazen sayi, bazen metin) guvenilir
        # degildir; cogunluk sayisalsa sayisal, degilse kategorik sayilir.
        if len(numeric_members) >= 0.9 * len(members) and len(numeric_members) >= 4:
            separation, n_high, n_low = _numeric_separation(numeric_members, 0.75, 0.25)
            extreme, n_eh, n_el = _numeric_separation(numeric_members, 0.90, 0.10)
            usable_flag = (
                separation is not None and n_high >= min_per_side and n_low >= min_per_side
            )

            def _day_numeric(day_members, _n=None):
                day_sep, dh, dl = _numeric_separation(day_members, 0.75, 0.25)
                if day_sep is None or dh < MIN_PER_SIDE_DAILY or dl < MIN_PER_SIDE_DAILY:
                    return None
                return day_sep

            daily = _daily_consistency(numeric_members, _day_numeric)
            within_symbol = _within_bucket_separation(numeric_members)

            # Rejim kırılımı -- havuzlanmış sayı, işaretin rejime göre
            # değiştiği durumları ortalayıp yok eder.
            by_regime: dict[str, dict] = {}
            for regime in sorted({r.get("regime") for r in numeric_members if r.get("regime")}):
                regime_members = [r for r in numeric_members if r.get("regime") == regime]
                regime_sep, rh, rl = _numeric_separation(regime_members, 0.75, 0.25)
                if regime_sep is None or rh < MIN_PER_SIDE_REGIME or rl < MIN_PER_SIDE_REGIME:
                    by_regime[regime] = {"n": len(regime_members), "separation": None,
                                         "usable": False}
                    continue
                by_regime[regime] = {
                    "n": len(regime_members), "separation": round(regime_sep, 6),
                    "usable": True,
                }
            regime_signs = {
                v["separation"] > 0 for v in by_regime.values()
                if v["usable"] and abs(v["separation"]) > NEUTRAL_BAND
            }
            features[feature] = {
                "kind": "numeric",
                "n": len(numeric_members),
                "separation": round(separation, 6) if separation is not None else None,
                "n_high": n_high, "n_low": n_low,
                "extreme_separation": round(extreme, 6) if extreme is not None else None,
                # Ucta guclenme, gercek bilginin en pratik gostergesi
                # (Faz 461'de taker akisinda kullanilan AYNI olcut).
                # ">=", ">" DEGIL. Bir testte yakalandi: az sayida farkli
                # deger alan (or. ikili/kategorik-benzeri) bir ozellikte
                # uc dilim ile ceyreklik AYNI gruba dusuyor, dolayisiyla
                # esitlik normaldir. Elemek istedigimiz gercek kusur
                # ucta ZAYIFLAMA (klasik gurultu imzasi) -- onu ">=" de
                # yakaliyor. Gercek ornek: vwap_deviation_pct ceyreklikte
                # -0,110 iken ucta -0,098'e DUSUYOR, dogru sekilde eleniyor.
                "monotonic": (
                    bool(abs(extreme) >= abs(separation))
                    if (extreme is not None and separation is not None) else None
                ),
                "daily": daily,
                "within_symbol": within_symbol,
                "by_regime": by_regime,
                # True = özelliğin işareti rejimden rejime DEĞİŞİYOR;
                # havuzlanmış sayı bu durumda yanıltıcıdır.
                "sign_flips_across_regimes": bool(len(regime_signs) > 1),
                "usable": usable_flag,
                "verdict": (
                    ("correct_sign" if separation > NEUTRAL_BAND
                     else "inverted" if separation < -NEUTRAL_BAND else "no_signal")
                    if usable_flag else None
                ),
                # "Kanitlanmis" = anlamli ayrim + ucta guclenme + gunluk
                # tutarlilik. Ucunu birden gecmeyen bir ozellik canli
                # skora BAGLANMAZ.
                # "Kanitlanmis" DORT sarti birden gerektirir:
                #   1. anlamli ham ayrim
                #   2. ucta guclenme (monotonluk)  -> gurultu degil
                #   3. gunluk tutarlilik           -> tek gunun kazasi degil
                #   4. SEMBOL-ICI ayrim ayni yonde -> piyasa geneli zaman
                #      dalgalanmasi degil, gercek sembol-bazli edge
                "proven": bool(
                    usable_flag and separation is not None
                    and abs(separation) > NEUTRAL_BAND
                    and extreme is not None and abs(extreme) >= abs(separation)
                    and daily is not None and daily["consistent"]
                    and within_symbol is not None
                    and within_symbol["symbol_specific"]
                    and within_symbol["separation"] is not None
                    and within_symbol["separation"] * separation > 0
                    and abs(within_symbol["separation"]) > NEUTRAL_BAND
                ),
            }
            continue

        by_category: dict[str, list[dict]] = {}
        for r in members:
            by_category.setdefault(str(r["value"]), []).append(r)
        eligible = {
            name: cat for name, cat in by_category.items()
            if len(cat) >= min_per_category
        }
        categories = {
            name: {"n": len(cat), "p_up": round(_p_up(cat), 6)}
            for name, cat in sorted(by_category.items())
        }
        if len(eligible) < 2:
            features[feature] = {
                "kind": "categorical", "n": len(members), "categories": categories,
                "separation": None, "usable": False, "verdict": None,
                "within_symbol": None, "daily": None, "proven": False,
            }
            continue
        rates = {name: _p_up(cat) for name, cat in eligible.items()}
        best = max(rates, key=rates.get)
        worst = min(rates, key=rates.get)
        spread = rates[best] - rates[worst]

        def _day_categorical(day_members, _b=best, _w=worst):
            b = [r for r in day_members if str(r["value"]) == _b]
            w = [r for r in day_members if str(r["value"]) == _w]
            if len(b) < 20 or len(w) < 20:
                return None
            return _p_up(b) - _p_up(w)

        daily = _daily_consistency(members, _day_categorical)
        within_symbol = _within_bucket_categorical(members, best, worst)
        features[feature] = {
            "kind": "categorical",
            "n": len(members),
            "categories": categories,
            "eligible_categories": len(eligible),
            "highest_p_up": {"category": best, "p_up": round(rates[best], 6)},
            "lowest_p_up": {"category": worst, "p_up": round(rates[worst], 6)},
            # Kategorik bir alanda "ters/dogru isaret" kavrami YOK (siralama
            # tanimli degil) -- sadece AYIRT ETME GUCU olculur.
            "separation": round(spread, 6),
            "daily": daily,
            "within_symbol": within_symbol,
            "usable": True,
            "verdict": "discriminative" if spread > NEUTRAL_BAND else "no_signal",
            # Sayisal daldaki ile AYNI siki sartlar (monotonluk disinda --
            # kategorik bir alanda "uc dilim" tanimsiz).
            "proven": bool(
                spread > NEUTRAL_BAND
                and daily is not None and daily["consistent"]
                and within_symbol is not None
                and within_symbol["symbol_specific"]
                and within_symbol["separation"] is not None
                and within_symbol["separation"] > NEUTRAL_BAND
            ),
        }

    ranked = sorted(
        (k for k, v in features.items() if v["usable"] and v["separation"] is not None),
        key=lambda k: -abs(features[k]["separation"]),
    )
    proven = sorted(
        (k for k, v in features.items() if v.get("proven")),
        key=lambda k: -abs(features[k]["separation"]),
    )
    return {
        "sample_size": len(usable),
        "features": features,
        "ranked_by_strength": ranked,
        "proven_features": proven,
        "neutral_band": NEUTRAL_BAND,
    }
