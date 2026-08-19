"""Faz 283: geçmişte kapanmış "scalp" (stop < %4.5) işlemlerini de
istatistiklerden hariç tut.

Kullanıcı kararı (2026-08-19): faz280'de sadece hâlâ açık pre-floor scalp
pozisyonları işaretlenmişti, geçmiş kapanmış 1188 işlem kasıtlı olarak
dokunulmamıştı ("dürüst tarihsel veri, tabanın kendi dayanağı"). Ama
kullanıcı gerçek dashboard verisini gördükten sonra netleşti: "Yeni kapanan
pozisyonlarda hep SL, hiçbir şey değişmiyor bu patern önemli bir veri
gösteriyor. Bu strateji kendi içinde problemli... scalp işlem riskli işlem
demektir. TP hedefi riske değmiyor genel olarak." — bu, faz268z'nin zaten
tespit ettiği yapısal bulguyu (dar ATR-tabanlı stop, normal piyasa
gürültüsüyle kolayca tetikleniyor) doğruluyor. Kullanıcı artık scalp'in
geçmiş performansının da dashboard'da/istatistiklerde görünmesini istemiyor.

Class 2 prensibi (Faz 238/240/268ab/279/280/281'de de uygulanan): satırlar
SİLİNMİYOR, sadece excluded_from_stats=true işaretleniyor — araştırma/
teşhis amaçlı ham veri hâlâ DB'de duruyor, sadece normal görünümden/
agregasyonlardan hariç.

api/rest/positions.py::_classify_trade_type ile AYNI öncelik sırası
(pump_fade > hedge > orta_vadeli > scalp) burada da uygulanıyor.

Revision ID: faz283
Revises: faz282
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op

revision = "faz283"
down_revision = "faz282"
branch_labels = None
depends_on = None

_SCALP_MAX_STOP_PCT = 4.5


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE decisions d SET excluded_from_stats = true "
            "WHERE d.status = 'closed' AND d.excluded_from_stats = false "
            "AND d.entry_price IS NOT NULL AND d.entry_price > 0 "
            "AND d.stop_loss_price IS NOT NULL "
            "AND (ABS(d.entry_price - d.stop_loss_price) / d.entry_price * 100) < :threshold "
            "AND (d.experiment_bucket IS NULL OR d.experiment_bucket != 'pump_fade_v1') "
            "AND (d.timeframe IS NULL OR d.timeframe NOT IN ('4h', '1d')) "
            "AND NOT EXISTS ( "
            "  SELECT 1 FROM jsonb_array_elements(d.agent_contributions) elem "
            "  WHERE elem->>'type' = 'market_snapshot' "
            "  AND elem->'data'->'raw_snapshot'->>'pairs_trade' IS NOT NULL "
            ")"
        ).bindparams(threshold=_SCALP_MAX_STOP_PCT)
    )


def downgrade() -> None:
    # Faz 240/268ab/279/280/281'deki aynı gerekçe: bu migration'ın SADECE
    # kendi işaretlediği satırları geri almak güvenli değil — koşulsuz
    # geri alma yapılmıyor.
    pass
