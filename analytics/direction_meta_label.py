"""Yön Meta-Etiketi — Faz 472 (2026-09-09). Madde 7'nin (Council →
evidence provider) ÖLÇÜM adımı.

López de Prado'nun meta-labeling'i: birincil model YÖNÜ söyler, ikincil
model "birincil şu an haklı mı" sorusunu tahmin eder ve büyüklüğü (sıfır
dahil) belirler. Bizde birincil model Council.

`services/meta_label_model.py` ZATEN bir meta-label modeli — ama hedefi
`P(TP önce mi SL önce mi)`, yani yine bir TRADE SONUCU (bariyer
yerleşimine bağlı). Bu oturumun ana bulgusu tam olarak bu karışıklıktı
(Faz 441/446/466/470'te dört ayrı yerde düzeltildi). Bu modül eksik
yarıyı ekliyor: hedef **Council'in YÖN çağrısının sabit ufukta doğru
çıkıp çıkmadığı**.

TASARIM, BU OTURUMDA ÖLÇÜLENLERDEN TÜRETİLDİ — icat edilmedi:

1. HÜCRE = (yön × rejim). Faz 471'de kanıtlandı ki havuzlanmış sayılar
   yapıyı gizliyor: `min_confidence_gate` havuzlanmış −0,042 iken
   bearish_low'da −0,117, bullish_high'ta +0,034. Aynı şekilde `ema`
   havuzlanmış +0,004 iken rejim başına ±0,07. Yani "Council güvenilir
   mi" sorusunun rejimden bağımsız tek bir cevabı YOK.

2. ZAMAN TABANLI train/holdout. Rastgele bölme, "keşiften sonra ne
   oldu" sorusunu cevaplayamaz (Faz 471'in survival mantığıyla aynı).

3. TABAN, HOLDOUT'UN KENDİ dönemi içinden. Piyasa zorlaştıysa hücrenin
   isabeti düşer ama fazlalığı korunabilir — Faz 471'de bu ayrımı
   yapmayan ham WR düşüşünün yanıltıcı olduğu gösterilmişti.

4. OOS'ta İŞARET KORUNMALI. Train'de pozitif, holdout'ta negatif bir
   hücre kanıt değil, gürültüdür.

Kasıtlı olarak SADECE ölçüm — Council'in canlı davranışına HİÇ
dokunmuyor. Bağlama kararı, kanıt birikince ayrı bir onay turu.
"""
MIN_PER_CELL_TRAIN = 60
MIN_PER_CELL_HOLDOUT = 40
DEFAULT_HOLDOUT_FRACTION = 0.3
# Faz 463/467/471 ile AYNI büyüklük.
EDGE_BAND = 0.02


def _correct(record: dict) -> bool:
    return (
        (record["council_direction"] == "LONG" and record["forward_label"] == "UP")
        or (record["council_direction"] == "SHORT" and record["forward_label"] == "DOWN")
    )


def _accuracy(members: list[dict]) -> float:
    return sum(1 for r in members if _correct(r)) / len(members)


def compute_direction_meta_label(
    records: list[dict],
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
) -> dict | None:
    """records: [{"council_direction": "LONG"|"SHORT",
                  "forward_label": "UP"|"DOWN", "regime": str,
                  "timestamp": ...}, ...]

    Her (yön × rejim) hücresi için:
      train_accuracy / holdout_accuracy — Council'in O HÜCREDE haklı
                                          çıkma oranı
      holdout_baseline — AYNI holdout döneminin geneli
      holdout_edge     — hücre − taban. POZİTİF = Council o hücrede
                         GÜVENİLİR KANIT. NEGATİF = o hücrede Council'in
                         dediğinin TERSİ daha isabetli.
      survives_oos     — train ve holdout fazlalıkları AYNI işaretli VE
                         holdout fazlalığı bandı aşıyor.

    `trustworthy_cells` = OOS'tan geçen POZİTİF hücreler; Council'i
    evidence-provider'a çevirirken SADECE bunlara kanıt muamelesi
    yapılmalı. `inverted_cells` ise Council'in sistematik olarak ters
    olduğu hücreler — onlar da bilgidir (işaret çevrilebilir), ama ayrı
    bir karardır."""
    usable = [
        r for r in records
        if r.get("council_direction") in ("LONG", "SHORT")
        and r.get("forward_label") in ("UP", "DOWN")
        and r.get("timestamp") is not None
    ]
    if len(usable) < (MIN_PER_CELL_TRAIN + MIN_PER_CELL_HOLDOUT):
        return None

    ordered = sorted(usable, key=lambda r: r["timestamp"])
    split = int(len(ordered) * (1 - holdout_fraction))
    train, holdout = ordered[:split], ordered[split:]
    if not train or not holdout:
        return None

    train_baseline = _accuracy(train)
    holdout_baseline = _accuracy(holdout)

    cells: dict[str, dict] = {}
    for direction in ("LONG", "SHORT"):
        regimes = sorted({r.get("regime") for r in ordered if r.get("regime")})
        for regime in regimes:
            key = f"{direction}|{regime}"
            cell_train = [
                r for r in train
                if r["council_direction"] == direction and r.get("regime") == regime
            ]
            cell_holdout = [
                r for r in holdout
                if r["council_direction"] == direction and r.get("regime") == regime
            ]
            if (len(cell_train) < MIN_PER_CELL_TRAIN
                    or len(cell_holdout) < MIN_PER_CELL_HOLDOUT):
                cells[key] = {
                    "train_n": len(cell_train), "holdout_n": len(cell_holdout),
                    "usable": False, "survives_oos": False,
                }
                continue

            train_edge = _accuracy(cell_train) - train_baseline
            holdout_edge = _accuracy(cell_holdout) - holdout_baseline
            cells[key] = {
                "direction": direction, "regime": regime,
                "train_n": len(cell_train), "holdout_n": len(cell_holdout),
                "train_accuracy": round(_accuracy(cell_train), 6),
                "holdout_accuracy": round(_accuracy(cell_holdout), 6),
                "train_edge": round(train_edge, 6),
                "holdout_edge": round(holdout_edge, 6),
                "usable": True,
                # Train'de pozitif ama holdout'ta negatif bir hücre kanıt
                # değil, gürültüdür -- işaret korunmalı.
                "survives_oos": bool(
                    train_edge * holdout_edge > 0 and abs(holdout_edge) > EDGE_BAND
                ),
            }

    surviving = [k for k, v in cells.items() if v.get("survives_oos")]
    return {
        "sample_size": len(ordered),
        "train_n": len(train), "holdout_n": len(holdout),
        "train_baseline": round(train_baseline, 6),
        "holdout_baseline": round(holdout_baseline, 6),
        "cells": cells,
        "trustworthy_cells": sorted(
            (k for k in surviving if cells[k]["holdout_edge"] > 0),
            key=lambda k: -cells[k]["holdout_edge"],
        ),
        "inverted_cells": sorted(
            (k for k in surviving if cells[k]["holdout_edge"] < 0),
            key=lambda k: cells[k]["holdout_edge"],
        ),
        "edge_band": EDGE_BAND,
    }
