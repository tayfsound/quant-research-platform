"""Faz 161: TimescaleDB hypertable for decisions.

Faz 182 fix: this originally failed two different ways. Locally it failed
with "table is not empty" (real dev data, needs migrate_data=>true — a
data-migration call this migration doesn't make for anyone). Verified
against a genuinely empty scratch DB, it then failed a SECOND, deeper way:
TimescaleDB requires the partitioning column to be part of any unique
index, including the primary key — and all three tables had a single-column
`id` primary key, not `(id, timestamp)`. That's the actual root cause;
"non-empty table" was just the first error encountered, not the only one.
Fixed here by widening each PK to include `timestamp` before hypertabling —
the standard, documented pattern for combining a UUID identity column with
a TimescaleDB hypertable. `id` stays globally unique via uuid4() at the
application layer, so this doesn't weaken uniqueness in practice.

Revision ID: faz161
Revises:
Create Date: 2026-08-02
"""
from alembic import op

revision = 'faz161'
down_revision = "f8fa21f0e94a"
branch_labels = None
depends_on = None

_TABLES = ["decisions", "experiment_registry", "weight_approvals"]


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS timescaledb;')

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {table}_pkey;")
        op.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (id, timestamp);")
        op.execute(f"SELECT create_hypertable('{table}', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);")


def downgrade():
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {table}_pkey;")
        op.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (id);")
