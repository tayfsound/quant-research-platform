"""Faz 461: market_snapshots'a Binance'in ZATEN GÖNDERDİĞİ order-flow alanları.

Kullanıcı bulgusu (2026-09-09): "Bu sinyalleri neden gerçekten almıyoruz,
BinanceAPI'den çekebiliyor olmamız lazım... Sinyalleri yok etmek yerine
orijinal sinyalleri çekip versek sisteme daha iyi olmaz mı?"

Doğrulandı: Binance'in /api/v3/klines'ı her mum için 12 alan döndürüyor,
`exchange_gateway/binance/adapter.py::_parse_klines()` bunların yalnızca
6'sını (d[0]-d[5]) alıp GERİ KALANINI ATIYORDU. Yani bugüne kadar
çektiğimiz her mumda -- milyonlarcasında -- şu veriler AYNI HTTP
cevabının içinde geldi ve çöpe gitti:

    d[7]  quote_volume    -- kote para biriminde hacim
    d[8]  trades          -- mumdaki işlem sayısı
    d[9]  taker_buy_base  -- AGRESİF ALIŞ hacmi (gerçek order flow)
    d[10] taker_buy_quote -- aynısının kote cinsinden hâli

`taker_buy_base / volume` = o mumdaki agresif alış oranı; literatürdeki
order flow imbalance'ın (Cont/Kukanov/Stoikov; Kolm/Turiel/Westray 2023)
mum seviyesindeki en basit hâli.

İNŞA ETMEDEN ÖNCE ÖLÇÜLDÜ (12 sembol, 33.750 pencere, canlı Binance):
  ham hâliyle (tek mum -> 1sa sonrası)         separation −0,023  (değersiz)
  15dk toplulaştırılmış + 120dk normalize:
      15 dakika ufku, üst %25 vs alt %25       separation −0,045
      15 dakika ufku, üst %10 vs alt %10       separation −0,075  (uçlarda güçleniyor)
      1 saat ufku                              separation −0,002  (yok)

Yani veri GERÇEK bilgi taşıyor ama (a) pencereleme+normalizasyon şart,
(b) etkin ufku KISA (15dk) -- Kolm/Turiel/Westray'in "etkin ufuk ≈ iki
ortalama fiyat değişimi" bulgusuyla birebir uyumlu, (c) işareti yine
ortalamaya-dönüş yönünde (Faz 460'ın genel örüntüsü).

Sütunlar nullable: GEÇMİŞ satırlar bu alanları içermiyor ve uydurma bir
değerle doldurulmayacak (fail-closed). Yeni mumlardan itibaren dolacak.

Revision ID: faz461
Revises: faz440
Create Date: 2026-09-09
"""
import sqlalchemy as sa
from alembic import op

revision = "faz461"
down_revision = "faz440"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_snapshots", sa.Column("quote_volume", sa.Float(), nullable=True))
    op.add_column("market_snapshots", sa.Column("trades", sa.Integer(), nullable=True))
    op.add_column("market_snapshots", sa.Column("taker_buy_base", sa.Float(), nullable=True))
    op.add_column("market_snapshots", sa.Column("taker_buy_quote", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("market_snapshots", "taker_buy_quote")
    op.drop_column("market_snapshots", "taker_buy_base")
    op.drop_column("market_snapshots", "trades")
    op.drop_column("market_snapshots", "quote_volume")
