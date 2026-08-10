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

os.environ["DATABASE_URL_SYNC"] = "postgresql+psycopg2://quant:quantpass@localhost:5432/quantdb_test"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://quant:quantpass@localhost:5432/quantdb_test"
os.environ["TIMESCALE_URL"] = "postgresql+asyncpg://quant:quantpass@localhost:5432/quantdb_test"
os.environ["AGENT_MEMORY_STORAGE_PATH"] = "tmp_test_memory/agent_memory_history"
os.environ["AGENT_CONFIDENCE_MODEL_STORAGE_PATH"] = "tmp_test_memory/confidence_model_history"
