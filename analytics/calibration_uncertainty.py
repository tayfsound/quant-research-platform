"""Probability Calibration ve Uncertainty — Faz 544-568 (Cognitive Core 2.0 / M4).

analytics/direction_prediction_v2.py::compute_brier_score() kalibrasyon
VE çözünürlüğü (resolution) TEK bir sayıda karıştırıyor — bir modelin
Brier skoru kötüyse bunun kalibrasyon mu yoksa çözünürlük sorunundan mı
kaynaklandığını ayırt edemez. Bu modül, literatürde standart olan
Expected Calibration Error'ı (ECE — Guo et al. 2017, "On Calibration of
Modern Neural Networks") ekliyor: SADECE kalibrasyonu izole eden bir
metrik — "ajan %70 dediğinde GERÇEKTEN %70 mi doğru çıkıyor" sorusuna tek
bir sayıyla cevap veriyor, icat edilmiş bir formül değil.

Kasıtlı olarak SADECE ölçüm/rapor."""

MIN_SAMPLE_SIZE = 10
DEFAULT_N_BINS = 10


def compute_expected_calibration_error(
    predictions: list[tuple[float, bool]],
    n_bins: int = DEFAULT_N_BINS,
) -> dict | None:
    """predictions: [(tahmin edilen olasılık, gerçek sonuç doğru muydu), ...]
    GERÇEK geçmiş tahmin-sonuç çiftleri. Standart eşit-genişlikte bin'lere
    (0-0.1, 0.1-0.2, ...) bölüp her bin için |bin ortalama tahmini - bin
    gerçek doğruluk oranı| farkının örneklem-ağırlıklı ortalamasını alır
    (ECE formülü). <MIN_SAMPLE_SIZE gözlemle fail-closed None döner —
    boş/az dolu bin'lerden icat edilmiş bir kalibrasyon hatası üretilmez."""
    if len(predictions) < MIN_SAMPLE_SIZE:
        return None

    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for p, outcome in predictions:
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, outcome))

    n = len(predictions)
    ece = 0.0
    bin_details = []
    for i, bucket in enumerate(bins):
        if not bucket:
            continue
        avg_confidence = sum(p for p, _ in bucket) / len(bucket)
        avg_accuracy = sum(1.0 if outcome else 0.0 for _, outcome in bucket) / len(bucket)
        weight = len(bucket) / n
        ece += weight * abs(avg_confidence - avg_accuracy)
        bin_details.append({
            "bin_range": [round(bin_edges[i], 2), round(bin_edges[i + 1], 2)],
            "avg_confidence": round(avg_confidence, 4),
            "avg_accuracy": round(avg_accuracy, 4),
            "sample_size": len(bucket),
        })

    return {
        "expected_calibration_error": round(ece, 6),
        "sample_size": n,
        "bins": bin_details,
    }
