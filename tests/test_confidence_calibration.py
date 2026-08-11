"""Faz 248: confidence kalibrasyon testleri."""
from services.confidence_calibration import calibrate_confidence


def test_calibrate_with_empty_curve_returns_raw_value_unchanged():
    """Yeterli gerçek veri yoksa (fail-closed) ham değer değişmemeli."""
    assert calibrate_confidence(0.55, curve=[]) == 0.55


def test_calibrate_interpolates_between_known_points():
    curve = [(0.4, 0.2), (0.6, 0.3)]
    # Tam ortada: doğrusal enterpolasyonla (0.2+0.3)/2 = 0.25
    assert abs(calibrate_confidence(0.5, curve=curve) - 0.25) < 1e-9


def test_calibrate_exact_match_returns_observed_value():
    curve = [(0.4, 0.2), (0.6, 0.3)]
    assert calibrate_confidence(0.4, curve=curve) == 0.2
    assert calibrate_confidence(0.6, curve=curve) == 0.3


def test_calibrate_below_curve_range_returns_raw_value_unchanged():
    """Eğrinin ALT ucunun dışında (hiç gözlenmemiş, çok düşük bir değer)
    icat edilmiş bir düzeltme yapılmamalı — zaten güvenli tarafta."""
    curve = [(0.4, 0.2), (0.6, 0.3)]
    assert calibrate_confidence(0.1, curve=curve) == 0.1


def test_calibrate_above_curve_range_clamps_to_last_observed_rate():
    """Faz 268r — kritik bulgu: eğrinin ÜST ucunun dışında (ör. raw=0.9
    ama eğri 0.6'da bitiyor) önceden ham değer DEĞİŞMEDEN dönüyordu —
    DecisionFusion'ın EV hesabı hiç doğrulanmamış bir güveni aynen
    kullanıyordu. Artık elimizdeki EN SON gerçek gözleme (curve[-1][1])
    sabitleniyor — icat edilmiş bir sayı değil, "bu kadar yüksek bir
    bölgede gördüğümüz en iyi gerçek oran" oydu."""
    curve = [(0.4, 0.2), (0.6, 0.3)]
    assert calibrate_confidence(0.9, curve=curve) == 0.3


def test_compute_calibration_curve_ignores_buckets_below_min_samples():
    from services import confidence_calibration

    original = confidence_calibration._MIN_BUCKET_SAMPLES
    try:
        # Gerçek DB'ye bağlanmadan sadece eşik mantığını doğrula.
        assert original == 20
    finally:
        confidence_calibration._MIN_BUCKET_SAMPLES = original


def test_compute_domain_calibration_curves_builds_one_curve_per_domain(tmp_path):
    """Faz 268al — "İsabeti artırmanın yolu daha akıllı kullanım" yol
    haritasının A fazı: her ajan KENDİ (confidence, was_correct)
    geçmişinden ayrı bir eğri üretmeli — WAIT kayıtları (bir tahmin
    değil) hariç, yeterli örneklemi olmayan domain'ler (technical'e göre
    çok daha az kaydı olan quant gibi) hiç eğri üretmemeli."""
    from contracts.agent_performance import AgentPerformanceRecord
    from services.agent_memory import AgentMemory
    from services.confidence_calibration import compute_domain_calibration_curves

    memory = AgentMemory(storage_path=str(tmp_path / "agent_memory"))

    # technical: 0.7 kovasında 25 kayıt, gerçek doğruluk %80 (20/25) —
    # eşiği (20) geçiyor, eğriye girmeli.
    for i in range(25):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="LONG", confidence=0.7,
            was_correct=(i < 20), pnl=1.0 if i < 20 else -1.0,
        ))
    # quant: sadece 5 kayıt — eşiğin (20) altında, eğriye hiç girmemeli.
    for i in range(5):
        memory.record(AgentPerformanceRecord(
            agent_domain="quant", direction="SHORT", confidence=0.6,
            was_correct=True, pnl=1.0,
        ))
    # time: hep WAIT (Faz245 tasarımı) — kalibrasyona hiç girmemeli.
    for i in range(25):
        memory.record(AgentPerformanceRecord(
            agent_domain="time", direction="WAIT", confidence=0.5,
            was_correct=False, pnl=0.0,
        ))

    curves = compute_domain_calibration_curves(memory=memory)

    assert "technical" in curves
    assert curves["technical"] == [(0.7, 0.8)]
    assert "quant" not in curves
    assert "time" not in curves
