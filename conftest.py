"""Testlerin gerçek dev/dashboard veritabanına (quantdb) hiç dokunmaması için
ayrı bir test veritabanı (quantdb_test) — kök neden bulgusu: testler her
çalıştığında SessionFactory üzerinden gerçek dev DB'ye yazıyordu, bu da
dashboard'da (Experiments listesi, Transactions sayfası, app_settings) rastgele
test sembolleri ve "%100 kazanma oranı" gibi anlamsız veri olarak görünüyordu
— aynı sorun üç ayrı yerde tekrar tekrar yaşandı.

Faz 243: aynı sınıf sorun AgentMemory (services/agent_memory.py) için de
çıktı — testler AgentMemory()'yi varsayılan path'le çağırdığında gerçek
agent_memory_history/agent_memory.json'a (WeightOptimizer'ın ağırlık
önerilerini hesapladığı gerçek dosya) yazıyordu. 60.519 kayıttan 21.649'u
test çöpü çıktı. .gitignore'daki "tmp_test_memory/" satırı bu niyetin
izi ama hiç bağlanmamıştı — şimdi bağlanıyor.

Faz 319: AgentMemory JSON dosyasından Postgres/TimescaleDB'ye taşındı
(agent_performance_records tablosu, quantdb_test'te de migrate edilmiş
olmalı). AGENT_MEMORY_STORAGE_PATH artık bir dosya yolu değil — yeni
`namespace` sütununun değeri, ama izolasyon rolü (testlerin paylaşımlı
canlı/gerçek namespace'ten [''] ayrılması) AYNI kaldı.

Bu dosya en üstte, `config`/`database` hiçbir yerden import edilmeden ÖNCE
ortam değişkenlerini test DB'sine çeviriyor — `config.get_settings()`
`@lru_cache`'li olduğu için ilk çağrıldığı andaki ortam değişkenleri kalıcı
oluyor, o yüzden bu dosyanın pytest'in gerçek uygulama kodunu import etmeden
önce çalışması (kök conftest.py, pytest garantisi) kritik.

quantdb_test'i oluşturup migrate etmek için:
    python3 -c "import psycopg2; c=psycopg2.connect('postgresql://quant:quantpass@localhost:5432/postgres'); c.autocommit=True; c.cursor().execute(\"CREATE DATABASE quantdb_test OWNER quant\")"
    DATABASE_URL_SYNC=postgresql+psycopg2://quant:quantpass@localhost:5432/quantdb_test python3 -m alembic upgrade head
"""
import os
import uuid

os.environ["DATABASE_URL_SYNC"] = "postgresql+psycopg2://quant:quantpass@localhost:5432/quantdb_test"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://quant:quantpass@localhost:5432/quantdb_test"
os.environ["TIMESCALE_URL"] = "postgresql+asyncpg://quant:quantpass@localhost:5432/quantdb_test"
# Faz 363 — kritik bulgu: bu namespace SABİT bir string'di (her pytest
# çalıştırmasında AYNI) — testler arasında değil, PYTEST SESSION'LARI
# ARASINDA da paylaşılıyordu, DB'de kalıcı olduğu için haftalarca birikti
# (gerçek ölçüm: quantdb_test'te 770 technical + 654 macro kaydı, en son
# yazma bu oturumdaki bir test koşusuyla aynı ana denk geldi). Bu birikim
# technical_agent'ın SourceReliabilityAgent'tan gelen performance_weight'ini
# 0.0'a düşürüp council_orchestrator testlerini (tek ajanlı senaryoda
# weight=1.0 bekleyen) kırdı. CANLI/ÜRETİM sistemi ETKİLENMEDİ — o namespace=''
# kullanıyor (bkz. services/agent_memory.py), tamamen ayrı bir Postgres
# veritabanında (quantdb_test vs quantdb) — ama test suite'in kendi
# güvenilirliğini bozuyordu. Her pytest SÜRECİ artık kendi benzersiz
# namespace'ini alıyor (uuid4) — session'lar arası birikim artık mümkün
# değil. Aynı session İÇİNDEKİ testler arası paylaşım (bazı testlerin
# KASITLI "was_correct=False" eklemesi) hâlâ mümkün ama bu ARTIK KALICI
# DEĞİL, bir sonraki pytest çalıştırması temiz bir namespace'le başlıyor.
os.environ["AGENT_MEMORY_STORAGE_PATH"] = f"tmp_test_memory/agent_memory_history_{uuid.uuid4().hex}"
# AGENT_CONFIDENCE_MODEL_STORAGE_PATH KASITLI OLARAK sabit bırakıldı — bu,
# agent_memory_history'nin aksine GERÇEK bir dosya sistemi yolu (Postgres'e
# hiç taşınmadı, services/agent_confidence_model.py::ConfidenceModelRepository
# hâlâ Path(storage_path).mkdir(exist_ok=True) kullanıyor) VE dosya isimleri
# sabit ("{domain}_latest.json" — her yeni model ESKİSİNİN ÜZERİNE yazılıyor),
# INSERT ile BİRİKEN bir tablo değil — session'lar arası kirlilik riski yok,
# session-bazlı benzersizleştirmeye gerek yok.
os.environ["AGENT_CONFIDENCE_MODEL_STORAGE_PATH"] = "tmp_test_memory/confidence_model_history"

