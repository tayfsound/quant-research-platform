"""Weight Optimizer testleri."""
from contracts.agent_performance import AgentPerformanceRecord
from services.agent_memory import AgentMemory
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository


def test_weight_optimizer_proposes_weights(tmp_path):
    # Faz 242/282: AgentMemory()/WeightRepository() (storage_path
    # override'sız) CANLI, paylaşılan dosyaları okuyup yazıyordu — hem
    # gerçek üretim verisinin (technical/macro) hem de paylaşılan
    # quantdb_test'teki regime=None onay geçmişinin (Faz 282'nin soğuma
    # süresi kontrolü) bu testin kendi senaryosuna karışmaması için
    # tmp_path ile izole edildi.
    memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_history"))
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

    weight_repo = WeightRepository(storage_path=str(tmp_path / "weight_history"))
    optimizer = WeightOptimizer(memory, weight_repository=weight_repo)
    snapshot = optimizer.propose_weights()
    assert "technical" in snapshot.weights
    assert "macro" in snapshot.weights
    # Başarılı ajanın ağırlığı, başarısızdan yüksek olmalı
    assert snapshot.weights["technical"] > snapshot.weights["macro"]


def test_domain_with_no_previous_weight_and_no_fresh_data_falls_back_to_peer_median_not_flat_one(tmp_path):
    """Kullanıcı bulgusu — gerçek olay: bir öneride onchain/time/
    epistemology/relative_strength "— (yeni)" diye 1.000'e sabitlenmişti,
    AYNI öneride technical/macro gibi GERÇEK veriye dayanan ajanlar
    0.2-0.3'e kesilmişti — hiç kanıtlanmamış bir ajan, o an aktif
    değerlendirilip cezalandırılan ajanlardan DAHA GÜVENİLİR görünüyordu.
    Artık önceki ağırlığı hiç olmayan bir domain, sabit 1.0 yerine BU
    RUNDAKİ gerçek verili ağırlıkların medyanına düşüyor."""
    import shutil

    from services.weight_repository import WeightRepository

    name = str(tmp_path / "weights_no_previous_test")
    try:
        memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_no_previous"))
        # technical: neredeyse hep başarısız -> düşük gerçek ağırlık.
        for _ in range(30):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.8, was_correct=False,
            ))
        # macro: neredeyse hep başarılı -> yüksek gerçek ağırlık.
        for _ in range(30):
            memory.record(AgentPerformanceRecord(
                agent_domain="macro", direction="LONG", confidence=0.8, was_correct=True,
            ))
        # onchain: memory.domains() içinde görünmesi için birkaç kayıt var
        # (AgentMemory.domains() sadece en az 1 kaydı olan domain'leri
        # döndürür) ama MIN_SAMPLES_FOR_PROPOSAL(10)'un altında -> yetersiz
        # taze veri sayılır.
        for _ in range(3):
            memory.record(AgentPerformanceRecord(
                agent_domain="onchain", direction="LONG", confidence=0.8, was_correct=True,
            ))

        # weight_repository'de HİÇBİR önceki onaylanmış ağırlık yok (ilk çalıştırma).
        repo = WeightRepository(storage_path=name)

        optimizer = WeightOptimizer(memory, weight_repository=repo)
        snapshot = optimizer.propose_weights(evaluation_window=100)

        assert snapshot.weights["technical"] < snapshot.weights["macro"]
        assert "onchain" in snapshot.weights
        # Sabit 1.0 DEĞİL — technical (düşük) ve macro (yüksek)
        # arasındaki gerçek medyana düşmeli, ikisinin arasında kalmalı.
        assert snapshot.weights["technical"] <= snapshot.weights["onchain"] <= snapshot.weights["macro"]
        assert snapshot.weights["onchain"] != 1.0
    finally:
        shutil.rmtree(name, ignore_errors=True)


