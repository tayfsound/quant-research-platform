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


# Faz 370-devam — kullanıcı kararı (2026-08-29, "ben kırık test kabul
# etmiyorum hiçbir şekilde"): Faz 363'ün satır-bazlı, iki kalıba özel
# purge'ü ("pump_fade_v1"/"basis_arb_v1"/testnet-open) SADECE decisions
# tablosunu ve SADECE o iki bilinen kirlilik türünü kapsıyordu. Gerçek
# ölçüm (2026-08-29): quantdb_test'te agent_performance_records 5093
# satır/156 namespace (3 GÜNDE, Faz 319'un Postgres'e taşımasından beri
# HİÇ temizlenmemiş — her pytest çalışması kendi benzersiz namespace'ini
# alıyor ama ESKİ namespace'ler sonsuza dek birikiyor), decisions 1853
# satır (11 günde, sadece iki kalıp temizleniyordu, DİĞER her testin
# try/finally'i atlanmış/başarısız olmuş satırları hâlâ birikiyordu).
# Bu SADECE iki tabloya özel değil — bu oturumda eklenen her yeni haftalık
# rapor tablosu (feature_relationship_reports, agent_pairwise_ablation_
# snapshots, vb.) da AYNI şekilde, HİÇ silinmeden birikiyor.
#
# Çözüm: kalıp-bazlı iki satır yerine, tablo-seviyesinde KAPSAMLI bir
# TRUNCATE — quantdb_test'in KENDİSİ zaten yalıtılmış (gerçek quantdb'den
# TAMAMEN ayrı bir Postgres veritabanı, bu dosyanın en üstünde ortam
# değişkenleriyle garanti ediliyor), yani içindeki HER satır test
# çalıştırmalarından geliyor — GERÇEK üretim verisi asla buraya yazmıyor.
# Sadece 5 tablo KORUNUYOR (migration durumu + config/auth seed verisi —
# bunlar boşsa sistem SESSİZCE bozulur, bkz. risk_limits olayı):
# alembic_version, app_settings, risk_limits, users, api_keys. Geri kalan
# HER public şema tablosu (yeni eklenenler DAHİL — allowlist değil
# denylist, gelecekte unutulmaya karşı otomatik kapsıyor) session
# BAŞINDA (henüz hiçbir test çalışmadan) temizleniyor — bu andaki HER
# satır mantık gereği önceki, yarım kalmış oturumlardan kalmış olabilir,
# güvenle silinir.
_PROTECTED_TABLES = frozenset({"alembic_version", "app_settings", "risk_limits", "users", "api_keys"})


@pytest.fixture(scope="session", autouse=True)
def _purge_all_test_generated_tables_at_session_start():
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        table_names = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
            ).fetchall()
            if row[0] not in _PROTECTED_TABLES
        ]
        if table_names:
            quoted = ", ".join(f'"{t}"' for t in table_names)
            session.execute(text(f"TRUNCATE TABLE {quoted} CASCADE"))
        session.commit()
    yield


