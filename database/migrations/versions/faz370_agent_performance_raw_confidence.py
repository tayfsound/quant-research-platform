"""Faz 370: agent_performance_records.raw_confidence.

GPT dış rapor önerisi (kullanıcı isteği, iş sırasının 3. maddesi):
"Brier score'u out-of-sample hesaplıyor musunuz? Aynı veri hem
confidence üretmek hem Brier ölçmek için kullanılıyorsa şişmiş
olabilir." Gerçek bulgu: confidence her zaman KALİBRE EDİLMİŞ değerdi
— ham (kalibrasyon öncesi) değer hiçbir yerde saklanmıyordu. Bu sütun
kalibrasyon ÖNCESİ ham değeri koruyor (bkz. contracts/agent.py::
AgentOpinion.raw_confidence, services/council_orchestrator.py:140) —
SADECE bu migration'dan SONRAKİ yeni kararlar için dolu, eski kayıtlarda
NULL (geriye dönük kurtarılamaz, additive/nullable).

Revision ID: faz370
Revises: faz369
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op

revision = "faz370"
down_revision = "faz369"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_performance_records",
        sa.Column("raw_confidence", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_performance_records", "raw_confidence")
