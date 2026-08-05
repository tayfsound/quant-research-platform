"""Faz 172 (gap #15): create risk_limits table.

`ctx.risk.limits`'i üretimde hiçbir kod yolu doldurmuyordu — `POST /cognitive/run`
boş bir context ile `engine.run()` çağırıyor, `RiskEngine.execute()` her zaman
`MISSING_LIMIT` ile reddediyordu. `RiskEngine`'in gerçekte beklediği arayüz
(`.value` + `.verify(secret) -> bool`) zaten `contracts/contexts/risk.py`'daki
`RiskLimitEntry`'de vardı (RiskContext.limits'in gerçek pydantic tipi), ama
onu DB'ye kalıcı, insan-onaylı (Faz 160: "insan onayı zorunluluğu") olarak
yazan bir tablo/repository yoktu. Bu tablo o eksik parçayı kapatıyor.

Class 2 (silme/update yok, sadece save/get_active) — weight_approvals ve
experiment_registry ile aynı desen. Yeni bir signed limit her zaman en son
aktif limit olur (created_at DESC ile seçilir), eskisi geçmiş olarak kalır.

Yan bulgu (bu migration'ı gerçek local dev DB'ye karşı çalıştırırken
bulundu — aynı "ghost table" deseni weight_approvals/episodes'ta da
görülmüştü): local DB'de zaten bir `risk_limits` tablosu vardı ama repo
geçmişinde (`git log --all`) bu tabloyu tanımlayan hiçbir SQLAlchemy modeli
yok — muhtemelen çok daha eski, artık kod tabanında izi kalmamış bir
denemeden kalma. Şeması da farklı (id/scope/limit_type/value/signed_hash/
effective_at — `created_by`/`created_at` yok) ve tamamen boş (0 satır),
hiçbir foreign key yok. Bu migration onu güvenle drop edip gerçek şemayla
yeniden oluşturuyor.

Revision ID: faz172
Revises: faz171
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz172"
down_revision = "faz171"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS risk_limits")
    op.create_table(
        "risk_limits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(64), nullable=False, server_default="global"),
        sa.Column("limit_type", sa.String(32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_risk_limits_scope_type_created",
        "risk_limits",
        ["scope", "limit_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_risk_limits_scope_type_created", table_name="risk_limits")
    op.drop_table("risk_limits")
