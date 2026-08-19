"""Faz 280: hâlâ açık, "scalp" bölgesindeki (stop < %4.5) pozisyonları,
kapandıklarında istatistiklere karışmasınlar diye şimdiden
excluded_from_stats=true işaretle.

Gerçek olay (2026-08-19): kullanıcı bulgusu — bugün kapanan scalp
işlemlerin verisi kendisini yanıltıyor. Kök neden faz268z'de (2026-08-13
20:58, "Minimum stop mesafesi tabanı — scalp kaybının kaynağı") zaten
tespit edilip düzeltilmişti: MIN_STOP_PCT tabanı o andan beri hesaplanan
stop %4.5'in altına düşerse SL/TP'yi oranı koruyarak genişletiyor.
Doğrulandı: o tarihten bu yana AÇILAN hiçbir işlem scalp bölgesine
düşmemiş (0/0) — mekanizma çalışıyor. Ama taban gelmeden ÖNCE açılmış
418 pozisyon hâlâ açık; bunlar artık düzeltilmiş stop/trailing
mantığıyla yönetiliyor olsa da, "scalp" sınıflandırması (kendisi zaten
kanıtlanmış zararlı bir rejimin — dar ATR-tabanlı stop'un piyasa
gürültüsüyle kolayca tetiklenmesi — kalıntısı) kapandıklarında
istatistiklere karışmaya devam ederdi.

api/rest/positions.py::_classify_trade_type ile AYNI öncelik sırası
(pump_fade > hedge > orta_vadeli > scalp) burada da uygulanıyor —
pump_fade_v1 (zaten faz279'da ayrıca ele alındı), hedge (jsonb
pairs_trade etiketi) ve 4h/1d zaman dilimli (orta_vadeli) pozisyonlar
scalp sayılmıyor.

Class 2 prensibi (Faz 238/240/268ab/279'da da uygulanan): satırlar
SİLİNMİYOR, sadece excluded_from_stats=true işaretleniyor. Geçmişte
ZATEN kapanmış, temiz scalp işlemlerine (dürüst performans kaydı,
tabanın kendi dayanağı) kasıtlı olarak DOKUNULMUYOR — sadece kapanmayı
bekleyen bu 418 pozisyon kapsam dahilinde.

Revision ID: faz280
Revises: faz279
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op

revision = "faz280"
down_revision = "faz279"
branch_labels = None
depends_on = None

_SCALP_MAX_STOP_PCT = 4.5


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE decisions d SET excluded_from_stats = true "
            "WHERE d.status = 'open' AND d.excluded_from_stats = false "
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
    # Faz 240/268ab/279'daki aynı gerekçe: bu migration'ın SADECE kendi
    # işaretlediği satırları geri almak güvenli değil — koşulsuz geri
    # alma yapılmıyor.
    pass
