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


def test_compute_calibration_curve_excludes_records_before_legacy_cutoff():
    """Faz 268-sonrası — kullanıcı bulgusu: bu eğri hiçbir zaman legacy-
    cutoff filtresi uygulamıyordu — WeightOptimizer/SourceReliabilityAgent'ta
    (reliability_legacy_cutoff_at) düzeltilen AYNI hata sınıfı burada
    unutulmuştu. Eski (kesimden önce kapanmış) kayıplı kararlar, yeni
    (kesimden sonra kapanmış) kazançlı kararlarla karışmamalı."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from services import confidence_calibration

    # Nadir kullanılan bir kova (0.1) seçildi — diğer testlerin sık
    # kullandığı 0.5-0.9 aralığıyla çakışma riski en düşük.
    bucket_confidence = 0.12
    old_ts = datetime.now(UTC) - timedelta(days=2)
    fresh_ts = datetime.now(UTC)
    with SessionFactory.get_session() as session:
        original_cutoff = AppSettingsRepository(session).get("reliability_legacy_cutoff_at")
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for _ in range(25):
                event = DecisionEvent(
                    id=uuid4(), symbol="CALTEST", proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, confidence=bucket_confidence, status="open",
                    entry_price=100.0, quantity=1.0,
                )
                repo.persist(event)
                repo.close_position(decision_id=str(event.id), exit_price=90.0, pnl=-1.0, closed_at=old_ts)
            for _ in range(25):
                event = DecisionEvent(
                    id=uuid4(), symbol="CALTEST", proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, confidence=bucket_confidence, status="open",
                    entry_price=100.0, quantity=1.0,
                )
                repo.persist(event)
                repo.close_position(decision_id=str(event.id), exit_price=110.0, pnl=1.0, closed_at=fresh_ts)

        curve_without_cutoff = dict(confidence_calibration.compute_calibration_curve())

        cutoff = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("reliability_legacy_cutoff_at", cutoff, updated_by="test")

        curve_with_cutoff = dict(confidence_calibration.compute_calibration_curve())

        # Kesim olmadan eski kayıplarla yeni kazançlar karışık -> düşük/orta.
        # Kesimle SADECE taze kazançlı kayıtlar kalmalı -> belirgin yüksek.
        assert curve_with_cutoff[0.1] > curve_without_cutoff[0.1]
        assert curve_with_cutoff[0.1] >= 0.9
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "reliability_legacy_cutoff_at", original_cutoff, updated_by="test"
            )
        from sqlalchemy import text
        with SessionFactory.get_session() as session:
            session.execute(text("DELETE FROM decisions WHERE symbol = 'CALTEST'"))
            session.commit()


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


def test_calibrate_domain_confidence_with_no_evidence_count_applies_full_calibration(monkeypatch):
    """evidence_count verilmezse (varsayılan None) eski davranış aynen
    korunmalı — tam kalibrasyon, geriye dönük uyumluluk."""
    from services import confidence_calibration as cc

    monkeypatch.setattr(cc, "get_domain_calibration_curves", lambda: {"quant": [(0.2, 0.8)]})
    result = cc.calibrate_domain_confidence("quant", 0.2)
    assert result == 0.8


def test_calibrate_domain_confidence_dampens_correction_for_single_evidence_decision(monkeypatch):
    """Faz 268e — gerçek bulgu: quant_agent'ın TEK kanıtlı (sadece
    "200-EMA bear trend") ham %25 güvenli kararı, kalibrasyonla %77.5'e
    şişmişti — o kovanın geçmişi muhtemelen çoğunlukla daha çok kanıtlı
    kararlardan oluşuyordu. TEK kanıtlı bir karar artık kalibrasyonun
    SADECE 1/3'ünü (evidence_count/_FULL_TRUST_EVIDENCE_COUNT) alıyor."""
    from services import confidence_calibration as cc

    monkeypatch.setattr(cc, "get_domain_calibration_curves", lambda: {"quant": [(0.25, 0.775)]})
    raw = 0.25
    full = cc.calibrate_domain_confidence("quant", raw)  # evidence_count=None -> tam
    dampened = cc.calibrate_domain_confidence("quant", raw, evidence_count=1)

    assert full == 0.775
    expected = raw + (0.775 - raw) * (1 / 3)
    assert abs(dampened - expected) < 1e-9
    assert dampened < full  # tek kanıtlı karar, tam kalibrasyon kadar yükselmemeli


def test_calibrate_domain_confidence_with_zero_evidence_stays_at_raw_value(monkeypatch):
    from services import confidence_calibration as cc

    monkeypatch.setattr(cc, "get_domain_calibration_curves", lambda: {"quant": [(0.25, 0.9)]})
    result = cc.calibrate_domain_confidence("quant", 0.25, evidence_count=0)
    assert result == 0.25  # hiç kanıt yoksa hiç kalibrasyon uygulanmamalı


def test_calibrate_domain_confidence_with_three_plus_evidence_gets_full_trust(monkeypatch):
    from services import confidence_calibration as cc

    monkeypatch.setattr(cc, "get_domain_calibration_curves", lambda: {"quant": [(0.25, 0.9)]})
    result_3 = cc.calibrate_domain_confidence("quant", 0.25, evidence_count=3)
    result_5 = cc.calibrate_domain_confidence("quant", 0.25, evidence_count=5)
    assert result_3 == 0.9
    assert result_5 == 0.9  # 3'ten fazlası ekstra güven eklemiyor, tavan zaten 3'te


