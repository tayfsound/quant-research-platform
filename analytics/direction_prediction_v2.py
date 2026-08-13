"""Direction Prediction v2 — Faz 519-543 (Cognitive Core 2.0 / M4).

Mevcut kalibrasyon sistemi (services/confidence_calibration.py) GERÇEK
ama sadece "kovaya göre gerçek doğruluk oranı"nı (reliability diagram)
ölçüyor — bunu TEK bir sayıya, bir ajanın/modelin genel olasılıksal
tahmin kalitesini karşılaştırılabilir kılan bir skora indirgenmiş hali
yok. Bu modül standart, literatürde tanımlı bir "proper scoring rule"
olan Brier Score'u (Brier, 1950) ekliyor — hem kalibrasyonu hem
çözünürlüğü (resolution) TEK bir sayıda birleştiriyor, icat edilmiş bir
metrik değil.

Kasıtlı olarak SADECE ölçüm/rapor."""

MIN_SAMPLE_SIZE = 10
RANDOM_BASELINE = 0.25  # p=0.5 sabit tahminin Brier skoru


def compute_brier_score(predictions: list[tuple[float, bool]]) -> dict | None:
    """predictions: [(tahmin edilen olasılık, gerçek sonuç doğru muydu), ...]
    GERÇEK geçmiş tahmin-sonuç çiftleri. <MIN_SAMPLE_SIZE gözlemle
    fail-closed None döner. Brier Score = ortalama((p - outcome)^2) —
    0 mükemmel, 0.25 rastgele (p=0.5 sabit tahmin), 1.0 en kötü mümkün."""
    if len(predictions) < MIN_SAMPLE_SIZE:
        return None

    errors = [(p - (1.0 if outcome else 0.0)) ** 2 for p, outcome in predictions]
    brier = sum(errors) / len(errors)

    return {
        "brier_score": round(brier, 6),
        "sample_size": len(predictions),
        "better_than_random": bool(brier < RANDOM_BASELINE),
    }
