"""Faz 268b — Regime-Aware Learning: WeightRepository.get_latest(regime=...)
gerçekten o rejime özel en yeni snapshot'ı buluyor mu, yoksa o rejim için
hiç snapshot yoksa (fail-closed) global'e mi düşüyor — bu iki davranış
karar anında hangi ağırlıkların kullanılacağını doğrudan belirliyor."""
import shutil

import pytest

from contracts.agent_weight_snapshot import AgentWeightSnapshot
from services.weight_repository import WeightRepository


@pytest.fixture
def repo(tmp_path):
    path = str(tmp_path / "weight_repo_regime_test")
    r = WeightRepository(storage_path=path)
    yield r
    shutil.rmtree(path, ignore_errors=True)


def test_get_latest_with_no_regime_arg_behaves_like_before(repo):
    repo.save(AgentWeightSnapshot(weights={"technical": 1.0}).finalize())
    repo.save(AgentWeightSnapshot(weights={"technical": 2.0}).finalize())
    latest = repo.get_latest()
    assert latest.weights["technical"] == 2.0
    assert latest.regime is None


def test_get_latest_returns_the_matching_regime_snapshot_not_global(repo):
    repo.save(AgentWeightSnapshot(weights={"technical": 1.0}, regime=None).finalize())
    repo.save(AgentWeightSnapshot(weights={"technical": 5.0}, regime="bullish_high").finalize())

    regime_snapshot = repo.get_latest(regime="bullish_high")
    global_snapshot = repo.get_latest(regime=None)

    assert regime_snapshot.weights["technical"] == 5.0
    assert regime_snapshot.regime == "bullish_high"
    assert global_snapshot.weights["technical"] == 1.0


def test_get_latest_falls_back_to_global_when_regime_has_no_snapshot_yet(repo):
    """Fail-closed: bearish_low rejimi için henüz hiç snapshot üretilmedi
    — icat edilmiş bir rejim-özel sayı yerine, elimizdeki en iyi gerçek
    veri olan global snapshot'a düşülmeli (hiç ağırlık kullanmamaktan
    iyi)."""
    repo.save(AgentWeightSnapshot(weights={"technical": 1.0}, regime=None).finalize())
    repo.save(AgentWeightSnapshot(weights={"technical": 5.0}, regime="bullish_high").finalize())

    fallback = repo.get_latest(regime="bearish_low")
    assert fallback is not None
    assert fallback.regime is None
    assert fallback.weights["technical"] == 1.0


def test_get_latest_with_regime_prefers_newest_matching_snapshot(repo):
    repo.save(AgentWeightSnapshot(weights={"technical": 1.0}, regime="bullish_high").finalize())
    repo.save(AgentWeightSnapshot(weights={"technical": 9.0}, regime="other").finalize())
    repo.save(AgentWeightSnapshot(weights={"technical": 3.0}, regime="bullish_high").finalize())

    latest = repo.get_latest(regime="bullish_high")
    assert latest.weights["technical"] == 3.0
