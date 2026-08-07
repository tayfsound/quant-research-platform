"""Faz 240: MockOHLCVAdapter sızıntısından (Faz 239) kirlenen işlemleri
istatistiklerden dürüstçe hariç tut — silmeden.

Kök neden (Faz 239'da düzeltildi): MARKET_DATA_FALLBACK_TO_MOCK=True iken
gerçek Binance isteği HERHANGİ bir sebeple başarısız olursa BinanceProvider
sessizce MockOHLCVAdapter'a (varsayılan base_price=$50,000, SEMBOLDEN
BAĞIMSIZ) düşüyordu. Bu, entry_price VEYA exit_price'ın (bazen ikisinin de,
farklı zamanlarda) gerçek sembolün fiyat ölçeğinden kopuk, BTC-ölçekli bir
mock değer olmasına yol açtı — ör. ADAUSDT (gerçek fiyat ~$0.20) için
exit_price=$49,855.91, ya da entry_price=$32,376 gibi.

Faz 238'in notional-eşiği (entry_price*quantity > $10,000) bu deseni
YAKALAMIYOR: quantity de gerçek pozisyon büyüklüğü hesabından geldiği için
(fake fiyata göre boyutlandırılmamış), toplam notional küçük kalabiliyor
(ör. ADAUSDT örneğinde entry notional sadece ~$40). Burada farklı bir
heuristik kullanılıyor: aynı sembol için entry_price ile exit_price
arasında 20 kattan fazla bir ölçek sıçraması — hiçbir gerçek piyasa
hareketi (major kripto dahil) bir pozisyonun ömrü içinde böyle bir
sıçrama yapamaz, bu sadece mock-fallback sızıntısının imzasıdır.

Class 2 prensibi (Faz 238'de de uygulanan): satırlar SİLİNMİYOR, sadece
excluded_from_stats=true işaretleniyor — ham veri bağımsız doğrulama için
tabloda kalıyor.

Revision ID: faz240
Revises: faz238
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op

revision = "faz240"
down_revision = "faz238"
branch_labels = None
depends_on = None

# Gerçek hiçbir varlık (major kripto, hisse, endeks, altın-destekli token)
# bir pozisyonun ömrü içinde 20 kattan fazla bir fiyat sıçraması yapmaz —
# bu sadece sembolden bağımsız ~$50,000 mock fallback'in gerçek fiyatla
# karışmasının imzasıdır (bkz. config/settings.py::MARKET_DATA_FALLBACK_TO_MOCK).
_IMPLAUSIBLE_PRICE_RATIO = 20


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE decisions SET excluded_from_stats = true "
            "WHERE status = 'closed' AND exit_price IS NOT NULL "
            "AND entry_price IS NOT NULL AND entry_price > 0 AND exit_price > 0 "
            "AND (exit_price / entry_price > :ratio OR entry_price / exit_price > :ratio)"
        ).bindparams(ratio=_IMPLAUSIBLE_PRICE_RATIO)
    )


def downgrade() -> None:
    # Faz 238'in eşiğiyle çakışabileceği için burada koşulsuz geri almıyoruz
    # (o zaten kendi işaretlediklerini korur) — bu migration'ın kendi
    # işaretlediklerini geri almak güvenli değil çünkü hangi satırların
    # SADECE bu migration tarafından işaretlendiği ayrıca izlenmiyor.
    pass
