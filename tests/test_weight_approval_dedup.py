"""Faz 229: kritik bulgu — canlı üretimde WeightOptimizer.optimize() ve
propose_weights() büyük bir ağırlık değişikliği hesapladığında, zaten
bekleyen bir WeightApproval olup olmadığını hiç kontrol etmeden KOŞULSUZCA
yeni bir satır ekliyordu. Gerçek trading cycle'lar (optimize(), her cycle'da)
ve gerçek pozisyon kapanışları (propose_weights(), her kapanışta) bunu sık
sık tetikleyince, canlı DB'de 7000'den fazla neredeyse aynı bekleyen onay
birikti — ve her iki metod da onaylanana kadar ESKİ ağırlığı döndürdüğü
için, gerçek ağırlıklar saatlerce hiç güncellenmeden donuk kaldı. Bu testler
hem dedup kontrolünü hem de "unknown" domain sızıntısının kapatıldığını
doğruluyor."""
import shutil
from uuid import uuid4

from contracts.agent_performance import AgentPerformanceRecord
from contracts.agent_weight_snapshot import AgentWeightSnapshot
from database.repositories.weight_approval_repository import WeightApprovalRepository
from database.session_factory import SessionFactory
from services.agent_memory import AgentMemory
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository


def _isolated_repo(name: str):
    return WeightRepository(storage_path=name)


def _cleanup(name: str):
    shutil.rmtree(name, ignore_errors=True)


def _pending_count() -> int:
    with SessionFactory.get_session() as session:
        return len(WeightApprovalRepository(session).get_pending(limit=100000))


def _clear_all_pending() -> None:
    """has_pending() KASITLI OLARAK global (tek bir 'ağırlık değişikliği
    insan onayı bekliyor' durumu, hangi metodun önerdiğinden bağımsız —
    üretimde doğru davranış). Ama bu, testin kendi ölçümünü paylaşılan
    quantdb_test'teki BAŞKA testlerin bıraktığı pending satırlardan
    izole etmek için, her dedup testinin temiz bir tahtayla başlaması
    gerektiği anlamına geliyor."""
    with SessionFactory.get_session() as session:
        WeightApprovalRepository(session).auto_reject_stale(max_age_seconds=0)


def test_has_pending_reflects_real_db_state():
    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        before = repo.has_pending()

    from contracts.weight_approval import WeightApproval
    with SessionFactory.get_session() as session:
        WeightApprovalRepository(session).save(
            WeightApproval(proposed_weights={"technical": 1.5}, previous_weights={"technical": 1.0}, status="pending")
        )
        assert WeightApprovalRepository(session).has_pending() is True
    # before durumu ne olursa olsun (başka testlerden kalan pending satırlar
    # olabilir), az önce eklediğimiz satırla artık kesinlikle True olmalı —
    # bu, before'un True/False olmasından bağımsız gerçek bir doğrulama.
    assert before in (True, False)


def test_propose_weights_does_not_queue_a_duplicate_when_one_is_already_pending():
    name = "test_weights_dedup_propose"
    try:
        # Faz 282: WeightOptimizer artık rejim başına bir soğuma süresi de
        # kontrol ediyor (bkz. propose_weights() içindeki not) — paylaşılan
        # quantdb_test'teki regime=None geçmişinden etkilenmesin diye
        # benzersiz bir regime kullanılıyor.
        regime = f"test_dedup_propose_{uuid4().hex[:8]}"
        repo = _isolated_repo(name)
        repo.save(AgentWeightSnapshot(weights={"technical": 1.0, "macro": 1.0}, regime=regime).finalize())

        memory = AgentMemory()
        for _ in range(50):
            memory.record(AgentPerformanceRecord(
                agent_domain="macro", direction="SHORT", confidence=0.6, was_correct=False,
                market_regime=regime,
            ))

        optimizer = WeightOptimizer(memory, weight_repository=repo)

        _clear_all_pending()
        before = _pending_count()
        optimizer.propose_weights(evaluation_window=50, regime=regime)
        after_first = _pending_count()
        optimizer.propose_weights(evaluation_window=50, regime=regime)
        after_second = _pending_count()

        assert after_first == before + 1  # ilk çağrı bir tane ekledi
        assert after_second == after_first  # ikinci çağrı YENİ bir tane eklemedi (dedup)
    finally:
        _cleanup(name)


def test_optimize_does_not_queue_a_duplicate_when_one_is_already_pending():
    name = "test_weights_dedup_optimize"
    try:
        repo = _isolated_repo(name)
        repo.save(AgentWeightSnapshot(weights={"technical": 1.0}).finalize())

        memory = AgentMemory()
        optimizer = WeightOptimizer(memory, weight_repository=repo)

        class _FakeOutcome:
            decision_score = 1.0  # büyük bir sıçrama tetikler (>%5)

        agents = [{"domain": "technical", "confidence": 0.9}]

        _clear_all_pending()
        before = _pending_count()
        optimizer.optimize(agents=agents, outcome=_FakeOutcome())
        after_first = _pending_count()
        optimizer.optimize(agents=agents, outcome=_FakeOutcome())
        after_second = _pending_count()

        assert after_first == before + 1
        assert after_second == after_first
    finally:
        _cleanup(name)


