"""Autonomous Strategy Synthesizer v1 "Regime Gate Discovery" testleri —
bkz. analytics/strategy_hypothesis_scanner.py."""
import numpy as np

from analytics.strategy_hypothesis_scanner import (
    scan_for_gate_candidates,
    validate_candidate_out_of_sample,
)


def _records(strategy: str, regime: str, n: int, win_rate: float, seed: int) -> list[dict]:
    rng = np.random.RandomState(seed)
    wins = rng.random(n) < win_rate
    return [{"strategy": strategy, "market_regime": regime, "win": bool(w)} for w in wins]


def test_scan_returns_empty_for_empty_input():
    assert scan_for_gate_candidates([]) == []


def test_scan_detects_a_real_injected_negative_effect():
    """SHORT/bearish_low'un gerçek desenine benzer: bir hücre %10
    isabetli, aynı stratejinin geri kalanı %70 isabetli — GERÇEK,
    büyük, n>=30 bir etki, kesin yakalanmalı."""
    records = (
        _records("test_strategy", "bad_regime", n=200, win_rate=0.10, seed=1)
        + _records("test_strategy", "good_regime_a", n=200, win_rate=0.70, seed=2)
        + _records("test_strategy", "good_regime_b", n=200, win_rate=0.70, seed=3)
    )
    candidates = scan_for_gate_candidates(records)
    flagged = {(c["strategy"], c["market_regime"]) for c in candidates}
    assert ("test_strategy", "bad_regime") in flagged
    assert ("test_strategy", "good_regime_a") not in flagged


def test_scan_respects_min_group_size():
    """Gerçek etkili ama küçük örneklemli (n=10 < varsayılan 30) bir
    hücre, esas compute_strategy_regime_compatibility'nin kendi fail-
    closed eşiğiyle zaten dışarıda kalır."""
    records = (
        _records("test_strategy", "bad_regime", n=10, win_rate=0.10, seed=1)
        + _records("test_strategy", "good_regime", n=200, win_rate=0.70, seed=2)
    )
    candidates = scan_for_gate_candidates(records, min_group_size=30)
    assert candidates == []


def test_scan_respects_effect_threshold():
    """Ilımlı bir fark (delta ~ -0.05, eşiğin -0.20'nin çok üstünde)
    aday olarak işaretlenmemeli — istatistiksel olarak anlamlı olsa
    bile ekonomik olarak önemsiz farklar için gate önerilmemeli."""
    records = (
        _records("test_strategy", "slightly_worse", n=500, win_rate=0.55, seed=1)
        + _records("test_strategy", "baseline", n=500, win_rate=0.60, seed=2)
    )
    candidates = scan_for_gate_candidates(records, effect_threshold=-0.20)
    assert candidates == []


def test_scan_filters_out_noise_via_fdr_correction():
    """Klasik multiple-testing gösterimi: 40 hücrenin HİÇBİRİNDE gerçek
    bir etki yok (hepsi AYNI %50 isabetle üretildi, farklı seed'lerle)
    — düzeltmesiz (ham p<0.05) bazı hücreler şans eseri "anlamlı"
    çıkabilir, ama FDR düzeltmesi bunları elemeli. delta eşiği zaten
    çoğunu eleyeceği için, sadece FDR'nin GERÇEK bir aşırı-hassas etki
    olmadan (küçük n, geniş varyans) yanlış pozitif üretmediğini
    doğruluyoruz."""
    records = []
    for i in range(40):
        records += _records("noise_strategy", f"regime_{i}", n=60, win_rate=0.50, seed=100 + i)
    candidates = scan_for_gate_candidates(records, effect_threshold=-0.05, min_group_size=30)
    # %50 civarı gürültüde -0.05 eşiğini asan tesadüfi sapmalar olabilir
    # ama FDR sonrası GERÇEKTEN anlamlı (q<0.05) hücre sayısı çok az
    # kalmalı — hepsi elenmese bile domine etmemeli.
    assert len(candidates) <= 3


def test_validate_out_of_sample_flags_replication():
    """Kötü desen HEM erken HEM geç yarıda tekrarlanıyorsa (gerçek,
    kalıcı bir örüntü) replicated_out_of_sample=True olmalı."""
    records = (
        _records("test_strategy", "bad_regime", n=100, win_rate=0.10, seed=1)
        + _records("test_strategy", "good_regime", n=100, win_rate=0.70, seed=2)
        + _records("test_strategy", "bad_regime", n=100, win_rate=0.12, seed=3)
        + _records("test_strategy", "good_regime", n=100, win_rate=0.68, seed=4)
    )
    candidate = {"strategy": "test_strategy", "market_regime": "bad_regime"}
    result = validate_candidate_out_of_sample(records, candidate, min_group_size=30)
    assert result["replicated_out_of_sample"] is True
    assert result["train_sample_size"] == 100
    # embargo_fraction toplam n'in %2'sini atlıyor, tam olarak bloğun
    # başına denk gelebilir — kesin 100 değil, yaklaşık kalmalı.
    assert 85 <= result["test_sample_size"] <= 100


def test_validate_out_of_sample_flags_non_replication():
    """Kötü desen SADECE erken yarıda var, geç (görülmemiş) yarıda
    normale dönmüşse (tek dönemin tesadüfü) replicated_out_of_sample=
    False olmalı."""
    records = (
        _records("test_strategy", "bad_regime", n=100, win_rate=0.10, seed=1)
        + _records("test_strategy", "good_regime", n=100, win_rate=0.70, seed=2)
        + _records("test_strategy", "bad_regime", n=100, win_rate=0.65, seed=3)
        + _records("test_strategy", "good_regime", n=100, win_rate=0.68, seed=4)
    )
    candidate = {"strategy": "test_strategy", "market_regime": "bad_regime"}
    result = validate_candidate_out_of_sample(records, candidate, min_group_size=30)
    assert result["replicated_out_of_sample"] is False


def test_validate_out_of_sample_handles_missing_test_bucket():
    """Aday, test yarısında hiç yeterli örneklem biriktirmemişse
    (min_group_size altında ya da hiç veri yok) fail-closed False —
    icat edilmiş bir 'tekrarlandı' asla üretilmez."""
    records = _records("test_strategy", "bad_regime", n=100, win_rate=0.10, seed=1)
    candidate = {"strategy": "test_strategy", "market_regime": "bad_regime"}
    result = validate_candidate_out_of_sample(records, candidate, train_fraction=0.9, min_group_size=30)
    assert result["replicated_out_of_sample"] is False
    assert result["test_win_rate"] is None
