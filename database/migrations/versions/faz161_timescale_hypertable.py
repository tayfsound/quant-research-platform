"""Faz 161: TimescaleDB hypertable for decisions.

Revision ID: faz161
Revises: 
Create Date: 2026-08-02
"""
from alembic import op

revision = 'faz161'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("SELECT create_hypertable('decisions', 'timestamp', if_not_exists => TRUE);")
    op.execute("SELECT create_hypertable('experiment_registry', 'timestamp', if_not_exists => TRUE);")
    op.execute("SELECT create_hypertable('weight_approvals', 'timestamp', if_not_exists => TRUE);")

def downgrade():
    pass
