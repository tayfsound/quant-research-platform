"""Faz 230: kullanıcı isteği — "sistem sessiz kalırsa alarma geçecek mi?"
Faz 203-211'deki 7 katmanlı sessiz-hata zinciri ("AI hiç işlem açmıyor",
hiçbir katman exception fırlatmıyordu) bir daha sessizce yaşanmasın diye
eklenen gerçek izleme katmanı. Bu test, o zincirin TAM İMZASINI (sistem
çalışıyor görünüyor ama HİÇ gerçek yönlü karar üretmiyor) gerçek DB'ye
yazılmış verilerle doğruluyor."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from observability.signal_health import _ZOMBIE_WAIT_SAMPLE_SIZE, _age_seconds, _check_zombie_wait


def test_age_seconds_computes_real_elapsed_time_for_aware_and_naive_timestamps():
    now = datetime.now(UTC)
    aware_five_min_ago = now - timedelta(minutes=5)
    naive_five_min_ago = aware_five_min_ago.replace(tzinfo=None)

    assert 290 < _age_seconds(aware_five_min_ago) < 310
    assert 290 < _age_seconds(naive_five_min_ago) < 310
    assert _age_seconds(None) is None


def test_zombie_wait_detects_the_exact_faz_203_211_signature():
    """Faz 203-211'in gerçek imzası: N ardışık kararın hiçbiri yönlü değil
    (hep WAIT) — sistem cycle üretiyor ama fiilen kör. Bu, "hiç veri yok"
    (checked=False, henüz erken) durumundan AYRI ve daha ciddi bir durum."""
    symbol_prefix = f"ZOMBIE{uuid4().hex[:6]}"
    # _check_zombie_wait() TÜM decisions tablosunun en son N satırına
    # bakıyor (kasıtlı olarak global, sembole özel değil) — paylaşılan
    # quantdb_test'te başka testlerin eşzamanlı yazdığı satırlarla
    # yarışmamak için zaman damgaları AÇIKÇA gelecekte (şu an gerçek
    # zamanla hiçbir gerçek test rekabet edemez).
    future = datetime.now(UTC) + timedelta(days=3650)
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        for i in range(_ZOMBIE_WAIT_SAMPLE_SIZE):
            persistor.persist(DecisionEvent(
                id=uuid4(),
                timestamp=future - timedelta(seconds=i),
                symbol=f"{symbol_prefix}",
                proposed_direction="WAIT",
                final_action="WAIT",
                status="no_trade",
            ))

    result = _check_zombie_wait(ai_enabled=True)
    assert result["checked"] is True
    assert result["healthy"] is False
    assert result["distinct_directions_seen"] == ["WAIT"]


def test_zombie_wait_check_is_skipped_when_ai_is_disabled():
    result = _check_zombie_wait(ai_enabled=False)
    assert result["checked"] is False
