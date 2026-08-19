"""Faz 214: kritik bulgu — WeightOptimizer.optimize() büyük ağırlık
değişikliklerini (>%10) WeightApproval kuyruğuna alıp insan onayı
bekliyordu, ama aynı sınıfın propose_weights() metodu (services/
position_closer.py'nin Faz 210b/211b'de gerçek kapanan her işlemde
çağırdığı yol) bu kapıdan hiç geçmiyordu — doğrudan kaydediyordu.
Artık ikisi de aynı onay kapısını kullanıyor."""
import shutil
from uuid import uuid4

from contracts.agent_performance import AgentPerformanceRecord
from contracts.agent_weight_snapshot import AgentWeightSnapshot
from database.repositories.weight_approval_repository import WeightApprovalRepository
from database.session_factory import SessionFactory
from services.agent_memory import AgentMemory
from services.weight_optimizer import MAX_WEIGHT_DELTA, WeightOptimizer
from services.weight_repository import WeightRepository


def _isolated_repo():
    repo = WeightRepository(storage_path="test_weights_approval_gate")
    return repo


def _cleanup():
    shutil.rmtree("test_weights_approval_gate", ignore_errors=True)


def test_large_weight_jump_is_queued_for_approval_not_applied_directly():
    try:
        # Faz 229: dedup düzeltmesi eklendi — zaten bekleyen bir onay VARSA
        # propose_weights() yeni bir tane eklemiyor (bkz. test_weight_
        # approval_dedup.py). Faz 282: ayrıca bir soğuma süresi kontrolü
        # eklendi (regime'in EN SON onayı — durumu ne olursa olsun — çok
        # yakınsa yeni öneri hesaplanmaz). İkisi de paylaşılan quantdb_
        # test'teki BAŞKA testlerden/regime=None geçmişinden etkilenmesin
        # diye bu test kendine ait, benzersiz bir regime kullanıyor.
        regime = f"test_gate_large_{uuid4().hex[:8]}"

        repo = _isolated_repo()
        repo.save(AgentWeightSnapshot(weights={"technical": 1.0, "macro": 1.0}, regime=regime).finalize())

        memory = AgentMemory()
        # technical'i tam isabetli yap — smoothed_accuracy ~1.0'a yakın,
        # önceki 1.0'dan farkı %10'un altında kalabilir; macro'yu ise
        # tamamen başarısız yaparak büyük bir düşüş (>%10) tetikle.
        for _ in range(50):
            memory.record(AgentPerformanceRecord(
                agent_domain="macro", direction="SHORT", confidence=0.6, was_correct=False,
                market_regime=regime,
            ))

        optimizer = WeightOptimizer(memory, weight_repository=repo)
        result = optimizer.propose_weights(evaluation_window=50, regime=regime)

        # Büyük değişiklik onay bekliyor olmalı — mevcut (eski) snapshot
        # döndürülmeli, YENİ öneri sessizce uygulanmamalı.
        assert result.weights.get("macro") == 1.0

        with SessionFactory.get_session() as session:
            pending = WeightApprovalRepository(session).get_pending(limit=50)
            proposed_macros = [p.proposed_weights.get("macro", 1.0) for p in pending if p.regime == regime]
        assert any(v < 0.9 for v in proposed_macros)
    finally:
        _cleanup()


def test_small_weight_change_still_applies_directly():
    try:
        # Faz 282: bkz. yukarıdaki testin notu — soğuma süresi kontrolü
        # paylaşılan quantdb_test'teki regime=None geçmişinden etkilenmesin
        # diye benzersiz bir regime kullanılıyor.
        regime = f"test_gate_small_{uuid4().hex[:8]}"

        repo = _isolated_repo()
        # Önceki ağırlık, az örnekle üretilecek öneriye yakın olsun (az
        # örnekte smoothed_accuracy Bayesian prior'a — 0.5'e — çeker, ama
        # confidence_factor küçük olduğu için nihai öneri 0'a yakın kalır;
        # burada %10'un altında bir fark hedefliyoruz).
        repo.save(AgentWeightSnapshot(weights={"technical": 0.02}, regime=regime).finalize())

        memory = AgentMemory()
        for _ in range(3):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.6, was_correct=True,
                market_regime=regime,
            ))

        optimizer = WeightOptimizer(memory, weight_repository=repo)
        result = optimizer.propose_weights(evaluation_window=100, regime=regime)

        assert abs(result.weights["technical"] - 0.02) < MAX_WEIGHT_DELTA
        # Onaya takılmadığının doğrudan kanıtı: yeni öneri gerçekten
        # kaydedilmiş (repo'nun "latest"i artık bu sonuç).
        latest = repo.get_latest(regime=regime)
        assert latest.weights.get("technical") == result.weights.get("technical")
        assert latest.id == result.id
    finally:
        _cleanup()
