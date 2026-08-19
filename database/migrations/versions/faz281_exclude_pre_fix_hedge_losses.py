"""Faz 281: pairs_trader (Hedge) bacak-boyutu birim bug'ından (dolar
yerine ham varlık birimi, 2026-08-16 18:41 UTC+2'de düzeltildi) önce
kapanmış hedge işlemlerini istatistiklerden hariç tut.

Gerçek olay: 20 kapanmış hedge işleminin tamamı toplamda -$12,961 (%25
kazanma oranı) — ama hepsi 2026-08-06 ile 2026-08-10 arası, YANİ hem
faz268aa'nın (2026-08-13 21:12, "Hedge — gerçek bug'lar düzeltildi")
HEM DE çok daha kritik olan 2026-08-16 18:41'deki bacak-boyutu bug
düzeltmesinden (pozisyon büyüklüğü ham varlık birimiyle hesaplanıyordu,
dolar değil) önce. Bu kayıpları "strateji kârsız" diye yorumlamak
yanıltıcı — bozuk boyutlandırmanın doğrudan sonucu. Düzeltmeden bu yana
hiç kapanan hedge işlemi yok (sadece 2 açık pozisyon, ikisi de
2026-08-18'de, yani düzeltmeden SONRA açılmış) — kullanıcı kararı:
pairs_trader görevi durdurulmuyor, temiz veri birikene kadar çalışmaya
devam ediyor; sadece bozuk-dönem geçmişi istatistiklerden çıkarılıyor.

Class 2 prensibi (Faz 238/240/268ab/279/280'de de uygulanan): satırlar
SİLİNMİYOR, sadece excluded_from_stats=true işaretleniyor.

Revision ID: faz281
Revises: faz280
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op

revision = "faz281"
down_revision = "faz280"
branch_labels = None
depends_on = None

# 9b719ec: "KRİTİK — pairs trading bacak boyutu dolar yerine ham varlık
# birimiydi" fix'inin canlıya alındığı gerçek commit anı.
_SIZING_FIX_LIVE_AT = "2026-08-16 18:41:44+02"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE decisions d SET excluded_from_stats = true "
            "WHERE d.status = 'closed' AND d.excluded_from_stats = false "
            "AND d.closed_at < :cutoff "
            "AND EXISTS ( "
            "  SELECT 1 FROM jsonb_array_elements(d.agent_contributions) elem "
            "  WHERE elem->>'type' = 'market_snapshot' "
            "  AND elem->'data'->'raw_snapshot'->>'pairs_trade' IS NOT NULL "
            ")"
        ).bindparams(cutoff=_SIZING_FIX_LIVE_AT)
    )


def downgrade() -> None:
    # Faz 240/268ab/279/280'deki aynı gerekçe: bu migration'ın SADECE
    # kendi işaretlediği satırları geri almak güvenli değil — koşulsuz
    # geri alma yapılmıyor.
    pass
