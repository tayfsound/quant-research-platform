"""Faz 268-sonrası — kullanıcı bulgusu: eski implementasyon "reliability"i
son 10 kararın ORTALAMA CONFIDENCE'i olarak hesaplıyordu, ajanın GERÇEKTEN
doğru tahmin edip etmediğine hiç bakmıyordu. Artık services/agent_memory.py
::AgentMemory'nin gerçek (was_correct alanlı) kayıtlarından, gerçek isabet
oranı üzerinden hesaplanıyor."""
from datetime import datetime, timedelta

from agents.source_reliability_agent import SourceReliabilityAgent
from contracts.agent_performance import AgentPerformanceRecord
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.agent_memory import AgentMemory


def _seed(memory: AgentMemory, domain: str, n: int, was_correct: bool, confidence: float = 0.9) -> None:
    for _ in range(n):
        memory.record(AgentPerformanceRecord(
            agent_domain=domain, direction="LONG", confidence=confidence, was_correct=was_correct,
        ))


def test_reliability_reflects_real_accuracy_not_confidence(tmp_path):
    """Kritik ayrım: ajan HEP yüksek confidence (0.95) bildiriyor ama
    GERÇEKTE hep yanlış çıkıyor — reliability düşük olmalı, yüksek değil."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False, confidence=0.95)

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "technical", "confidence": 0.95}])

    assert result[0]["source_reliability"] < 0.35
    assert result[0]["benched"] is True


def test_reliability_reflects_genuinely_correct_track_record(tmp_path):
    # Faz 268-sonrası — kritik bulgu: küçük bir örneklemde (ör. 15) %100
    # ham isabet bile artık Bayesian yumuşatmayla (prior_strength=5)
    # 0.80'e (tam sınıra) düşer — bu KASITLI (gerçek olay: macro ajanının
    # ~23 örneklemlik "harika" son serisi, 600+ işlemlik geçmişte aslında
    # ~%37 isabetliydi; küçük örneklemi tam güvenle işlemek yanıltıcıydı).
    # Bu test 30 örneklemle ("gerçekten büyük, tutarlı bir track record")
    # bu ayrımı koruyor — smoothed değer hâlâ ham orana yaklaşıp %80'i
    # rahatça aşıyor.
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "macro", 30, was_correct=True, confidence=0.5)

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "macro", "confidence": 0.5}])

    assert result[0]["source_reliability"] > 0.8
    assert result[0]["benched"] is False


def test_small_sample_high_accuracy_is_smoothed_not_fully_trusted(tmp_path):
    """Faz 268-sonrası — gerçek olay: macro ajanının son ~23 kararı %82.6
    isabetli görünüyordu (LDOUSDT kararında tek başına %84 nihai güvenle
    kararı taşımasının nedeni buydu) — ama aynı ajanın büyük örneklemli
    (600+ işlem) geçmiş performansı sadece ~%37'ydi. Küçük bir örneklemde
    yüksek ham isabet artık TAM güvenle işlenmiyor — Bayesian yumuşatma
    onu nötre doğru çekiyor, ham orandan belirgin şekilde düşük çıkmalı."""
    memory = AgentMemory(storage_path=str(tmp_path))
    n = 23
    correct_n = round(n * 0.826)
    for i in range(n):
        memory.record(AgentPerformanceRecord(
            agent_domain="macro", direction="LONG", confidence=0.7,
            was_correct=i < correct_n,
        ))

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "macro", "confidence": 0.7}])

    raw_accuracy = correct_n / n
    assert result[0]["source_reliability"] < raw_accuracy
    # Yine de nötrün (0.5) üzerinde kalmalı — gerçekten pozitif bir sinyal
    # var, sadece abartılı güvenle değil.
    assert 0.5 < result[0]["source_reliability"] < raw_accuracy


def test_insufficient_real_samples_is_neutral_not_benched(tmp_path):
    """Fail-closed: yeterli gerçek kanıt (MIN_SAMPLES) yoksa nötr (tam
    ağırlık) — "kanıtlanana kadar güven", eksik veriyle cezalandırma değil."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "onchain", 3, was_correct=False)

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "onchain", "confidence": 0.5}])

    assert result[0]["source_reliability"] == 0.5
    assert result[0]["benched"] is False


