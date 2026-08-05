"""Faz 188: app_settings — kullanıcının kendi risk/mod ayarlarını gerçekten
kontrol edebilmesi için tek gerçek kaynak.

Gerçek bulgu: tek risk kuralı (max_position_size) bir ADMIN'in POST
/risk-limits'e elle çağrı yapmasıyla set ediliyordu, dashboard'da hiçbir
arayüzü yoktu; "kaç işlem aynı anda açık olabilir" veya "kasanın max
%kaçı kullanılabilir" gibi bir kural kodda hiç yoktu. Bu tablo + api/rest/
settings.py bunu kapatıyor: trading_mode (test/live), max_concurrent_positions,
max_capital_pct, trade_horizon (kısa/orta/uzun vadeli tutma süresi).

Revision ID: faz188
Revises: faz187
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op

revision = "faz188"
down_revision = "faz187"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(256), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
