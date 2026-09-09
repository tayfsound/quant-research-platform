"""Kapı Seçim Değeri — Faz 467 (2026-09-09).

Faz 459 bağımsız bir problem bulmuştu: icra kapıları (EV kapısı + risk +
meta + min_confidence...) sinyalin EN TERS örneklerini seçip geçiriyor.
Ölçülen `execution_amplification` 2,32'den 3,72'ye çıktı — yani sorun
kaybolmuyor, büyüyor.

2026-09-09'da elle yapılan teşhiste baskın kapı bulundu:
`min_confidence_gate` (3 günde 2388 engelleme, açılan kararlarda SIFIR).
Ve havuzlanmış veride YANLIŞ tarafı seçiyor:

    geçenler   (confidence >= 0,70)  n=3.198   isabet %45,6
    engellenen (confidence <  0,70)  n=24.682  isabet %47,7

LONG'da ilişki daha da çarpıcı ve monoton: güven 0,28'de isabet %65,5,
güven 0,83'te %43,0. Mekanizma da tutarlı — confidence, Faz 460'ta ters
işaretli olduğu kanıtlanan trend/momentum/ema/adx yığınından üretiliyor;
yüksek güven = güçlü trend uzlaşması = ortalamaya dönüşün en çok
cezalandırdığı an (Faz 448'in MTF bulgusuyla AYNI kök).

AMA BU BULGU KENDİ KANIT ÇITAMIZI GEÇEMEDİ: Faz 463'te "kanıtlanmış"
için günlerin >= %80'inde aynı yön şartını koymuştuk; min_confidence_gate
günlük kırılımda 5/8 (%62,5) çıktı ve en son üç günün ikisi TERS yönde.
Havuzlanmış 22 puanlık ilişki gerçek olabilir ama tek bir rejim
döneminin etkisi de olabilir — bugün AYNI tuzağa iki kez düştük
(`rsi_percentile` ham −0,175 iken sembol-içi +0,000; onchain özellikleri
piyasa-geneli çıktı).

Bu yüzden kapıya DOKUNULMADI ve bunun yerine ölçüm kalıcı hale
getirildi: gözlem penceresi boyunca kanıt kendiliğinden birikecek,
tahmin yürütmek yerine bakıp karar vereceğiz.

Kasıtlı olarak SADECE ölçüm — hiçbir kapıyı değiştirmiyor.
"""
MIN_PER_GROUP = 200
MIN_PER_GROUP_DAILY = 40
NEUTRAL_BAND = 0.02
MIN_CONSISTENT_DAY_RATIO = 0.8


def _hit_rate(members: list[dict]) -> float:
    hits = sum(
        1 for r in members
        if (r["direction"] == "LONG" and r["forward_label"] == "UP")
        or (r["direction"] == "SHORT" and r["forward_label"] == "DOWN")
    )
    return hits / len(members)


def compute_gate_selection_effect(records: list[dict]) -> dict | None:
    """records: [{"blocking_gates": list[str], "direction": "LONG"|"SHORT",
                  "forward_label": "UP"|"DOWN", "day": str}, ...]

    `blocking_gates` BOŞ olan kararlar "tüm kapılardan geçmiş" sayılır ve
    her kapı için ortak karşılaştırma grubudur.

    Her kapı için:
      passed_hit_rate   — hiçbir kapıya takılmayanların isabeti
      blocked_hit_rate  — BU kapıya takılanların isabeti
      selection_value   — passed − blocked.
                          POZİTİF = kapı işini yapıyor (daha iyileri
                          geçiriyor). NEGATİF = kapı TERS SEÇİM yapıyor,
                          yani engellediği kararlar geçirdiklerinden
                          DAHA İYİ.
      daily             — günlük tutarlılık (Faz 463 ile AYNI çıta).
      proven            — anlamlı etki + günlük tutarlılık. Bu bayrak
                          True olmadan hiçbir kapı değiştirilmemeli."""
    usable = [
        r for r in records
        if r.get("direction") in ("LONG", "SHORT")
        and r.get("forward_label") in ("UP", "DOWN")
        and isinstance(r.get("blocking_gates"), list)
    ]
    if len(usable) < MIN_PER_GROUP:
        return None

    passed = [r for r in usable if not r["blocking_gates"]]
    if len(passed) < MIN_PER_GROUP:
        return None
    passed_hit = _hit_rate(passed)

    gate_names: set[str] = set()
    for r in usable:
        gate_names.update(r["blocking_gates"])

    gates: dict[str, dict] = {}
    for gate in sorted(gate_names):
        blocked = [r for r in usable if gate in r["blocking_gates"]]
        if len(blocked) < MIN_PER_GROUP:
            gates[gate] = {
                "blocked_n": len(blocked), "usable": False,
                "selection_value": None, "verdict": None, "proven": False,
            }
            continue

        blocked_hit = _hit_rate(blocked)
        selection_value = passed_hit - blocked_hit

        # Günlük tutarlılık: her gün AYNI karşılaştırma, ayrı ayrı.
        by_day: dict[str, dict[str, list[dict]]] = {}
        for r in passed:
            if r.get("day") is not None:
                by_day.setdefault(str(r["day"]), {"passed": [], "blocked": []})["passed"].append(r)
        for r in blocked:
            if r.get("day") is not None:
                by_day.setdefault(str(r["day"]), {"passed": [], "blocked": []})["blocked"].append(r)

        daily_values = []
        for groups in by_day.values():
            if (len(groups["passed"]) < MIN_PER_GROUP_DAILY
                    or len(groups["blocked"]) < MIN_PER_GROUP_DAILY):
                continue
            daily_values.append(_hit_rate(groups["passed"]) - _hit_rate(groups["blocked"]))

        daily = None
        if len(daily_values) >= 3:
            negative = sum(1 for v in daily_values if v < 0)
            positive = sum(1 for v in daily_values if v > 0)
            dominant = max(negative, positive)
            daily = {
                "days": len(daily_values),
                "negative_days": negative,
                "positive_days": positive,
                "consistency_ratio": round(dominant / len(daily_values), 4),
                "consistent": bool(dominant / len(daily_values) >= MIN_CONSISTENT_DAY_RATIO),
            }

        verdict = (
            "selective" if selection_value > NEUTRAL_BAND
            else "anti_selective" if selection_value < -NEUTRAL_BAND
            else "no_effect"
        )
        gates[gate] = {
            "blocked_n": len(blocked),
            "blocked_hit_rate": round(blocked_hit, 6),
            "selection_value": round(selection_value, 6),
            "daily": daily,
            "usable": True,
            "verdict": verdict,
            # Bir kapiyi degistirmek icin GEREKEN cita. Faz 463'un
            # dersini tekrarliyor: havuzlanmis bir iliski, gunluk
            # tutarlilik olmadan tek bir rejim doneminin etkisi olabilir.
            "proven": bool(
                verdict != "no_effect" and daily is not None and daily["consistent"]
            ),
        }

    anti_selective = sorted(
        (k for k, v in gates.items() if v["usable"] and v["verdict"] == "anti_selective"),
        key=lambda k: gates[k]["selection_value"],
    )
    return {
        "sample_size": len(usable),
        "passed_n": len(passed),
        "passed_hit_rate": round(passed_hit, 6),
        "gates": gates,
        "anti_selective_gates": anti_selective,
        "proven_anti_selective_gates": sorted(
            k for k in anti_selective if gates[k]["proven"]
        ),
        "neutral_band": NEUTRAL_BAND,
    }