def test_state_persists_across_fresh_instances_not_reset_every_call(tmp_path):
    """Kritik bulgu: eski implementasyon in-process bir dict'te tutuyordu
    ve her yeni CognitiveOrchestrator (dolayısıyla her run_trading_cycle_
    task çağrısı, 120 saniyede bir) ile sıfırlanıyordu. Artık AgentMemory
    diskten okunuyor — YENİ bir SourceReliabilityAgent örneği bile aynı
    gerçek geçmişi görmeli."""
    memory_path = str(tmp_path)
    seed_memory = AgentMemory(storage_path=memory_path)
    _seed(seed_memory, "quant", 15, was_correct=False, confidence=0.9)

    # Tamamen YENİ bir örnek — hiçbir in-process state paylaşmıyor.
    fresh_agent = SourceReliabilityAgent(memory=AgentMemory(storage_path=memory_path))
    result = fresh_agent.annotate([{"domain": "quant", "confidence": 0.9}])

    assert result[0]["benched"] is True


def _seed_symbol(memory: AgentMemory, domain: str, symbol: str, n: int, was_correct: bool, confidence: float = 0.7) -> None:
    for _ in range(n):
        memory.record(AgentPerformanceRecord(
            agent_domain=domain, direction="LONG", confidence=confidence, was_correct=was_correct, symbol=symbol,
        ))


def test_reliability_is_asset_class_aware_not_global(tmp_path):
    """Faz 268-sonrası — kullanıcı bulgusu, gerçek veriyle doğrulandı: bir
    ajanın performansı varlık sınıfına göre büyük ölçüde farklılaşabiliyor
    (macro kripto'da %30.5, kripto-dışında %55.4 — TAM TERSİ değil ama bu
    testte netlik için tersi kurgulanıyor). Global tek bir ortalama her
    iki bağlamda da yanlış bir sinyal veriyordu — artık symbol verilirse
    o sembolün varlık sınıfına özel geçmiş kullanılıyor."""
    memory = AgentMemory(storage_path=str(tmp_path))
    # Kripto'da hep yanlış (20 örneklem, yeterli).
    _seed_symbol(memory, "macro", "BTCUSDT", 20, was_correct=False)
    # Hisse senedinde hep doğru (20 örneklem, yeterli).
    _seed_symbol(memory, "macro", "AAPL", 20, was_correct=True)

    agent = SourceReliabilityAgent(memory=memory)

    crypto_result = agent.annotate([{"domain": "macro", "confidence": 0.7}], symbol="ETHUSDT")
    equity_result = agent.annotate([{"domain": "macro", "confidence": 0.7}], symbol="NVDA")

    # ETHUSDT/NVDA hiç doğrudan izlenmemiş ama AYNI varlık sınıfına
    # (crypto/equity) düşüyor — BTCUSDT/AAPL'ın geçmişini kullanmalı.
    assert crypto_result[0]["benched"] is True
    assert crypto_result[0]["source_reliability"] < 0.35
    assert equity_result[0]["benched"] is False
    assert equity_result[0]["source_reliability"] > 0.7


def test_reliability_falls_back_to_global_when_asset_class_has_insufficient_samples(tmp_path):
    """Belirli bir varlık sınıfında yeterli örneklem yoksa (MIN_SAMPLES
    altında), tamamen nötre (0.5) düşmek yerine GLOBAL (tüm sınıflar)
    geçmişe düşülmeli — confidence_calibration.py'nin fail-closed
    deseniyle aynı."""
    memory = AgentMemory(storage_path=str(tmp_path))
    # Kripto'da bol örneklem, hep dogru.
    _seed_symbol(memory, "quant", "BTCUSDT", 20, was_correct=True)
    # Hisse senedinde SADECE 2 örneklem (MIN_SAMPLES=10'un altında).
    _seed_symbol(memory, "quant", "AAPL", 2, was_correct=False)

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "quant", "confidence": 0.7}], symbol="NVDA")

    # NVDA (equity) kendi sınıfında yetersiz veri -> global'e (esas
    # olarak kripto'nun 20 doğru kaydı) düşmeli, nötr (0.5) DEĞİL.
    assert result[0]["source_reliability"] > 0.6


