"""Sinyal Seviyesinde Yön Değeri — Faz 460 (2026-09-09).

Faz 459 "Council'in sinyali ters işaretli" dedi (pooled separation
−0,104). Faz 460 bunu SİNYAL seviyesine indiriyor: `decisions.
agent_contributions` içindeki her ajanın `feature_contributions`
sözlüğü, o kararda hangi ham sinyalin hangi yönde ne kadar oy verdiğini
zaten saklıyor — yeni bir kayıt/wiring gerekmiyor, veri BUGÜNE KADAR
ORADAYDI ve hiç bu amaçla okunmamıştı.

Ölçüt Faz 459 ile AYNI: separation = P(UP | katkı>0) − P(UP | katkı<0).
Pozitif katkı "yukarı" oyu demek olduğuna göre, doğru işaretli bir
sinyalde separation POZİTİF olmalı.

2026-09-09'da GERÇEK veriyle bulunan sonuç (7 gün, günlük tutarlılıkla):

    bollinger_confirm   −0,290   (5/5 gün negatif)
    break_of_structure  −0,194   (7/7)
    momentum            −0,164   (7/7)
    adx_strong_confirm  −0,137   (7/7)
    ema_alignment       −0,121   (7/7)
    trend               −0,105   (7/7)
    obv_divergence      +0,070   (6/7 pozitif)
    structure_phase     +0,075   (6/7)
    rsi_extreme         +0,217   (7/7 pozitif -- sistemdeki EN GÜÇLÜ
                                  yön sinyali)

Örüntü kusursuz: TÜM trend-takip sinyalleri ters, TÜM ortalamaya-dönüş
sinyalleri doğru. Dört ufukta (15dk/1sa/4sa/24sa) ayrıca ölçüldü — trend
sinyalleri HİÇBİR ufukta doğruya dönmüyor, sadece sıfıra sönüyor; yani
sorun ufuk seçimi DEĞİL.

EN DERİN BULGU — REJİM EŞDOĞRUSALLIĞI: `trend` ve `momentum`,
`market_regime` etiketiyle %100 eşdoğrusal çıktı (6.019 gözlemde TEK
istisna yok: bearish_* rejimlerde katkı her zaman negatif, bullish_*
rejimlerde her zaman pozitif). Yani bu sinyaller bağımsız kanıt değil,
rejim etiketinin oy olarak yeniden kodlanmış hâli — ve rejim etiketinin
kendisi 1 saatlik ufukta anti-prediktif ("bearish" rejimlerde fiyat
%60-62 ihtimalle YÜKSELİYOR). Council, aynı tek bilgiyi altı farklı
sinyal adı altında tekrar tekrar oyluyordu.

Bu yüzden modül eşdoğrusallığı BİRİNCİ SINIF bir çıktı olarak
raporluyor: bir sinyalin ters olması ile o sinyalin aslında başka bir
şeyin kopyası olması, taban tabana zıt düzeltmeler gerektirir.

Kasıtlı olarak SADECE ölçüm — hiçbir canlı kararı etkilemiyor.
"""
MIN_PER_SIDE = 100
MIN_PER_SIDE_DAILY = 40
# ±0,02 altı, bu örneklem büyüklüklerinde gürültüden ayırt edilemez.
# Keyfi bir eşik olduğu açıkça belirtiliyor (Faz 459 ile AYNI değer).
NEUTRAL_BAND = 0.02


def _separation(members: list[dict]) -> tuple[float | None, int, int]:
    positive = [r for r in members if r["contribution"] > 0]
    negative = [r for r in members if r["contribution"] < 0]
    if not positive or not negative:
        return None, len(positive), len(negative)
    p_up_pos = sum(1 for r in positive if r["forward_label"] == "UP") / len(positive)
    p_up_neg = sum(1 for r in negative if r["forward_label"] == "UP") / len(negative)
    return p_up_pos - p_up_neg, len(positive), len(negative)