import pytest


@pytest.fixture(scope="session", autouse=True)
def _purge_orphaned_test_decisions_at_session_start():
    """Faz 363 — kritik bulgu: testlerin çoğu kendi ürettiği decisions
    satırlarını try/finally ile temizliyor (bkz. tests/test_pump_fade_
    strategy.py::_cleanup_symbol, tests/test_decision_recorder_execution_
    mode.py) ama bu SADECE süreç normal bitince çalışır — pytest süreci
    dıştan öldürülürse (Bash araç zaman aşımı, Ctrl+C) finally hiç
    çalışmaz, satır paylaşımlı quantdb_test'te KALICI kalır. Gerçek olay:
    8 günde (18-26 Ağustos) 548 satırlık pump_fade_v1 birikimi (-$3M
    toplam), pump_fade'in gerçek devre kesicisini HER pytest oturumunda
    yanlışlıkla tetikleyip 16 ilgisiz testi kırıyordu; ayrı bir birikim
    (execution_mode='testnet' AND status='open') ise close_due_positions()
    gibi TÜM açık pozisyonları tarayan testlerin gerçek Binance testnet
    API'sine bağlanıp "Invalid symbol" ile patlamasına yol açıyordu
    (tests/test_position_lifecycle.py + tests/test_pump_fade_strategy.py'de
    46 ilgisiz test). Session BAŞINDA (henüz hiçbir test çalışmadan) bu
    satırlar mantık gereği SADECE önceki, yarım kalmış oturumlardan
    kalabilir — güvenle silinir. Session İÇİNDEKİ testlerin kendi
    temizliği (normal bitişte) değişmeden çalışmaya devam eder."""
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        session.execute(
            text("DELETE FROM decisions WHERE execution_mode = 'testnet' AND status = 'open'")
        )
        session.execute(
            text(
                "DELETE FROM decisions WHERE status = 'closed' "
                "AND experiment_bucket IN ('pump_fade_v1', 'basis_arb_v1')"
            )
        )
        session.commit()
    yield


@pytest.fixture(scope="session", autouse=True)
def _disable_signal_persistence_gate_by_default():
    """Faz 362 — signal_persistence_gate_enabled canlıda varsayılan AÇIK
    (gerçek veriyle doğrulanmış, koruyucu bir mekanizma) ama pyramid_
    regime_gate'in aksine (sadece zaten AÇIK bir pozisyon varken devreye
    girer, testleri doğal olarak etkilemez) bu kapı HER yeni pozisyon
    açılışına (geçmişi olmayan taze test sembolleri dahil) uygulanıyor —
    onlarca mevcut testin "fresh sembol -> pozisyon açılır" varsayımını
    bozar. Test ortamında bilerek kapalı; sadece bunu bizzat test eden
    testler (tests/test_decision_recorder.py) kendi scope'unda elle
    açıp kapatıyor."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(
            "signal_persistence_gate_enabled", "false", updated_by="conftest"
        )
    yield
