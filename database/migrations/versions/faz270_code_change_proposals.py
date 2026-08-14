"""Faz 270: LLM'in kod-değişikliği önerileri için onay kuyruğu tablosu.

Kullanıcı isteği — bugüne kadar defalarca ertelenen bir iş: "LLM in
herşeyi görüp takip edebiliyor olması lazım, gerekirse kod üzerinde
apdate için onayıma düzeltmeler gönderecekti... En başta llm deepseek
entegre ederek yükseltmemizin amacı zaten bu." Bu tablo, o vizyonun
GÜVENLİ yarısı — LLM (Respond sekmesi, artık gerçek kod/DB araçlarına
sahip NvidiaDecisionCritic.ask_with_tools()) bir kod değişikliği
ÖNERDİĞİNDE, bunu DOĞRUDAN diske yazmak yerine burada "pending" olarak
biriktirir. Hiçbir satır, insan onayı olmadan gerçek bir dosyaya
uygulanmıyor — "teşhis + öneri kuyruğu evet, otomatik self-deploy hayır"
ilkesinin doğrudan karşılığı (bu oturumda daha önce belirlenen standing
instruction).

Revision ID: faz270
Revises: faz268ab
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz270"
down_revision = "faz268ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "code_change_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        # pending | approved | rejected — Class 2: satırlar SİLİNMİYOR,
        # sadece durumu değişiyor (backtest_runs/weight_approvals ile AYNI
        # kalıcı-denetim ilkesi).
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
    )
    op.create_index("ix_code_change_proposals_status", "code_change_proposals", ["status"])
    op.create_index("ix_code_change_proposals_created_at", "code_change_proposals", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_code_change_proposals_created_at", table_name="code_change_proposals")
    op.drop_index("ix_code_change_proposals_status", table_name="code_change_proposals")
    op.drop_table("code_change_proposals")
