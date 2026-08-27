"""Faz 366: strategy_gate_approvals — analytics/strategy_hypothesis_
scanner.py'nin bulduğu (strateji × rejim) adaylarının insan onayı
kuyruğu. weight_approvals (Faz 160) ile AYNI desen: propose → pending →
approve/reject, hiçbir aday insan onayı olmadan canlı bir gate'e
bağlanmıyor.

Kullanıcı isteği (2026-08-26): "ürettiği strateji insan onayına sunulur
böyle bir yapı ayarlamıştık" — WeightApproval TAM olarak bunu yapıyordu
ama SADECE ajan ağırlıkları için; strategy_hypothesis_scanner'ın
adayları için eşdeğer bir onay kuyruğu hiç yoktu, bu eksiği kapatıyor.

Revision ID: faz366
Revises: faz365
Create Date: 2026-08-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "faz366"
down_revision = "faz365"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_gate_approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("market_regime", sa.String(64), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("rest_win_rate", sa.Float(), nullable=False),
        sa.Column("delta_vs_rest", sa.Float(), nullable=False),
        sa.Column("p_value", sa.Float(), nullable=False),
        sa.Column("replicated_out_of_sample", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("approved_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_strategy_gate_approvals_strategy_regime_status",
        "strategy_gate_approvals", ["strategy", "market_regime", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_gate_approvals_strategy_regime_status", table_name="strategy_gate_approvals")
    op.drop_table("strategy_gate_approvals")
