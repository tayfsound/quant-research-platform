"""Faz 250: add decisions.experiment_bucket.

Live A/B Testing Framework — bu karar bir deneyin (ör.
"multi_timeframe_cascade_v1") control/treatment kovasından mı geldi.
Deneysel olmayan (ezici çoğunluk) kararlarda NULL kalır. Faz 233'te
kaldırılan experiment_registry tablosunun AKSİNE (write-only, hiç
okunmayan bir denetim kaydıydı) bu sütun gerçekten okunuyor — bkz.
services/ab_testing.py::evaluate_experiment.

Revision ID: faz250
Revises: faz249
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from alembic import op

revision = "faz250"
down_revision = "faz249"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("experiment_bucket", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "experiment_bucket")
