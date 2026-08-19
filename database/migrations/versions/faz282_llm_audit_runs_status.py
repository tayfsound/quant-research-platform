"""Faz 282: llm_audit_runs'a başarısızlık status alanı ekle.

Kullanıcı bulgusu — gerçek olay (2026-08-19): "Araç çağrı döngüsü
sınırına ulaşıldı, net bir cevap üretemedim" gibi teknik başarısızlıklar
(zaman aşımı, API anahtarı eksik, araç döngü sınırı) önceden normal bir
denetim çalıştırması gibi kaydediliyordu — gerçek bir bulgu ya da dürüst
"sorun yok" cevabıyla ayırt edilemiyordu. llm_reasoner.py::ask_with_tools
artık "ok"/"no_api_key"/"timeout"/"tool_loop_limit"/"error" döndürüyor,
bu sütun onu saklıyor.

Revision ID: faz282
Revises: faz281
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op

revision = "faz282"
down_revision = "faz281"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_audit_runs",
        sa.Column("status", sa.Text(), nullable=False, server_default="ok"),
    )


def downgrade() -> None:
    op.drop_column("llm_audit_runs", "status")