def compute_signal_directional_value(
    records: list[dict], min_per_side: int = MIN_PER_SIDE,
) -> dict | None:
    """records: [{"signal": str, "contribution": float,
                  "forward_label": "UP"|"DOWN", "day": str,
                  "regime": str | None}, ...]

    Her sinyal için:
      separation        — P(UP|katkı>0) − P(UP|katkı<0). Pozitif = doğru
                          işaretli, negatif = TERS işaretli.
      daily             — günlük tutarlılık (kaç günde negatif/pozitif).
                          Örtüşen örneklem itirazına karşı asıl kanıt bu
                          (Faz 458'in günlük işaret testiyle aynı ilke).
      regime_collinear  — sinyal, HER rejimin içinde tek bir işarette mi
                          kalıyor? True ise sinyal bağımsız kanıt DEĞİL,
                          rejim etiketinin kopyası.
      verdict           — "correct_sign" / "inverted" / "no_signal"
    """
    usable = [
        r for r in records
        if r.get("signal") and r.get("forward_label") in ("UP", "DOWN")
        and isinstance(r.get("contribution"), (int, float)) and r["contribution"] != 0
    ]
    if not usable:
        return None

    by_signal: dict[str, list[dict]] = {}
    for r in usable:
        by_signal.setdefault(r["signal"], []).append(r)

    signals: dict[str, dict] = {}
    for signal, members in by_signal.items():
        separation, n_pos, n_neg = _separation(members)
        if separation is None or n_pos < min_per_side or n_neg < min_per_side:
            signals[signal] = {
                "n_positive": n_pos, "n_negative": n_neg,
                "separation": None, "usable": False,
            }
            continue

        # Günlük tutarlılık.
        by_day: dict[str, list[dict]] = {}
        for r in members:
            if r.get("day") is not None:
                by_day.setdefault(str(r["day"]), []).append(r)
        daily_separations = []
        for day_members in by_day.values():
            day_sep, dp, dn = _separation(day_members)
            if day_sep is not None and dp >= MIN_PER_SIDE_DAILY and dn >= MIN_PER_SIDE_DAILY:
                daily_separations.append(day_sep)

        # Rejim eşdoğrusallığı: her rejimin İÇİNDE sinyal tek işarette mi?
        # (bkz. modül notu -- Faz 460'ın en derin bulgusu)
        by_regime: dict[str, set[bool]] = {}
        for r in members:
            regime = r.get("regime")
            if regime:
                by_regime.setdefault(regime, set()).add(r["contribution"] > 0)
        regime_collinear = None
        if len(by_regime) >= 2:
            regime_collinear = all(len(signs) == 1 for signs in by_regime.values())

        signals[signal] = {
            "n_positive": n_pos, "n_negative": n_neg,
            "separation": round(separation, 6),
            "usable": True,
            "daily": {
                "days": len(daily_separations),
                "negative_days": sum(1 for s in daily_separations if s < 0),
                "positive_days": sum(1 for s in daily_separations if s > 0),
            },
            "regimes_seen": len(by_regime),
            "regime_collinear": regime_collinear,
            "verdict": (
                "correct_sign" if separation > NEUTRAL_BAND
                else "inverted" if separation < -NEUTRAL_BAND
                else "no_signal"
            ),
        }

    usable_signals = {k: v for k, v in signals.items() if v["usable"]}
    inverted = sorted(
        (k for k, v in usable_signals.items() if v["verdict"] == "inverted"),
        key=lambda k: usable_signals[k]["separation"],
    )
    correct = sorted(
        (k for k, v in usable_signals.items() if v["verdict"] == "correct_sign"),
        key=lambda k: -usable_signals[k]["separation"],
    )
    collinear = sorted(
        k for k, v in usable_signals.items() if v.get("regime_collinear") is True
    )

    return {
        "sample_size": len(usable),
        "signals": signals,
        "inverted_signals": inverted,
        "correct_sign_signals": correct,
        "regime_collinear_signals": collinear,
        "neutral_band": NEUTRAL_BAND,
    }