def test_annotate_without_symbol_uses_global_summary_unchanged(tmp_path):
    """Regresyon kontrolü: symbol verilmezse (eski çağıranlar, ör. testler)
    davranış birebir eskisiyle aynı kalmalı — global özet kullanılır."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False, confidence=0.95)

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "technical", "confidence": 0.95}])

    assert result[0]["benched"] is True


def test_concept_drift_benches_an_agent_even_above_the_reliability_threshold(tmp_path):
    """3. taraf inceleme bulgusu, kullanıcı isteği: analytics/concept_
    drift.py şu ana kadar SADECE sistem-geneli çalışıyordu, hiçbir
    ajanın benching'ine bağlı değildi. Bu test: reliability (SADECE son
    20 karara bakar, %60 -> smoothed ~0.567) HÂLÂ eşiğin (0.35) ÜSTÜNDE
    kalacak kadar yüksek olsa bile, baseline'dan (%100) recent'a (%60)
    istatistiksel olarak anlamlı bir düşüş varsa ajan benched olmalı —
    reliability TEK BAŞINA bu düşüşü yakalayamaz, drift kontrolü şart."""
    memory = AgentMemory(storage_path=str(tmp_path))
    # Baseline (eski) pencere: 20 karar, %100 doğru — GERÇEKTEN kusursuz geçmiş.
    for i in range(20):
        memory.record(AgentPerformanceRecord(
            agent_domain="order_flow", direction="LONG", confidence=0.8, was_correct=True,
        ))
    # Recent (yeni) pencere: 20 karar, %60 doğru — reliability eşiğinin
    # (0.35) hâlâ ÜSTÜNDE ama baseline'a göre anlamlı bir düşüş.
    for i in range(20):
        memory.record(AgentPerformanceRecord(
            agent_domain="order_flow", direction="LONG", confidence=0.8, was_correct=i < 12,
        ))

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "order_flow", "confidence": 0.8}])

    assert result[0]["source_reliability"] > 0.35  # reliability TEK BAŞINA benchlemezdi
    assert result[0]["benched"] is True
    assert agent.is_benched("order_flow") is True


def test_concept_drift_does_not_bench_when_recent_performance_is_stable(tmp_path):
    """Aynı (istikrarlı) doğruluk oranıyla iki pencere — istatistiksel
    olarak anlamlı bir fark YOK, drift tetiklenmemeli (yanlış pozitif
    olmamalı)."""
    memory = AgentMemory(storage_path=str(tmp_path))
    for i in range(40):
        memory.record(AgentPerformanceRecord(
            agent_domain="pattern", direction="LONG", confidence=0.7, was_correct=i % 2 == 0,
        ))

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "pattern", "confidence": 0.7}])

    assert result[0]["benched"] is False


def test_concept_drift_does_not_bench_on_improvement():
    """Doğruluk YÜKSELİYORSA (baseline kötü, recent iyi) bu bir
    iyileşme — benching kuralı sadece GERİLEMEYİ (regresyon) cezalandırmalı,
    iyileşmeyi değil."""
    import tempfile

    from services.agent_memory import AgentMemory as _AgentMemory

    with tempfile.TemporaryDirectory() as tmp:
        memory = _AgentMemory(storage_path=tmp)
        for i in range(20):
            memory.record(AgentPerformanceRecord(
                agent_domain="epistemology_test", direction="LONG", confidence=0.6, was_correct=i < 4,
            ))
        for i in range(20):
            memory.record(AgentPerformanceRecord(
                agent_domain="epistemology_test", direction="LONG", confidence=0.6, was_correct=i < 18,
            ))

        agent = SourceReliabilityAgent(memory=memory)
        result = agent.annotate([{"domain": "epistemology_test", "confidence": 0.6}])

        assert result[0]["benched"] is False


def test_concept_drift_requires_at_least_two_full_windows(tmp_path):
    """<2*DRIFT_WINDOW gerçek yönlü kayıt varsa (fail-closed) drift
    kontrolü hiç çalışmamalı, sadece reliability eşiği geçerli olmalı."""
    memory = AgentMemory(storage_path=str(tmp_path))
    for i in range(15):
        memory.record(AgentPerformanceRecord(
            agent_domain="relative_strength", direction="LONG", confidence=0.7, was_correct=i < 12,
        ))

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "relative_strength", "confidence": 0.7}])

    assert result[0]["benched"] is False


def test_legacy_records_before_cutoff_do_not_count(tmp_path, monkeypatch):
    """Kullanıcı isteği: "başlangıç olarak her ajanın kararda eşit
    ağırlığı olsun." reliability_legacy_cutoff_at set edildiğinde, o
    tarihten ÖNCEKİ kayıtlar (eski/bozuk mekanizmanın dönemi) yeni hesaba
    hiç girmemeli."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    memory = AgentMemory(storage_path=str(tmp_path))
    old_record = AgentPerformanceRecord(
        agent_domain="pattern", direction="LONG", confidence=0.9, was_correct=False,
        timestamp=datetime.now() - timedelta(days=2),
    )
    memory.record(old_record)
    # Faz 268-sonrası: 12'den 30'a çıkarıldı — Bayesian yumuşatma artık
    # küçük örneklemi nötre çekiyor (bkz. test_small_sample_high_accuracy_
    # is_smoothed_not_fully_trusted), bu test kesim mantığını (eski kayıt
    # sayılmamalı) doğruluyor, yumuşatmanın kendisini değil — yeterince
    # büyük bir örneklem seçildi ki iki etki birbirine karışmasın.
    _seed(memory, "pattern", 30, was_correct=True, confidence=0.6)

    cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
    with SessionFactory.get_session() as session:
        original = AppSettingsRepository(session).get("reliability_legacy_cutoff_at")
        AppSettingsRepository(session).set("reliability_legacy_cutoff_at", cutoff, updated_by="test")
    try:
        agent = SourceReliabilityAgent(memory=memory)
        result = agent.annotate([{"domain": "pattern", "confidence": 0.6}])
        assert result[0]["benched"] is False
        assert result[0]["source_reliability"] > 0.8
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("reliability_legacy_cutoff_at", original, updated_by="test")


