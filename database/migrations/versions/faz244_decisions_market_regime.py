"""Faz 244-246: add decisions.market_regime.

Predictive Risk (Regime-Switching Monte Carlo) rejime göre koşullanmış
GERÇEK kapanmış işlem getirisi dağılımına ihtiyaç duyuyor.
AgentPerformanceRecord.market_regime (Faz 268s) zaten bunu ajan bazında
tutuyor, ama decisions tablosunda (asıl işlemin kendisi, margin/leverage
dahil gerçek pnl%'i hesaplayabildiğimiz tek yer) hiç yoktu. services/
position_closer.py._extract_market_regime() zaten kapanış anında bunu
hesaplıyor — sadece decisions satırına da yazılması eklendi (geriye dönük
DOLDURULMUYOR, sadece bundan sonraki kapanışlar için — fail-closed, eski
kapanışlar regime=NULL kalır, uydurulmuş bir geçmiş atanmaz).

Revision ID: faz244
Revises: faz239
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from alembic import op

revision = "faz244"
down_revision = "faz239"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("market_regime", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "market_regime")
