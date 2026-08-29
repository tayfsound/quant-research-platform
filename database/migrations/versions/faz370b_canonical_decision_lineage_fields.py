"""Faz 370-devam: decisions.council_direction/council_confidence/
meta_decision/pre_fusion_confidence/final_ev/rejection_reason.

KRİTİK canlı bulgu (kullanıcı: "aynı kararın farklı katmanlarda farklı
karar olarak temsil edilmesi") — TRUMPUSDT örneği: debate_result.
final_direction=SHORT/0.429 (services/agent_debate.py'nin ham, benching/
weight-snapshot'tan habersiz kendi sentezi) iken persist edilen
decisions.direction=LONG, confidence=0.7939 (services/decision_fusion.py:
138'in belief_engine'in weight-snapshot-ağırlıklı belief'inden SONRA
yeniden kalibre edip ctx.decision.confidence'ı SESSİZCE ÜZERİNE YAZDIĞI
değer). İkisi de gerçek ama FARKLI aşamaların çıktısı; sorun bunların
ayrı ayrı, açıkça KAYDEDİLMEMİŞ olmasıydı — "hangi sayı hangi aşamadan
geldi" sorusu JSON arkeolojisi olmadan SQL ile cevaplanamıyordu.

Bu sütunlar zaten hesaplanan ara değerleri (services/decision_recorder.py,
engines/cognitive_pipeline.py::MetaStage) sadece ayrı, sorgulanabilir
alanlara çıkarıyor — hiçbir karar mantığı DEĞİŞMİYOR. SADECE bu migration'
dan SONRAKİ yeni kararlar için dolu, eski kayıtlarda NULL (geriye dönük
kurtarılamaz, additive/nullable).

Revision ID: faz370b
Revises: faz370
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op

revision = "faz370b"
down_revision = "faz370"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("council_direction", sa.String(), nullable=True))
    op.add_column("decisions", sa.Column("council_confidence", sa.Float(), nullable=True))
    op.add_column("decisions", sa.Column("meta_decision", sa.String(), nullable=True))
    op.add_column("decisions", sa.Column("pre_fusion_confidence", sa.Float(), nullable=True))
    op.add_column("decisions", sa.Column("final_ev", sa.Float(), nullable=True))
    op.add_column("decisions", sa.Column("rejection_reason", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "rejection_reason")
    op.drop_column("decisions", "final_ev")
    op.drop_column("decisions", "pre_fusion_confidence")
    op.drop_column("decisions", "meta_decision")
    op.drop_column("decisions", "council_confidence")
    op.drop_column("decisions", "council_direction")