def _save_trustworthy_report(pairs: list[dict]) -> None:
    from contracts.agent_combination_reliability_report import AgentCombinationReliabilityReport
    from database.repositories.agent_combination_reliability_report_repository import (
        AgentCombinationReliabilityReportRepository,
    )

    with SessionFactory.get_session() as session:
        AgentCombinationReliabilityReportRepository(session).save(
            AgentCombinationReliabilityReport(
                result={"pairs": pairs, "baseline_win_rate": 0.7, "baseline_sample_size": 100, "n_trades": 100},
            )
        )


def _set_gate_threshold(value: str) -> str:
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        original = repo.get("agent_combination_gate_min_win_rate")
        repo.set("agent_combination_gate_min_win_rate", value, updated_by="test")
    return original


def _restore_gate_threshold(original: str) -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("agent_combination_gate_min_win_rate", original, updated_by="test")


def test_combination_override_unbenches_a_domain_agreeing_with_a_trustworthy_group(tmp_path):
    """Faz 367-devam — kullanıcı isteği: "ajanları kendi başlarına
    değerlendirmeye devam ettiğimiz sürece çözemeyiz." technical solo
    benchlenmiş (kötü geçmiş) ama ŞU AN quant ile AYNI yönde oy veriyor,
    ve technical+quant tarihsel olarak güvenilir/eşik-üstü bir grup —
    bench kararı geçersiz kılınmalı."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False, confidence=0.9)

    original = _set_gate_threshold("0.74")
    _save_trustworthy_report([{
        "domains": ["technical", "quant"], "win_rate": 0.95,
        "fdr_significant": True, "max_shared_trade_overlap_pct": 0.1, "sample_size": 40,
    }])
    try:
        agent = SourceReliabilityAgent(memory=memory)
        result = agent.annotate([
            {"domain": "technical", "confidence": 0.9, "direction": "SHORT"},
            {"domain": "quant", "confidence": 0.7, "direction": "SHORT"},
        ])
        technical = next(r for r in result if r["domain"] == "technical")
        assert technical["benched"] is False
        assert technical["combination_override_applied"] is True
    finally:
        _restore_gate_threshold(original)


def test_combination_override_does_not_apply_when_agreeing_agents_dont_match_a_group(tmp_path):
    """technical benchlenmiş ve ŞU AN sadece macro ile aynı yönde —
    technical+macro güvenilir grup listesinde YOK, bench kararı korunmalı."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False, confidence=0.9)

    original = _set_gate_threshold("0.74")
    _save_trustworthy_report([{
        "domains": ["technical", "quant"], "win_rate": 0.95,
        "fdr_significant": True, "max_shared_trade_overlap_pct": 0.1, "sample_size": 40,
    }])
    try:
        agent = SourceReliabilityAgent(memory=memory)
        result = agent.annotate([
            {"domain": "technical", "confidence": 0.9, "direction": "SHORT"},
            {"domain": "macro", "confidence": 0.7, "direction": "SHORT"},
        ])
        technical = next(r for r in result if r["domain"] == "technical")
        assert technical["benched"] is True
        assert technical["combination_override_applied"] is False
    finally:
        _restore_gate_threshold(original)