def test_asset_class_of_symbol_groups_gold_backed_tokens_together():
    """Faz 247: kullanıcının getirdiği PAXG/XAUTUSDT raporu — bu ikisi
    'kripto' değil, ayrı bir varlık sınıfında gruplanmalı."""
    from services.confidence_calibration import _asset_class_of_symbol

    assert _asset_class_of_symbol("PAXGUSDT") == "gold_backed"
    assert _asset_class_of_symbol("XAUTUSDT") == "gold_backed"
    assert _asset_class_of_symbol("BTCUSDT") == "crypto"
    assert _asset_class_of_symbol("AAPL") == "equity"
    assert _asset_class_of_symbol("^IXIC") == "equity_index"
    assert _asset_class_of_symbol("GC=F") == "precious_metal_future"
    assert _asset_class_of_symbol("SOMETHING_UNKNOWN") == "other"


def test_compute_asset_class_calibration_curves_separates_by_asset_class(tmp_path):
    """Faz 247 — kullanıcının getirdiği rapor gerçek veriyle doğrulandı:
    technical_agent'ın PAXG/XAUTUSDT'deki gerçek doğruluğu (%40, kötü),
    BTC ağırlıklı genel geçmişinden (%85, iyi) ÇOK farklı olabiliyor —
    asset-class eğrisi bunu ayrı tutmalı, birbirine karıştırmamalı."""
    from contracts.agent_performance import AgentPerformanceRecord
    from services.agent_memory import AgentMemory
    from services.confidence_calibration import compute_asset_class_calibration_curves

    memory = AgentMemory(storage_path=str(tmp_path / "agent_memory"))

    # gold_backed (PAXGUSDT): 0.3 kovasında 25 kayıt, sadece %40 doğru.
    for i in range(25):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="SHORT", confidence=0.3,
            was_correct=(i < 10), symbol="PAXGUSDT",
        ))
    # crypto (BTCUSDT): AYNI kova (0.3), 25 kayıt, %84 doğru.
    for i in range(25):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="SHORT", confidence=0.3,
            was_correct=(i < 21), symbol="BTCUSDT",
        ))

    curves = compute_asset_class_calibration_curves(memory=memory)

    assert curves["technical:gold_backed"] == [(0.3, 0.4)]
    assert curves["technical:crypto"] == [(0.3, 0.84)]


def test_compute_asset_class_calibration_curves_skips_thin_asset_class_samples(tmp_path):
    from contracts.agent_performance import AgentPerformanceRecord
    from services.agent_memory import AgentMemory
    from services.confidence_calibration import compute_asset_class_calibration_curves

    memory = AgentMemory(storage_path=str(tmp_path / "agent_memory"))
    # gold_backed: sadece 5 kayıt — eşiğin (20) altında.
    for i in range(5):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="SHORT", confidence=0.3,
            was_correct=True, symbol="PAXGUSDT",
        ))

    curves = compute_asset_class_calibration_curves(memory=memory)
    assert "technical:gold_backed" not in curves


def test_calibrate_domain_confidence_prefers_asset_class_curve_over_global(monkeypatch):
    """Faz 247: symbol verilirse ve o varlık sınıfı için yeterli veri
    varsa, GLOBAL (tüm sembol) eğrisi yerine asset-class eğrisi
    kullanılmalı — global eğri (0.9) ile asset-class eğrisi (0.4)
    kasıtlı olarak ÇOK farklı, hangisinin gerçekten kullanıldığını
    ayırt edebilmek için."""
    from services import confidence_calibration as cc

    monkeypatch.setattr(cc, "get_domain_calibration_curves", lambda: {"technical": [(0.3, 0.9)]})
    monkeypatch.setattr(
        cc, "get_asset_class_calibration_curves",
        lambda: {"technical:gold_backed": [(0.3, 0.4)]},
    )

    result = cc.calibrate_domain_confidence("technical", 0.3, symbol="PAXGUSDT")
    assert result == 0.4


def test_calibrate_domain_confidence_falls_back_to_global_without_asset_class_data(monkeypatch):
    """Faz 247: symbol verilir ama o varlık sınıfı için (fail-closed)
    yeterli veri yoksa, mevcut global domain eğrisine düşülmeli — eski
    davranış hiç bozulmamalı."""
    from services import confidence_calibration as cc

    monkeypatch.setattr(cc, "get_domain_calibration_curves", lambda: {"technical": [(0.3, 0.9)]})
    monkeypatch.setattr(cc, "get_asset_class_calibration_curves", lambda: {})

    result = cc.calibrate_domain_confidence("technical", 0.3, symbol="PAXGUSDT")
    assert result == 0.9


def test_calibrate_domain_confidence_without_symbol_uses_global_curve_unchanged(monkeypatch):
    """symbol verilmezse (varsayılan None) davranış eskisiyle birebir
    aynı kalmalı — geriye dönük uyumluluk."""
    from services import confidence_calibration as cc

    monkeypatch.setattr(cc, "get_domain_calibration_curves", lambda: {"technical": [(0.3, 0.9)]})
    result = cc.calibrate_domain_confidence("technical", 0.3)
    assert result == 0.9
