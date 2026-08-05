"""Testlerin gerçek dev/dashboard veritabanına (quantdb) hiç dokunmaması için
ayrı bir test veritabanı (quantdb_test) — kök neden bulgusu: testler her
çalıştığında SessionFactory üzerinden gerçek dev DB'ye yazıyordu, bu da
dashboard'da (Experiments listesi, Transactions sayfası, app_settings) rastgele
test sembolleri ve "%100 kazanma oranı" gibi anlamsız veri olarak görünüyordu
— aynı sorun üç ayrı yerde tekrar tekrar yaşandı.

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
