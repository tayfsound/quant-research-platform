"""Faz 375: decisions.mtf_direction/mtf_confidence — canonical decision
lineage'in eksik kalan parçası (0.5266/multi-timeframe cascade
instrumentation).

Faz 370-devam (aynı gün, daha erken) council_direction/council_confidence
(debate_result'ın ham oyu) ve meta_decision/pre_fusion_confidence
(MetaStage'in ACT/REDUCE/WAIT kararı) sütunlarını eklemişti — ama
services/orchestrator.py::propose_multi_timeframe()'in "timeframe_belief"
(15m/4h/medium-term kırılımı + Bayesian birleştirilmiş sonuç) kaydı hiçbir
zaman decisions.agent_contributions'a persist EDİLMİYORDU (hesaplanıyor,
gerçekten confidence'ı etkiliyor, ama gözlemlenemiyordu — "0.5266 aynı
confidence" gizeminin araştırılamamasının doğrudan sebebi). Bu, kullanıcının
kendi tasarladığı canonical decision şemasının ("mtf_direction/mtf_
confidence") tamamlanması.

Revision ID: faz375
Revises: faz370b
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op

revision = "faz375"
down_revision = "faz370b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("mtf_direction", sa.String(), nullable=True))
    op.add_column("decisions", sa.Column("mtf_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "mtf_confidence")
    op.drop_column("decisions", "mtf_direction")
