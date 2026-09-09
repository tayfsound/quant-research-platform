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

Kasıtlı olarak SADECE ölçüm — hiçbir canlı kararı etkilemiyor.
"""
MIN_PER_SIDE = 200
MIN_PER_CATEGORY = 80
NEUTRAL_BAND = 0.02


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
            features[feature] = {
                "kind": "numeric",
                "n": len(numeric_members),
                "separation": round(separation, 6) if separation is not None else None,
                "n_high": n_high, "n_low": n_low,
                "extreme_separation": round(extreme, 6) if extreme is not None else None,
                # Ucta guclenme, gercek bilginin en pratik gostergesi
                # (Faz 461'de taker akisinda kullanilan AYNI olcut).
                "monotonic": (
                    bool(abs(extreme) > abs(separation))
                    if (extreme is not None and separation is not None) else None
                ),
                "usable": usable_flag,
                "verdict": (
                    ("correct_sign" if separation > NEUTRAL_BAND
                     else "inverted" if separation < -NEUTRAL_BAND else "no_signal")
                    if usable_flag else None
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
            }
            continue
        rates = {name: _p_up(cat) for name, cat in eligible.items()}
        best = max(rates, key=rates.get)
        worst = min(rates, key=rates.get)
        spread = rates[best] - rates[worst]
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
            "usable": True,
            "verdict": "discriminative" if spread > NEUTRAL_BAND else "no_signal",
        }

    ranked = sorted(
        (k for k, v in features.items() if v["usable"] and v["separation"] is not None),
        key=lambda k: -abs(features[k]["separation"]),
    )
    return {
        "sample_size": len(usable),
        "features": features,
        "ranked_by_strength": ranked,
        "neutral_band": NEUTRAL_BAND,
    }
