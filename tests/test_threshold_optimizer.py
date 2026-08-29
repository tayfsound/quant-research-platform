"""Faz 204: MetaStage'in ACT/REDUCE eşiklerinin gerçek kapalı işlem
geçmişinden kendi kendine kalibrasyonu."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.threshold_optimizer import compute_suggested_thresholds


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


def test_returns_none_with_insufficient_closed_trades():
    symbol = f"THRESH{uuid4().hex[:8]}"
    for i in range(5):
        _closed_trade(confidence=0.6, pnl=1.0, symbol=symbol)

    # Sadece bu testin ürettiği 5 işlemle DB'de yeterli örnek yok demiyoruz
    # (paylaşılan test DB'de başka gerçek kapalı işlemler de olabilir) —
    # ama min_sample'ı yapay olarak yükselterek "yetersiz veri" davranışını
    # deterministik test ediyoruz.
    result = compute_suggested_thresholds(min_sample=100_000)
    assert result is None


def test_grid_search_favors_the_threshold_with_highest_real_mean_reward():
    """Düşük confidence'lı işlemler hep zararlı, yüksek confidence'lılar hep
    kârlı olacak şekilde kurgula — optimizer'ın gerçekten yüksek eşiği
    seçmesi gerekir (düşük confidence'lı zararlıları elemek için). Her iki
    grup da MIN_CANDIDATE_SAMPLE_SIZE'ı (20) tek başına geçecek kadar büyük
    — aksi halde yüksek-confidence adayı örneklem yetersizliğinden elenir."""
    # Paylaşılan test DB'de başka testlerin bıraktığı kapalı işlemler de
    # olabilir (son 500 içinde) — kendi sinyalimizin bunları eziyor olması
    # için aşırı büyük büyüklükler kullanıyoruz.
    symbol = f"THRESH{uuid4().hex[:8]}"
    for _ in range(25):
        _closed_trade(confidence=0.45, pnl=-100_000.0, symbol=symbol)  # düşük conf, hep zarar
    for _ in range(25):
        _closed_trade(confidence=0.85, pnl=100_000.0, symbol=symbol)  # yüksek conf, hep kâr

    result = compute_suggested_thresholds(min_sample=20)

    assert result is not None
    assert result["act_threshold"] >= 0.5  # düşük-confidence zararlıları dışlamalı
    assert result["sample_size"] >= 25


def test_sum_based_reward_would_have_wrongly_favored_the_highest_threshold_when_overall_negative():
    """Faz 370-devam — KRİTİK canlı olay regresyon testi (gerçek olay:
    act_threshold 0.9'a kilitlenip canlı sistemi durdurdu). Tüm işlemler
    hafif zararlı (çoğunluk daha zararlı, azınlık — ve örneklem-yetersiz —
    az zararlı) olacak şekilde kurgulanmış: eski SUM-tabanlı ödül eşik
    yükseldikçe dahil edilen işlem azaldığı için toplamı 0'a yaklaştırıyor
    (t=0.90'da örneklem TAMAMEN boşalıp sum=0 oluyor, ki 0 her negatif
    sayıdan büyük) — grid-search yapısal olarak en yüksek adaya (0.90)
    kilitleniyordu. Yeni MEAN-tabanlı + MIN_CANDIDATE_SAMPLE_SIZE'lı sürüm,
    örneklem-yetersiz (n=3 < 20) yüksek-confidence adayını elemeli ve genel
    zararlı ortamda makul (yüksek olmayan) bir eşikte kalmalı."""
    symbol = f"THRESH{uuid4().hex[:8]}"
    for _ in range(30):
        _closed_trade(confidence=0.45, pnl=-1000.0, symbol=symbol)  # çoğunluk, ciddi zararlı
    for _ in range(3):
        _closed_trade(confidence=0.85, pnl=-10.0, symbol=symbol)  # azınlık, örneklem yetersiz, hafif zararlı

    result = compute_suggested_thresholds(min_sample=20)

    assert result is not None
    # 0.85 grubu MIN_CANDIDATE_SAMPLE_SIZE (20) altında olduğu için elenmeli
    # — eski SUM-tabanlı davranış burada (t=0.90'da örneklem boşalıp sum=0
    # olduğu için) 0.90'a kilitlenirdi.
    assert result["act_threshold"] < 0.85
    assert result["sample_size"] >= 20
