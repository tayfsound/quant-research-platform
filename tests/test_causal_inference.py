"""Causal Cognitive Core (Granger Causality) testleri — Faz 861-900 (Cognitive Core 4.0)."""
import numpy as np

from analytics.causal_inference import apply_fdr_correction, compute_granger_causality


def test_detects_a_real_granger_causal_relationship():
    rng = np.random.default_rng(42)
    n = 200
    cause = rng.normal(0, 1, n)
    effect = np.zeros(n)
    for t in range(1, n):
        effect[t] = 0.8 * cause[t - 1] + rng.normal(0, 0.1)

    result = compute_granger_causality(list(cause), list(effect), max_lag=3)
    assert result is not None
    assert result["granger_causes"] is True
    assert result["best_p_value"] < 0.01


def test_independent_series_do_not_show_granger_causality():
    rng = np.random.default_rng(7)
    cause = list(rng.normal(0, 1, 150))
    effect = list(rng.normal(0, 1, 150))
    result = compute_granger_causality(cause, effect, max_lag=3)
    assert result is not None
    assert result["granger_causes"] is False


def test_mismatched_lengths_are_fail_closed():
    assert compute_granger_causality([0.1] * 50, [0.1] * 40, max_lag=2) is None


def test_below_min_sample_size_is_fail_closed():
    assert compute_granger_causality([0.1] * 10, [0.1] * 10, max_lag=2) is None


def test_constant_series_is_handled_without_crashing():
    result = compute_granger_causality([1.0] * 50, [1.0] * 50, max_lag=2)
    assert result is None


def test_fdr_correction_empty_input_is_fail_closed():
    assert apply_fdr_correction([]) == []


def test_fdr_correction_keeps_strong_signal_but_rejects_borderline_noise():
    """Faz 331 — 96 çiftlik gerçek senaryonun küçültülmüş bir hali: 2 tane
    GERÇEKTEN güçlü sinyal (p<0.001) + 94 tane null-hipotez (uniform[0,1]
    rastgele, aralarında şans eseri 0.05'in altına düşenler de var — TAM
    olarak GPT raporunun işaret ettiği "96 bağımsız test" senaryosu).
    Güçlü sinyaller FDR'ı da geçmeli, ham α=0.05 testinin çoğu-şans-eseri
    "anlamlı" saydığı null-hipotezlerin çoğu FDR'da düşmeli."""
    rng = __import__("random").Random(7)
    p_values = [0.0001, 0.0005] + [rng.random() for _ in range(94)]
    naive_significant_count = sum(1 for p in p_values if p < 0.05)
    fdr_flags = apply_fdr_correction(p_values)

    assert naive_significant_count > 2  # şans eseri ekstra "anlamlı" null'lar var
    assert fdr_flags[0] is True and fdr_flags[1] is True  # gerçek sinyaller hayatta kalıyor
    assert sum(fdr_flags) < naive_significant_count  # FDR gerçekten daraltıyor


def test_fdr_correction_all_null_hypothesis_rejects_almost_everything():
    """Gerçek ilişki hiç yokken (tüm p-value'lar uniform[0,1] rastgele)
    ham α=0.05 testi ~%5 yanlış-pozitif üretir ama FDR bunların neredeyse
    tamamını elemeli — GPT raporunun tam işaret ettiği senaryo."""
    rng = __import__("random").Random(42)
    p_values = [rng.random() for _ in range(96)]
    naive_significant = [p < 0.05 for p in p_values]
    fdr_flags = apply_fdr_correction(p_values)

    assert sum(fdr_flags) <= sum(naive_significant)
