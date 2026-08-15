"""Weight Optimizer testleri."""
from contracts.agent_performance import AgentPerformanceRecord
from services.agent_memory import AgentMemory
from services.weight_optimizer import WeightOptimizer


def test_weight_optimizer_proposes_weights():
    memory = AgentMemory()
    # Teknik ajan başarılı
    for _ in range(20):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical",
            direction="LONG",
            confidence=0.8,
            was_correct=True,
            market_regime="trend",
        ))
    # Makro ajan başarısız
    for _ in range(20):
        memory.record(AgentPerformanceRecord(
            agent_domain="macro",
            direction="SHORT",
            confidence=0.6,
            was_correct=False,
            market_regime="trend",
        ))

    optimizer = WeightOptimizer(memory)
    snapshot = optimizer.propose_weights()
    assert "technical" in snapshot.weights
    assert "macro" in snapshot.weights
    # Başarılı ajanın ağırlığı, başarısızdan yüksek olmalı
    assert snapshot.weights["technical"] > snapshot.weights["macro"]


def test_get_summary_with_regime_only_counts_matching_regime_records(tmp_path):
    """Faz 268b — Regime-Aware Learning: aynı ajan farklı rejimlerde
    çok farklı performans gösterebilir (rapor: "TechnicalAgent trending
    piyasada harika, mean-reverting'de felaket olabilir"). get_summary()
    regime verildiğinde SADECE o rejimdeki gerçek kararları saymalı."""
    memory = AgentMemory(storage_path=str(tmp_path / "agent_memory"))
    for _ in range(10):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="LONG", confidence=0.7,
            was_correct=True, market_regime="bullish_high",
        ))
    for _ in range(10):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="LONG", confidence=0.7,
            was_correct=False, market_regime="bearish_low",
        ))

    bullish_summary = memory.get_summary("technical", regime="bullish_high")
    bearish_summary = memory.get_summary("technical", regime="bearish_low")
    unfiltered_summary = memory.get_summary("technical")

    assert bullish_summary.total_predictions == 10
    assert bullish_summary.overall_accuracy == 1.0
    assert bearish_summary.total_predictions == 10
    assert bearish_summary.overall_accuracy == 0.0
    assert unfiltered_summary.total_predictions == 20


def test_insufficient_fresh_samples_keeps_previous_weight_instead_of_crushing_to_near_zero(tmp_path):
    """Faz 268-sonrası — kritik bulgu, gerçek olay: yeterli taze kanıt
    yokken confidence_factor (min(total/window,1.0)) küçük çıkıp
    smoothed_accuracy'nin (veri yokken Bayesian prior sayesinde ~0.5
    "nötr") ÇARPIMI neredeyse sıfıra eziliyordu — "kanıt yok = nötr"
    değil, "kanıt yok = sıfır" davranıyordu. Artık yeterli taze kanıt
    yoksa (< MIN_SAMPLES_FOR_PROPOSAL) hiç değişiklik önerilmiyor, mevcut
    ağırlık aynen korunuyor."""
    import shutil

    from services.weight_optimizer import MIN_SAMPLES_FOR_PROPOSAL
    from services.weight_repository import WeightRepository

    name = str(tmp_path / "weights_insufficient_test")
    try:
        memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_insufficient"))
        # MIN_SAMPLES_FOR_PROPOSAL'ın altında, az sayıda GERÇEK kayıt.
        for _ in range(MIN_SAMPLES_FOR_PROPOSAL - 1):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.8, was_correct=True,
            ))

        repo = WeightRepository(storage_path=name)
        # Önceki (onaylanmış) ağırlık — 1.5 gibi, nötr olmayan bir değer.
        from contracts.agent_weight_snapshot import AgentWeightSnapshot
        repo.save(AgentWeightSnapshot(weights={"technical": 1.5}, evaluation_window=100).finalize())

        optimizer = WeightOptimizer(memory, weight_repository=repo)
        snapshot = optimizer.propose_weights(evaluation_window=100)

        # Sıfıra ezilmiş bir değer DEĞİL, mevcut/önceki ağırlık aynen korunmalı.
        assert snapshot.weights["technical"] == 1.5
    finally:
        shutil.rmtree(name, ignore_errors=True)


