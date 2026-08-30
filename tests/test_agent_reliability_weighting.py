"""Faz 381 — saf matematik testleri: yeni uncertainty-additive
ağırlıklandırmanın eski çarpımsal (hard suppression) davranışla TEK
kaynak için eşleştiğini, ama BİRDEN FAZLA kaynak birleştiğinde kademeli
(üstel-çöküş-değil) davrandığını kilitliyor. Bkz. services/agent_
reliability_weighting.py docstring'i — kullanıcının PYPLUSDT bulgusu ve
sistem genelinde 642/642 karar reddinin kök nedeni."""
import pytest

from services.agent_reliability_weighting import (
    MAX_BENCH_PENALTY,
    compute_challenge_uncertainty,
    compute_performance_weight,
    compute_reliability_uncertainty,
)

BENCH_THRESHOLD = 0.35


def test_not_benched_contributes_zero_uncertainty():
    assert compute_reliability_uncertainty(0.9, BENCH_THRESHOLD, benched=False) == 0.0


def test_maximally_benched_matches_old_flat_floor():
    """source_reliability=0 (en kötü durum) — eski MIN_INFLUENCE=0.1 ile
    pratik olarak eşleşmeli: gerçekten kötü bir ajan hâlâ güçlü şekilde
    susturuluyor, regresyon yok."""
    uncertainty = compute_reliability_uncertainty(0.0, BENCH_THRESHOLD, benched=True)
    weight = compute_performance_weight(uncertainty, 0.0)
    assert weight == pytest.approx(0.1, abs=0.01)


def test_marginally_benched_is_far_less_suppressed_than_old_flat_floor():
    """source_reliability=0.30, eşik=0.35 — eski sistemde YİNE 0.1 (flat
    floor) olurdu. Yeni sistemde eşiğin az altındaki bir ajan neredeyse
    hiç bastırılmamalı — asıl düzeltilen davranış."""
    uncertainty = compute_reliability_uncertainty(0.30, BENCH_THRESHOLD, benched=True)
    weight = compute_performance_weight(uncertainty, 0.0)
    assert weight > 0.6
    assert weight > 6 * 0.1  # eski flat floor'un en az 6 katı


def test_single_challenge_penalty_matches_old_multiplicative_result():
    """TEK bir itiraz (ceza=0.3) — eski `performance_weight *= (1-0.3)`
    ile TAM AYNI sonucu vermeli (odds-dönüşümünün matematiksel özelliği)."""
    uncertainty = compute_challenge_uncertainty([0.3])
    weight = compute_performance_weight(0.0, uncertainty)
    assert weight == pytest.approx(0.7, abs=1e-6)


def test_multiple_challenges_compound_less_harshly_than_old_multiplicative_chain():
    old_style = (1 - 0.3) * (1 - 0.3)  # eski sıralı çarpım
    uncertainty = compute_challenge_uncertainty([0.3, 0.3])
    new_style = compute_performance_weight(0.0, uncertainty)
    assert new_style > old_style


def test_bench_and_challenge_combined_still_suppresses_genuinely_bad_agent():
    """Bugünkü PYPLUSDT vakası gibi: hem benched (kötü, deficit yüksek)
    hem de cevapsız itiraz var. Yeni model eskisi kadar SIKI olmasa da
    hâlâ ANLAMLI şekilde bastırmalı — "gerçek kötü ajanlar hâlâ
    susturuluyor" ilkesi."""
    reliability_uncertainty = compute_reliability_uncertainty(0.05, BENCH_THRESHOLD, benched=True)
    challenge_uncertainty = compute_challenge_uncertainty([0.3])
    weight = compute_performance_weight(reliability_uncertainty, challenge_uncertainty)
    assert weight < 0.25


def test_moe_tilt_applies_as_separate_multiplier_on_top():
    uncertainty = compute_reliability_uncertainty(0.0, BENCH_THRESHOLD, benched=True)
    base_weight = compute_performance_weight(uncertainty, 0.0, moe_tilt=1.0)
    tilted_down = compute_performance_weight(uncertainty, 0.0, moe_tilt=0.7)
    tilted_up = compute_performance_weight(uncertainty, 0.0, moe_tilt=1.3)
    assert tilted_down == pytest.approx(base_weight * 0.7, abs=1e-4)
    assert tilted_up == pytest.approx(base_weight * 1.3, abs=1e-4)


def test_weight_is_always_bounded_between_zero_and_moe_tilt_ceiling():
    for sr in (0.0, 0.1, 0.2, 0.3, 0.34):
        uncertainty = compute_reliability_uncertainty(sr, BENCH_THRESHOLD, benched=True)
        weight = compute_performance_weight(uncertainty, compute_challenge_uncertainty([0.3, 0.2, 0.1]))
        assert 0.0 < weight <= 1.0


def test_max_bench_penalty_constant_is_documented_and_positive():
    assert 0.0 < MAX_BENCH_PENALTY < 1.0
