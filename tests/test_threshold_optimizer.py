"""Faz 204: MetaStage'in ACT/REDUCE eşiklerinin gerçek kapalı işlem
geçmişinden kendi kendine kalibrasyonu.

Faz 482 — bu dosya YENİDEN YAPILANDIRILDI. Grid-search testleri eskiden
gerçek `decisions` tablosuna satır yazıp `compute_suggested_thresholds()`
çağırıyordu; sonuç paylaşılan quantdb_test'te o an ne olduğuna bağlı
olduğu için aynı testler İZOLE geçip TAM PAKET koşusunda düşüyordu.
Grid-search artık saf bir fonksiyon (`select_threshold`) — mantık
deterministik test ediliyor, DB round-trip'i ise ayrı, tek bir
entegrasyon testinde doğrulanıyor.
"""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.threshold_optimizer import compute_suggested_thresholds, select_threshold


def _closed_trade(confidence: float, pnl: float, symbol: str):
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
        final_size=1.0, confidence=confidence,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
    )
    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        repo.persist(event)
        repo.close_position(decision_id=str(event.id), exit_price=100.0, pnl=pnl, closed_at=now)
    return event.id


def _samples(*groups) -> list[tuple[float, float]]:
    """(confidence, pnl, adet) üçlülerinden örneklem listesi üretir."""
    out: list[tuple[float, float]] = []
    for confidence, pnl, count in groups:
        out.extend([(confidence, pnl)] * count)
    return out


# ---------------------------------------------------------------- saf mantık


def test_returns_none_with_insufficient_sample():
    assert select_threshold(_samples((0.6, 1.0, 5)), min_sample=20) is None


def test_grid_search_favors_the_threshold_with_highest_real_mean_reward():
    """Düşük confidence'lı işlemler hep zararlı, yüksek confidence'lılar hep
    kârlı — optimizer'ın düşük-confidence zararlıları eleyen eşiği seçmesi
    gerekir. Her iki grup da MIN_CANDIDATE_SAMPLE_SIZE'ı (20) tek başına
    geçecek kadar büyük; aksi halde yüksek-confidence adayı örneklem
    yetersizliğinden elenirdi."""
    result = select_threshold(
        _samples((0.45, -100.0, 25), (0.85, 100.0, 25)), min_sample=20
    )

    assert result is not None
    assert result["act_threshold"] >= 0.5  # düşük-confidence zararlıları dışlamalı
    assert result["sample_size"] == 25
    assert result["best_reward"] == 100.0


def test_sum_based_reward_would_have_wrongly_favored_the_highest_threshold():
    """Faz 370-devam — KRİTİK canlı olay regresyon testi (gerçek olay:
    act_threshold 0.9'a kilitlenip canlı sistemi durdurdu). Eski SUM-tabanlı
    ödül, eşik yükseldikçe dahil edilen işlem azaldığı için toplamı 0'a
    yaklaştırıyordu (t=0.90'da örneklem TAMAMEN boşalıp sum=0 oluyordu, ki
    0 her negatif sayıdan büyük) — grid-search yapısal olarak en yüksek
    adaya kilitleniyordu. MEAN-tabanlı + MIN_CANDIDATE_SAMPLE_SIZE'lı
    sürüm, örneklem-yetersiz (n=3 < 20) yüksek-confidence adayını elemeli."""
    result = select_threshold(
        _samples((0.45, -100.0, 30), (0.60, 200.0, 25), (0.85, -10.0, 3)),
        min_sample=20,
    )

    assert result is not None
    # 0.85 grubu MIN_CANDIDATE_SAMPLE_SIZE (20) altında olduğu için elenmeli.
    assert result["act_threshold"] < 0.85
    assert result["sample_size"] >= 20


def test_returns_none_when_no_threshold_reaches_positive_expectancy():
    """Faz 482 — İKİNCİ canlı kilitlenme olayının regresyon testi. Gerçek
    olay (9 Eylül): son 500 kapanmış işlemde ızgaranın HER noktası negatif
    expectancy veriyordu (t=0,40 -> -0,60 $/işlem ... t=0,80 -> -3,66) ve
    fonksiyon "en az kötü"yü seçip CANLIYA yazıyordu. Aradaki fark gürültü
    olduğu için act_threshold saatlik turlarda 0,40 ile 0,70 arasında gidip
    geliyordu; 0,70'e sıçradığı turlarda açılma oranı %30,7'den %1,2'ye
    düşüyordu. "Hiçbir eşik bu işlemleri kârlı yapmıyor" bulgusu, bir eşik
    seçme gerekçesi DEĞİL."""
    all_negative = _samples(
        (0.45, -50.0, 25), (0.60, -30.0, 25), (0.75, -10.0, 25), (0.90, -5.0, 25)
    )
    assert select_threshold(all_negative, min_sample=20) is None


def test_break_even_expectancy_is_also_rejected():
    """Sınır durumu: tam sıfır expectancy de "kanıt" sayılmaz — komisyon/
    kayma sonrası gerçek sonuç negatiftir."""
    assert select_threshold(_samples((0.60, 0.0, 25)), min_sample=20) is None


def test_reduce_threshold_trails_act_threshold_but_never_below_floor():
    high = select_threshold(_samples((0.45, -100.0, 25), (0.85, 100.0, 25)), min_sample=20)
    assert high is not None
    assert high["reduce_threshold"] == round(max(0.25, high["act_threshold"] - 0.3), 3)
    assert high["reduce_threshold"] >= 0.25


# ------------------------------------------------------------- DB round-trip


def test_compute_suggested_thresholds_reads_real_closed_trades():
    """Sarmalayıcının GERÇEKTEN `decisions` tablosunu okuduğunu doğrulayan
    tek entegrasyon testi. Paylaşılan DB'de başka kapanmış işlemler de
    olabileceği için sonucun DEĞERİNE değil, bu satırların ölçüme GİRDİĞİNE
    bakıyor — mantığın kendisi yukarıdaki saf testlerde doğrulanıyor."""
    symbol = f"THRESHDB{uuid4().hex[:6]}"
    try:
        for _ in range(25):
            _closed_trade(confidence=0.85, pnl=1_000_000.0, symbol=symbol)

        result = compute_suggested_thresholds(min_sample=20)

        assert result is not None
        assert result["sample_size"] >= 25
        # 25 x $1M bu semboldeki kayıtlar dışında hiçbir şeyin bastıramayacağı
        # kadar büyük — ölçüme girmiş olmaları gerekir.
        assert result["best_reward"] > 0
    finally:
        with SessionFactory.get_session() as session:
            session.execute(text("DELETE FROM decisions WHERE symbol = :s"), {"s": symbol})
            session.commit()