def test_combination_override_does_not_apply_when_agreeing_agents_vote_opposite_directions(tmp_path):
    """technical+quant güvenilir bir grup ama BU KARARDA quant TERS yönde
    (LONG) oy veriyor — technical'ın SHORT'u tek başına kalıyor, bench
    kararı korunmalı."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False, confidence=0.9)

    original = _set_gate_threshold("0.74")
    _save_trustworthy_report([{
        "domains": ["technical", "quant"], "win_rate": 0.95,
        "fdr_significant": True, "max_shared_trade_overlap_pct": 0.1, "sample_size": 40,
    }])
    try:
        agent = SourceReliabilityAgent(memory=memory)
        result = agent.annotate([
            {"domain": "technical", "confidence": 0.9, "direction": "SHORT"},
            {"domain": "quant", "confidence": 0.7, "direction": "LONG"},
        ])
        technical = next(r for r in result if r["domain"] == "technical")
        assert technical["benched"] is True
        assert technical["combination_override_applied"] is False
    finally:
        _restore_gate_threshold(original)


def test_combination_override_ignores_a_group_below_the_win_rate_threshold(tmp_path):
    """technical+quant grubu var ama win_rate eşiğin altında — bench
    kararı korunmalı, "sadece güçlendirme" ilkesi (gate ile AYNI eşik)."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False, confidence=0.9)

    original = _set_gate_threshold("0.74")
    _save_trustworthy_report([{
        "domains": ["technical", "quant"], "win_rate": 0.50,
        "fdr_significant": True, "max_shared_trade_overlap_pct": 0.1, "sample_size": 40,
    }])
    try:
        agent = SourceReliabilityAgent(memory=memory)
        result = agent.annotate([
            {"domain": "technical", "confidence": 0.9, "direction": "SHORT"},
            {"domain": "quant", "confidence": 0.7, "direction": "SHORT"},
        ])
        technical = next(r for r in result if r["domain"] == "technical")
        assert technical["benched"] is True
        assert technical["combination_override_applied"] is False
    finally:
        _restore_gate_threshold(original)


def test_combination_override_never_applies_to_a_domain_that_wasnt_benched(tmp_path):
    """Zaten benchlenmemiş bir domain'de override alanı False kalmalı —
    "override" sadece GERÇEKTEN bir bench kararını geçersiz kıldığında
    anlamlı, her zaman tetiklenen bir bayrak değil."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "pattern", 30, was_correct=True, confidence=0.6)

    original = _set_gate_threshold("0.74")
    _save_trustworthy_report([{
        "domains": ["pattern", "quant"], "win_rate": 0.95,
        "fdr_significant": True, "max_shared_trade_overlap_pct": 0.1, "sample_size": 40,
    }])
    try:
        agent = SourceReliabilityAgent(memory=memory)
        result = agent.annotate([
            {"domain": "pattern", "confidence": 0.6, "direction": "SHORT"},
            {"domain": "quant", "confidence": 0.7, "direction": "SHORT"},
        ])
        pattern = next(r for r in result if r["domain"] == "pattern")
        assert pattern["benched"] is False
        assert pattern["combination_override_applied"] is False
    finally:
        _restore_gate_threshold(original)


def test_combination_override_is_a_noop_without_directions_in_opinions(tmp_path):
    """Geriye dönük uyumluluk: direction hiç verilmezse (eski çağıran
    şekli) davranış hiç değişmemeli — bench kararı solo hesaba göre kalır."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False, confidence=0.9)

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "technical", "confidence": 0.9}])
    assert result[0]["benched"] is True
    assert result[0]["combination_override_applied"] is False