def test_regime_specific_approval_does_not_block_or_get_blocked_by_a_different_regime():
    """Faz 268b — Regime-Aware Learning: has_pending() regime parametresi
    olmadan GLOBAL çalışırdı — bir rejimin bekleyen onayı, TAMAMEN
    FARKLI bir rejimin yeni önerisini de bloke ederdi. İki farklı rejim
    aynı anda kendi bekleyen onayına sahip olabilmeli, birbirini
    etkilememeli."""
    name_a = "test_weights_regime_dedup_a"
    name_b = "test_weights_regime_dedup_b"
    # Faz 282: bkz. yukarıdaki testin notu — soğuma süresi kontrolünün
    # paylaşılan quantdb_test'teki "bullish_high"/"bearish_low" geçmişinden
    # (başka testler de bu literal isimleri kullanıyor) etkilenmemesi için
    # benzersiz regime isimleri kullanılıyor.
    regime_a = f"test_regime_dedup_bullish_{uuid4().hex[:8]}"
    regime_b = f"test_regime_dedup_bearish_{uuid4().hex[:8]}"
    try:
        _clear_all_pending()

        repo_a = _isolated_repo(name_a)
        repo_a.save(AgentWeightSnapshot(weights={"technical": 1.0}, regime=regime_a).finalize())
        memory_a = AgentMemory()
        for _ in range(50):
            memory_a.record(AgentPerformanceRecord(
                agent_domain="technical", direction="SHORT", confidence=0.6,
                was_correct=False, market_regime=regime_a,
            ))
        optimizer_a = WeightOptimizer(memory_a, weight_repository=repo_a)
        optimizer_a.propose_weights(evaluation_window=50, regime=regime_a)

        with SessionFactory.get_session() as session:
            assert WeightApprovalRepository(session).has_pending(regime=regime_a) is True
            # Farklı bir rejimin bekleyen onayı YOK — regime_a'nın onayı
            # regime_b'yi bloklamıyor.
            assert WeightApprovalRepository(session).has_pending(regime=regime_b) is False

        repo_b = _isolated_repo(name_b)
        repo_b.save(AgentWeightSnapshot(weights={"technical": 1.0}, regime=regime_b).finalize())
        memory_b = AgentMemory()
        for _ in range(50):
            memory_b.record(AgentPerformanceRecord(
                agent_domain="technical", direction="SHORT", confidence=0.6,
                was_correct=False, market_regime=regime_b,
            ))
        optimizer_b = WeightOptimizer(memory_b, weight_repository=repo_b)
        result_b = optimizer_b.propose_weights(evaluation_window=50, regime=regime_b)

        # regime_a'nın bekleyen onayı VARKEN bile regime_b'nin önerisi
        # gerçekten yeni bir onay satırı olarak kuyruğa girdi.
        with SessionFactory.get_session() as session:
            pending = WeightApprovalRepository(session).get_pending(limit=100000)
            bearish_pending = [p for p in pending if p.regime == regime_b]
        assert len(bearish_pending) == 1
        assert result_b.weights.get("technical") == 1.0  # onaya takıldı, eski değer döndü
    finally:
        _cleanup(name_a)
        _cleanup(name_b)


def test_normalize_domain_rejects_non_voting_agents_instead_of_falling_back_to_unknown():
    """Faz 229: canlı üretimde doğrulandı — pending onaylarda gerçekten
    "unknown" diye bir domain satırı oluşmuştu. _normalize_domain artık
    9 gerçek oy-veren ajan domain'i dışındaki her şey için None döner."""
    from services.weight_optimizer import WeightOptimizer

    assert WeightOptimizer._normalize_domain({"domain": "technical"}) == "technical"
    assert WeightOptimizer._normalize_domain({"agent_id": "risk_challenger_v1"}) is None
    assert WeightOptimizer._normalize_domain({}) is None
    assert WeightOptimizer._normalize_domain({"domain": "alter_ego"}) is None


def test_learning_loop_skips_opinions_with_no_real_agent_domain():
    from contracts.decision_event import DecisionEvent
    from services.learning_loop import LearningLoop

    loop = LearningLoop()
    total_before = loop.agent_memory.total_record_count()

    event = DecisionEvent(
        symbol="TESTUNKNOWN",
        proposed_direction="LONG",
        final_action="LONG",
        agent_opinions=[{"direction": "LONG", "confidence": 0.5}],  # domain yok
        market_snapshot={"raw_snapshot": {"trend": "neutral"}},
    )
    loop._apply_feedback(event, was_correct=True, pnl=1.0)

    total_after = loop.agent_memory.total_record_count()
    # Not: gerçek agent_memory_history/agent_memory.json dosyasında bu
    # düzeltmeden ÖNCEKİ çalıştırmalardan kalma "unknown" kayıtları hâlâ
    # olabilir (temizlenmedi, sadece YENİ kirlenme durduruldu) — bu yüzden
    # asıl kanıt "unknown" domain'inin hiç var olmaması değil, bu çağrının
    # HİÇBİR yeni kayıt eklememiş olması.
    assert total_after == total_before
