"""Faz 182: create episodes, beliefs, observations, lessons tables.

f8fa21f0e94a_reconcile_initial_memory_schema.py already documented this
exact gap in its own docstring: "Tables already exist from legacy
initialization... No DDL changes applied." — an honest acknowledgment that
was never actually followed up with real DDL. Found the same way as the
weight_approvals/experiment_registry gaps (faz165_base, faz166): running
the full migration chain against a genuinely fresh DB (this time a real
Kubernetes pod's Postgres, not just a scratch container) — the API crashed
on startup because MemoryConsolidator eagerly queries `episodes` at
construction time and the table didn't exist.

episodes/observations already have a composite (id, created_at) primary
key on the real DB and are already TimescaleDB hypertables (created via
0001/0002, which is why grepping for the table name literally didn't find
them) — reproduced here. beliefs/lessons are plain tables.

Revision ID: faz171
Revises: faz169
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "faz171"
down_revision = "faz169"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        "episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("observation", postgresql.JSONB(), nullable=True),
        sa.Column("binding_expression", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("outcome", postgresql.JSONB(), nullable=True),
        sa.Column("lesson", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.PrimaryKeyConstraint("id", "created_at"),
    )
    op.execute("SELECT create_hypertable('episodes', 'created_at', if_not_exists => TRUE);")

    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("observation_type", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", "created_at"),
    )
    op.execute("SELECT create_hypertable('observations', 'created_at', if_not_exists => TRUE);")

    op.create_table(
        "beliefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("expression", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lesson_text", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("lessons")
    op.drop_table("beliefs")
    op.drop_table("observations")
    op.drop_table("episodes")
