"""Faz 284: backtest_runs tablosunu kaldır — backtest sistemi tamamen kaldırıldı.

Kullanıcı kararı (2026-08-19): backtest sonuçlarının (source="backtest"
etiketiyle) AgentMemory'ye yazıldığı doğrulandı, ama Faz 268i'de bilinçli
olarak canlı ("agent_memory_history/") dosyasından TAMAMEN AYRI, izole bir
dosyaya (backtest_agent_memory_history/) yönlendirilmişti — hiçbir üretim
kodu (WeightOptimizer, SourceReliabilityAgent, haftalık ajan ayarlama
görevi) bu izole dosyayı okumuyor. Yani backtest, karar mekanizmasına HİÇ
katkı sağlamıyordu, sadece celery kaynağını tüketen (49 sembollük bir
çalıştırma saatlerce sürdü, gerçek trading task'larıyla yarıştı) ölü bir
alt sistemdi. Kullanıcı: "Karar mekanizmasını etkilemedikten sonra buradan
gelen datayı ne yapayım... Kaldıralım backtest'e veda edelim."

backtest_runs tablosunu okuyan hiçbir üretim kodu kalmadı (api/rest/
backtest.py, database/repositories/backtest_run_repository.py, contracts/
backtest_run.py hepsi bu commit'te silindi) — tablo genuinely artık
erişilemez, tutmanın hiçbir anlamı yok.

Revision ID: faz284
Revises: faz283
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz284"
down_revision = "faz283"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("backtest_runs")


def downgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("symbols", postgresql.JSON(), nullable=False),
        sa.Column("git_sha", sa.String(40), nullable=False),
        sa.Column("weight_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fee", sa.Float(), nullable=False),
        sa.Column("lookback", sa.Integer(), nullable=False),
        sa.Column("num_bars", sa.Integer(), nullable=False),
        sa.Column("total_pnl", sa.Float(), nullable=False),
        sa.Column("per_symbol_pnl", postgresql.JSON(), nullable=False),
        sa.Column("metrics", postgresql.JSON(), nullable=False),
        sa.Column("equity_curve", postgresql.JSON(), nullable=False),
    )
