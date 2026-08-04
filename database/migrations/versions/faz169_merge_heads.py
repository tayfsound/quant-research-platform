"""Faz 182: merge the faz161 (TimescaleDB hypertable) and faz168 (main
chain) branches into one head. Verified against a genuinely empty scratch
database (docker run timescale/timescaledb, no data) before merging for
real — faz161's create_hypertable() calls fail on the local dev DB only
because it has real data (needs migrate_data=>true), NOT because the
migration itself is broken. On an empty DB (CI, a fresh production deploy)
the full chain applies cleanly, which this merge now makes the single,
un-branched path for.

Revision ID: faz169
Revises: faz161, faz168
Create Date: 2026-08-04
"""

revision = "faz169"
down_revision = ("faz161", "faz168")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