def test_single_data_driven_domain_does_not_get_cloned_onto_all_fallback_domains(tmp_path):
    """Faz 282 — kritik bulgu (2026-08-19, gerçek olay: bullish_high
    rejiminde SADECE technical'ın yeterli örneklemi vardı, diğer 8 ajan
    fallback'e düştü; kullanıcı: "hiçbir mantık kuramadım niye böyle bir
    teklifte bulunduğuna dair"). "Medyan" TEK elemanlı bir listede
    matematiksel olarak o TEK değere eşit — sistem technical'ın kendi
    skorunu, hiç kanıtı olmayan 8 ajana AYNEN kopyalamıştı (previous={
    'technical': 1.77}, proposed'da TÜM domain'ler 1.770). Artık medyan
    SADECE >=2 gerçek veri-güdümlü domain varken kullanılıyor; TEK domain
    varsa nötr 1.0'a düşülüyor — bir ajanın kendi skoru asla diğerlerine
    kopyalanmıyor."""
    import shutil

    from services.weight_repository import WeightRepository

    name = str(tmp_path / "weights_single_domain_test")
    try:
        memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_single_domain"))
        # SADECE technical'ın yeterli (>=10) taze örneklemi var — gerçek
        # olaydaki AYNI senaryo (nadir bir rejimde tek ajan aktif).
        for _ in range(30):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.8, was_correct=True,
            ))
        # macro'nun MIN_SAMPLES_FOR_PROPOSAL(10) altında kalan birkaç
        # kaydı var (domains() listesinde görünsün diye) ama önceki
        # ağırlığı da yok -> o da fallback'e düşer.
        for _ in range(3):
            memory.record(AgentPerformanceRecord(
                agent_domain="macro", direction="LONG", confidence=0.8, was_correct=True,
            ))

        repo = WeightRepository(storage_path=name)
        optimizer = WeightOptimizer(memory, weight_repository=repo)
        snapshot = optimizer.propose_weights(evaluation_window=100)

        assert snapshot.weights["technical"] != 1.0  # gerçek veriyle hesaplandı
        # macro, technical'ın skoruna KOPYALANMAMALI — nötr 1.0'a düşmeli.
        assert snapshot.weights["macro"] == 1.0
        assert snapshot.weights["macro"] != snapshot.weights["technical"]
    finally:
        shutil.rmtree(name, ignore_errors=True)


def test_domain_with_previous_weight_but_no_fresh_data_still_keeps_its_own_previous_weight(tmp_path):
    """Az önceki testin karşıtı: önceki ağırlığı OLAN bir domain, medyan
    fallback'e DEĞİL, kendi önceki değerine düşmeye devam etmeli — bu
    zaten doğru çalışıyordu (bkz. test_insufficient_fresh_samples_keeps_
    previous_weight_instead_of_crushing_to_near_zero), medyan fallback'i
    eklerken bunu bozmadığımızı doğruluyoruz."""
    import shutil

    from contracts.agent_weight_snapshot import AgentWeightSnapshot
    from services.weight_repository import WeightRepository

    name = str(tmp_path / "weights_has_previous_test")
    try:
        memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_has_previous"))
        for _ in range(30):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.8, was_correct=False,
            ))
        for _ in range(30):
            memory.record(AgentPerformanceRecord(
                agent_domain="macro", direction="LONG", confidence=0.8, was_correct=True,
            ))
        for _ in range(3):
            memory.record(AgentPerformanceRecord(
                agent_domain="onchain", direction="LONG", confidence=0.8, was_correct=True,
            ))
        # onchain'in az veriyle bile GERÇEK bir önceki onaylı ağırlığı var: 0.05.
        repo = WeightRepository(storage_path=name)
        repo.save(AgentWeightSnapshot(weights={"onchain": 0.05}, evaluation_window=100).finalize())

        optimizer = WeightOptimizer(memory, weight_repository=repo)
        snapshot = optimizer.propose_weights(evaluation_window=100)

        assert "onchain" in snapshot.weights
        assert snapshot.weights["onchain"] == 0.05
    finally:
        shutil.rmtree(name, ignore_errors=True)


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

        # Faz 269-sonrası — kritik bulgu: confidence_factor artık statik
        # bir hedefe (500) göre DEĞİL, kesimden bu yana TÜM ajanlar
        # arasında GERÇEKTEN birikmiş en yüksek örnekleme göre (dinamik
        # tavan) ölçülüyor — bu testte tek domain (technical) olduğu için
        # tavan HER İKİ senaryoda da kendi toplamına eşit, yani confidence_
        # factor ikisinde de ≈1.0. Eski varsayım (kesim = daha az kayıt =
        # kesinlikle daha düşük confidence_factor) artık geçerli değil —
        # asıl doğrudan kanıt, kesimin GERÇEKTEN eski kalitesiz veriyi
        # dışarıda bıraktığı (aşağıdaki fresh_only_summary kontrolü) ve bu
        # sayede nihai skorun (kalite serbestçe yükselince) kesimli
        # tarafta daha YÜKSEK çıkması — eski %0 isabetli kayıtlar taze
        # %100 isabetli veriyi artık aşağı çekmiyor.
        assert snapshot.window_breakdown["technical"]["long"] > snapshot_no_cutoff.window_breakdown["technical"]["long"]
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
