"""Faz 189: experiments tablosu — gerçek bulgu (ghost table).

database/repositories/experiment_repository.py (curiosity engine'in
ExperimentProposal'ları için, faz166'daki ayrı `experiment_registry`
tablosuyla karıştırılmamalı) hiçbir migration'da tanımlı olmayan bir
tabloya INSERT/UPDATE/SELECT yapıyordu — gerçek dev DB'de tablo elle/dışarıdan
var edilmiş olduğu için hiç fark edilmemişti. İzole, sadece migration'larla
kurulan bir test veritabanında `relation "experiments" does not exist` ile
patlayarak ortaya çıktı. Şema, gerçek dev DB'nin information_schema'sından
birebir alındı.

Revision ID: faz189
Revises: faz188
Create Date: 2026-08-05
"""
from alembic import op

revision = "faz189"
down_revision = "faz188"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: gerçek dev DB'de bu tablo migration dışı zaten var
    # (ghost table) — hem oradaki mevcut veriyi koruyarak hem de tamamen
    # taze bir DB'de aynı migration'ın çalışmasını sağlayan tek yol.
    op.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id UUID PRIMARY KEY,
            curiosity_id UUID,
            hypothesis TEXT,
            test_expression TEXT,
            estimated_value DOUBLE PRECISION DEFAULT 0.0,
            status TEXT DEFAULT 'proposed',
            result JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.drop_table("experiments")
