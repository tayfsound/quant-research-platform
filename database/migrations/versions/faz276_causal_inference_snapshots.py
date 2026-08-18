"""Cognitive Core 4.0 — Causal Inference (Granger causality) haftalık anlık görüntüsü.

analytics/causal_inference.py::compute_granger_causality() (Faz 861-900)
zaten yazılmış ve testliydi ama hiçbir üretim kodu onu çağırmıyordu —
self_model.py'den sonraki, council'i etkilemeyen (gözlemsel) Grup B
adayı. Sistemdeki diğer TÜM ilişki sinyalleri (feature importance,
cross_symbol_correlation, correlation_breakdown, cross_asset_lead_lag)
korelasyon tabanlı — bu, standart bir "öngörücü nedensellik" testi
(Granger, 1969) ekliyor.

Revision ID: faz276
Revises: faz275
Create Date: 2026-08-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz276"
down_revision = "faz275"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "causal_inference_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_causal_inference_snapshots_created_at", "causal_inference_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_causal_inference_snapshots_created_at", table_name="causal_inference_snapshots")
    op.drop_table("causal_inference_snapshots")
