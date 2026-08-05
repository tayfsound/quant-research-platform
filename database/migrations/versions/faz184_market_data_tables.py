"""Faz 184: Market Data Service — market_snapshots (OHLCV) + market_trades tables.

Proje sahibiyle netleşen gerçek bulgu: `exchange_gateway/binance/adapter.py`
(REST), `exchange_gateway/binance/live_feed.py` (WS), `market_data/ingestion/
pipeline.py` hepsi gerçek ve çalışır durumdaydı ama hiçbir yerden
çağrılmıyordu; çağrılsalar bile `events/message_bus.py` in-memory'di, hiçbir
kalıcı subscriber yoktu — veri publish edilir edilmez kaybolurdu.
`contracts/market_data.py::MarketSnapshot` da tam olarak bu iş için
tasarlanmış ama hiç kullanılmayan bir şemaydı. Bu migration o kalıcı
katmanı ekliyor.

market_snapshots: doğal composite key (exchange, symbol, resolution, time) —
TimescaleDB'nin hypertable şartı zaten time'ı içeriyor, ayrı bir id/surrogate
key gerekmiyor; aynı bar tekrar çekilirse (henüz kapanmamış mum) UPSERT ile
güncellenir, duplicate satır oluşmaz.

market_trades: id + time composite PK (episodes/decisions ile aynı desen) —
trade'lerin doğal bir unique key'i yok (aynı sembol+fiyat+zaman birden fazla
gerçek trade'de tekrar edebilir), bu yüzden surrogate id kullanılıyor.

Revision ID: faz184
Revises: faz172
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz184"
down_revision = "faz172"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Yan bulgu (aynı "ghost table" deseni risk_limits/weight_approvals'ta
    # da görülmüştü): local dev DB'de zaten bir `market_snapshots` tablosu
    # vardı — repo geçmişinde bunu tanımlayan hiçbir model yok, şeması
    # (NUMERIC kolonlar, farklı varchar uzunlukları) burada tanımlanandan
    # ufak farklarla neredeyse birebir aynı, tamamen boş (0 satır), FK yok.
    # Güvenle drop edilip gerçek şemayla (ve hypertable olarak) yeniden
    # oluşturuluyor.
    op.execute("DROP TABLE IF EXISTS market_snapshots")
    op.create_table(
        "market_snapshots",
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("resolution", sa.String(8), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("source_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("quality", sa.String(16), nullable=False, server_default="valid"),
        sa.PrimaryKeyConstraint("exchange", "symbol", "resolution", "time"),
    )
    op.execute("SELECT create_hypertable('market_snapshots', 'time', if_not_exists => TRUE);")

    op.create_table(
        "market_trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("side", sa.String(8), nullable=True),
        sa.PrimaryKeyConstraint("id", "time"),
    )
    op.execute("SELECT create_hypertable('market_trades', 'time', if_not_exists => TRUE);")
    op.create_index(
        "ix_market_trades_symbol_time", "market_trades", ["symbol", "time"]
    )


def downgrade() -> None:
    op.drop_index("ix_market_trades_symbol_time", table_name="market_trades")
    op.drop_table("market_trades")
    op.drop_table("market_snapshots")
