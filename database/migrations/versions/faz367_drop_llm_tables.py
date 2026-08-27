"""Faz 367: LLM sistemi tamamen kaldırıldı — kullanıcı kararı (2026-08-27):
"LLM'i kaldıracağız, 5 gündür zaten çalışmıyor, çalışsa da işe yarar bir
tavsiyede bulunduğu hiç olmadı. Mimariyi şişiriyor gereksiz, bizim
ajanlar daha iyisini yapabilir." Gerçek doğrulama: llm_audit_runs'ta
30/30 çalıştırmada proposals_created=0, son gerçek çalıştırma 5 gün
önce hata ile durmuş (`[Errno 2] No such file or directory`), canlı
test edilen NVIDIA API çağrısı ReadTimeout ile başarısız oldu.
sentiment_agent zaten daha önce (Faz 269-sonrası) 9 oy-veren ajan
listesinden çıkarılmıştı — refresh_llm_news_sentiment_task'ın ürettiği
veriyi tüketen hiçbir şey kalmamıştı (ölü kod).

llm_audit_runs (Faz 271) ve code_change_proposals (Faz 270) tabloları
— ikisi de SADECE bu sistemin kullandığı, başka hiçbir modülün
paylaşmadığı tablolardı, doğrulandı.

Revision ID: faz367
Revises: faz366
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz367"
down_revision = "faz366"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_llm_audit_runs_created_at", table_name="llm_audit_runs")
    op.drop_table("llm_audit_runs")
    op.drop_table("code_change_proposals")


def downgrade() -> None:
    op.create_table(
        "code_change_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
    )
    op.create_table(
        "llm_audit_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=False),
        sa.Column("proposals_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
    )
    op.create_index("ix_llm_audit_runs_created_at", "llm_audit_runs", ["created_at"])
