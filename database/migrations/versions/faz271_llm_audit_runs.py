"""Faz 271: LLM periyodik sistem denetimi geçmişi.

Kullanıcı isteği — "LLM'i her pozisyonda devreye sokmak lazım... onay
panelimi anlamlı kılmak için." Gerçek zamanlı, her karar için LLM'e
sormak yerine (gecikme+maliyet), LLM düzenli aralıklarla (bkz.
services/llm_system_audit.py, services/celery_app.py beat schedule)
SON dönemdeki TÜM kararları toplu gözden geçiriyor, elindeki gerçek
araçlarla (get_recent_performance_summary, classify_recent_stop_loss_
failures, read_source_file, search_code) mantık hatası/sistemik sorun
arıyor, bulursa code_change_proposals kuyruğuna öneri düşürüyor (faz270).

Bu tablo o denetimlerin GEÇMİŞİNİ tutuyor — "hiçbir şey bulamadım" da
dahil, çünkü kullanıcının "LLM çalışıyor mu, gerçekten bakıyor mu"
sorusuna şeffaf bir cevap bu geçmiş olmadan mümkün değil (proposal
oluşmadığında hiçbir iz kalmazdı).

Revision ID: faz271
Revises: faz270
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz271"
down_revision = "faz270"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_audit_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=False),
        sa.Column("proposals_created", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_llm_audit_runs_created_at", "llm_audit_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_audit_runs_created_at", table_name="llm_audit_runs")
    op.drop_table("llm_audit_runs")
