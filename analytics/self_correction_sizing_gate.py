"""Self-Correction Sizing Gate — Faz 368, kullanıcı kararı (2026-08-28):
"boyut küçült, iptal etme." risk/drawdown_sizing.py ile AYNI "asla
büyütmez, sadece küçültür" ilkesi — services/scientific_self_correction_
gatherer.py'nin zaten hesapladığı hipotez-retest verisini (bkz. o
modülün docstring'i: original_win_rate/recent_win_rate/hypothesis_
still_valid/significant_change) kullanır, yeni bir istatistik icat
edilmiyor.

Gerçek olay (2026-08-28, Grok raporu doğrulaması): council'in LONG
hipotezi ("LONG neredeyse her zaman kazanır") 1033 örneklemlik orijinal
%96.4'ten, son 1634 kararda %71.5'e düşmüş — istatistiksel olarak
anlamlı (p<0.001), hipotez artık geçerli sayılmıyor. Kill switch/rejim
kapıları gibi sert bir "dur" yerine, DrawdownSizingStage'in kademeli
frenine benzer, orantılı bir boyut küçültmesi tercih edildi."""

MIN_MULTIPLIER = 0.4


def self_correction_size_multiplier(segment: dict | None) -> float:
    """segment: gather_scientific_self_correction()'ın segments'inden
    ilgili yönün ("direction=LONG"/"direction=SHORT") kaydı. Hipotez hâlâ
    geçerliyse (hypothesis_still_valid=True) ya da değişim istatistiksel
    olarak anlamlı değilse (significant_change=False) — ya da segment/
    veri eksikse (fail-open, icat edilmiş bir küçültme asla uygulanmaz)
    — tam boyut (1.0). Aksi halde recent_win_rate/original_win_rate
    oranı (orantılı, icat edilmiş bir eğri değil) — [MIN_MULTIPLIER, 1.0]
    aralığında sabitlenir, asla büyütmez (oran >1.0 çıksa bile 1.0'da
    tavanlanır)."""
    if not segment:
        return 1.0
    if segment.get("hypothesis_still_valid", True):
        return 1.0
    if not segment.get("significant_change", False):
        return 1.0

    original = segment.get("original_win_rate")
    recent = segment.get("recent_win_rate")
    if not original or original <= 0 or recent is None:
        return 1.0

    ratio = recent / original
    return max(MIN_MULTIPLIER, min(1.0, ratio))
