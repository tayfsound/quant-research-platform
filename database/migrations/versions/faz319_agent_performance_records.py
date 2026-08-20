"""Faz 319: AgentMemory JSON -> Postgres/TimescaleDB.

Kullanıcı isteği: agent_memory_history/agent_memory.json (60.519 kayıt,
tek dosya, fcntl kilitli) yerine gerçek bir Postgres tablosu — decisions/
weight_approvals ile AYNI TimescaleDB hypertable deseni (bkz. faz161).
Bu migration SADECE şemayı kurar (yeni, boş tablo) — gerçek JSON
geçmişinin taşınması ayrı, tek seferlik bir script ile yapılıyor (bkz.
scripts/migrate_agent_memory_to_postgres.py) çünkü o script'in girdisi
(yerel agent_memory.json dosyası) alembic'in kendisinin garanti edebileceği
bir şey değil — decisions tablosundaki geçmiş veri düzeltmeleriyle AYNI
ilke (faz279/280/281/317): migration şemayı kurar, ayrı bir adım gerçek
veriyi taşır/düzeltir.

id+timestamp bileşik birincil anahtar (faz161 ile AYNI TimescaleDB
zorunluluğu — hypertable'ın bölümleme sütunu birincil anahtarın parçası
olmalı). (namespace, agent_domain, timestamp) üzerinde ayrı bir indeks:
AgentMemory'nin TÜM sorguları (get_summary/get_filtered_records) önce
domain'e göre filtreleyip sonra timestamp'e göre sıralıyor.

`namespace` (varsayılan '') — testlerin eski AgentMemory(storage_path=...)
ile aldığı GERÇEK izolasyonun (her test kendi boş JSON dizinini kullanır,
diğer testlerin/paylaşımlı tablonun kaydından asla etkilenmez) Postgres'te
karşılığı: her benzersiz storage_path değeri artık benzersiz bir namespace
değeri oluyor, 38 test çağrı noktasının HİÇBİRİ değişmiyor. Gerçek/canlı
kayıtlar (AgentMemory() varsayılanı) namespace='' kullanıyor. Bu sütun
olmadan tüm testler AYNI paylaşımlı tabloyu okur/yazardı — pump_fade
rejim-gate testlerinde az önce doğrulanan AYNI kirlilik riski
(project_shared_test_state_bloat) burada da doğardı.

Revision ID: faz319
Revises: faz317
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz319"
down_revision = "faz317"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_performance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False, server_default=""),
        sa.Column("agent_domain", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("was_correct", sa.Boolean(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="live"),
        sa.Column("decision_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("r_multiple", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("failure_type", sa.Text(), nullable=False, server_default=""),
        sa.Column("symbol", sa.Text(), nullable=False, server_default=""),
        sa.Column("market_regime", sa.Text(), nullable=False, server_default=""),
        sa.Column("timeframe", sa.Text(), nullable=False, server_default=""),
        sa.Column("volatility", sa.Float(), nullable=False, server_default="0"),
        sa.Column("session", sa.Text(), nullable=False, server_default=""),
        sa.Column("spread", sa.Float(), nullable=False, server_default="0"),
        sa.Column("funding", sa.Float(), nullable=False, server_default="0"),
        sa.Column("leverage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("holding_time_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("news_type", sa.Text(), nullable=False, server_default=""),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_analysis", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id", "timestamp"),
    )
    op.create_index(
        "ix_agent_performance_records_namespace_domain_timestamp",
        "agent_performance_records",
        ["namespace", "agent_domain", "timestamp"],
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    op.execute(
        "SELECT create_hypertable('agent_performance_records', 'timestamp', "
        "if_not_exists => TRUE);"
    )


def downgrade():
    op.drop_table("agent_performance_records")