def test_propose_weights_excludes_records_before_legacy_cutoff(tmp_path):
    """Faz 268-sonrası — kullanıcı isteği: "her ajanın kararda eşit
    ağırlığı olsun." reliability_legacy_cutoff_at set edildiğinde, bu
    tarihten ÖNCEKİ (eski/bozuk dönem) kayıtlar öneriye hiç girmemeli —
    tıpkı agents/source_reliability_agent.py'de olduğu gibi."""
    import shutil
    from datetime import datetime, timedelta

    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory
    from services.weight_optimizer import MIN_SAMPLES_FOR_PROPOSAL
    from services.weight_repository import WeightRepository

    name = str(tmp_path / "weights_cutoff_test")
    with SessionFactory.get_session() as session:
        original = AppSettingsRepository(session).get("reliability_legacy_cutoff_at")
    try:
        memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_cutoff"))
        # Kesimden ÖNCE (eski/bozuk dönem): tamamen yanlış.
        old_ts = datetime.now() - timedelta(days=2)
        for _ in range(MIN_SAMPLES_FOR_PROPOSAL * 3):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.8,
                was_correct=False, timestamp=old_ts,
            ))
        # Kesimden SONRA (taze, düzeltilmiş dönem): tamamen doğru.
        for _ in range(MIN_SAMPLES_FOR_PROPOSAL * 3):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.8, was_correct=True,
            ))

        # Kesim UYGULANMADAN önceki öneri (eski %0 isabetli kayıtlar dahil).
        repo_no_cutoff = WeightRepository(storage_path=name + "_no_cutoff")
        snapshot_no_cutoff = WeightOptimizer(memory, weight_repository=repo_no_cutoff).propose_weights(evaluation_window=100)

        cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("reliability_legacy_cutoff_at", cutoff, updated_by="test")

        repo = WeightRepository(storage_path=name)
        optimizer = WeightOptimizer(memory, weight_repository=repo)
        snapshot = optimizer.propose_weights(evaluation_window=100)

        # confidence_factor (örneklem büyüklüğüne bağlı) ile smoothed_
        # accuracy (kalite) etkileşimi karışık olduğu için nihai ağırlığı
        # doğrudan karşılaştırmak güvenilir değil — ama "long" penceresi
        # (window=500, hem 30 hem 120 kayıttan çok daha büyük) confidence_
        # factor'ü SADECE ham kayıt SAYISINA bağlı, kaliteden bağımsız:
        # kesim uygulanınca (120 kayıt yerine sadece 30'u sayılınca)
        # kesinlikle daha DÜŞÜK çıkmalı — bu, eski kayıtların gerçekten
        # dışarıda bırakıldığının kalitesiz bir yan etkiyle karışmayan,
        # doğrudan kanıtı.
        assert snapshot.window_breakdown["technical"]["long"] < snapshot_no_cutoff.window_breakdown["technical"]["long"]
        # Ve kalite tarafı: kesimli tarafın ISABETİ (confidence_factor'den
        # bağımsız olarak) gerçekten %100 taze veriyi yansıtmalı — eski
        # %0 isabetli kayıtlar hiç karışmamış olmalı.
        fresh_only_summary = memory.get_summary("technical", window=100, min_timestamp=datetime.fromisoformat(cutoff))
        assert fresh_only_summary.overall_accuracy == 1.0
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("reliability_legacy_cutoff_at", original, updated_by="test")
        shutil.rmtree(name, ignore_errors=True)
        shutil.rmtree(name + "_no_cutoff", ignore_errors=True)


def test_propose_weights_with_regime_produces_a_separate_regime_tagged_snapshot(tmp_path):
    """Faz 268b — bir rejim için önerilen ağırlıklar, global öneriden
    bağımsız, kendi regime etiketiyle saklanmalı — WeightRepository.
    get_latest(regime=...) ile geri okunabilmeli."""
    import shutil

    from services.weight_repository import WeightRepository

    name = str(tmp_path / "weights_regime_test")
    try:
        memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_regime"))
        for _ in range(20):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.8,
                was_correct=True, market_regime="bullish_high",
            ))

        repo = WeightRepository(storage_path=name)
        optimizer = WeightOptimizer(memory, weight_repository=repo)

        snapshot = optimizer.propose_weights(evaluation_window=20, regime="bullish_high")

        assert snapshot.regime == "bullish_high"
        fetched = repo.get_latest(regime="bullish_high")
        assert fetched is not None
        assert fetched.id == snapshot.id
    finally:
        shutil.rmtree(name, ignore_errors=True)
