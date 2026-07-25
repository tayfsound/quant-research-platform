"""TimescaleDB hypertables, compression & retention policies

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # -- Class 1 --
    op.create_table(
        'market_snapshots',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('exchange', sa.String(20), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('resolution', sa.String(5), nullable=False),
        sa.Column('open', sa.Numeric(), nullable=False),
        sa.Column('high', sa.Numeric(), nullable=False),
        sa.Column('low', sa.Numeric(), nullable=False),
        sa.Column('close', sa.Numeric(), nullable=False),
        sa.Column('volume', sa.Numeric(), nullable=False),
        sa.Column('source_version', sa.String(20), nullable=False),
        sa.Column('quality', sa.String(10), server_default='valid'),
    )
    op.execute("SELECT create_hypertable('market_snapshots', 'time')")
    op.execute("ALTER TABLE market_snapshots SET (timescaledb.compress)")
    op.execute("SELECT add_compression_policy('market_snapshots', INTERVAL '30 days', if_not_exists => true)")

    op.create_table(
        'orderbook_snapshots',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('exchange', sa.String(20), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('bids', postgresql.JSONB(), nullable=False),
        sa.Column('asks', postgresql.JSONB(), nullable=False),
        sa.Column('source_version', sa.String(20), nullable=False),
    )
    op.execute("SELECT create_hypertable('orderbook_snapshots', 'time')")
    op.execute("ALTER TABLE orderbook_snapshots SET (timescaledb.compress)")
    op.execute("SELECT add_compression_policy('orderbook_snapshots', INTERVAL '30 days', if_not_exists => true)")
    op.execute("SELECT add_retention_policy('orderbook_snapshots', INTERVAL '180 days', if_not_exists => true)")

    # Continuous aggregate — WITH NO DATA transaction içinde çalışır
    op.execute("""
        CREATE MATERIALIZED VIEW orderbook_1m
        WITH (timescaledb.continuous) AS
        SELECT time_bucket('1 minute', time) AS bucket,
               exchange, symbol,
               avg((bids->0->>0)::numeric) AS avg_best_bid,
               avg((asks->0->>0)::numeric) AS avg_best_ask
        FROM orderbook_snapshots
        GROUP BY bucket, exchange, symbol
        WITH NO DATA
    """)

    # -- Class 2 --
    op.create_table(
        'predictions',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_version', sa.String(50), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('direction', sa.SmallInteger(), nullable=False),
        sa.Column('confidence', sa.Numeric(), nullable=False),
        sa.Column('raw_output', postgresql.JSONB(), server_default='{}'),
        sa.Column('snapshot_ref', sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.execute("SELECT create_hypertable('predictions', 'time')")

    op.create_table(
        'simulated_fills',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(5), nullable=False),
        sa.Column('quantity', sa.Numeric(), nullable=False),
        sa.Column('price', sa.Numeric(), nullable=False),
        sa.Column('fee', sa.Numeric(), nullable=False),
        sa.Column('slippage', sa.Numeric(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('order_type', sa.String(20), nullable=False),
        sa.Column('leverage', sa.Numeric(), server_default='1'),
        sa.Column('liquidation', sa.Boolean(), server_default='false'),
    )
    op.execute("SELECT create_hypertable('simulated_fills', 'time')")

    op.create_table(
        'feature_vectors',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('feature_set_version', sa.String(50), nullable=False),
        sa.Column('values', postgresql.JSONB(), nullable=False),
    )
    op.execute("SELECT create_hypertable('feature_vectors', 'time')")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS orderbook_1m CASCADE")
    op.drop_table('feature_vectors')
    op.drop_table('simulated_fills')
    op.drop_table('predictions')
    op.drop_table('orderbook_snapshots')
    op.drop_table('market_snapshots')
