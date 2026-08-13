"""Faz 268ab: 2026-08-06'daki gerçek olaydan kalan aşırı stop-overshoot'lu
işlemleri istatistiklerden dürüstçe hariç tut — silmeden.

Gerçek bulgu (2026-08-13, kullanıcı bulgusu üzerine incelendi): son 200
gerçek SL kapanışının medyan stop-aşımı sadece %0.07 (60sn kontrol
aralığı için makul) — ama 13 kayıt %22-%1078 arası aşım gösteriyor,
hepsi 2026-08-06 18:18-21:41 arası (XAUTUSDT/PAXGUSDT/ADAUSDT/XRPUSDT),
hepsi kaldıraçsız. Bu, Faz 239/240'ın MockOHLCVAdapter sızıntısıyla AYNI
zaman penceresine denk geliyor ama farklı bir imza (20x fiyat sıçraması
değil, gerçek stop seviyesinden makul-olmayan bir sapma) — faz240'ın
kendi eşiğini (entry/exit oranı > 20x) yakalamamış, ayrı bir heuristik
gerekiyor.

Class 2 prensibi (Faz 238/240'ta da uygulanan): satırlar SİLİNMİYOR,
sadece excluded_from_stats=true işaretleniyor.

Revision ID: faz268ab
Revises: faz269
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

revision = "faz268ab"
down_revision = "faz269"
branch_labels = None
depends_on = None

# Gerçek 60sn'lik kontrol aralığında normal bir stop-loss aşımı %1'in
# çok altında kalır (gerçek ölçüm: son 200 SL kapanışının medyanı %0.07).
# %10'un üzerindeki bir aşım, gerçek bir piyasa hareketiyle açıklanamaz —
# 2026-08-06'daki bilinen veri kalitesi olayının imzasıdır.
_OVERSHOOT_THRESHOLD_PCT = 0.10


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE decisions SET excluded_from_stats = true "
            "WHERE status = 'closed' AND excluded_from_stats = false "
            "AND outcome ->> 'exit_reason' = 'stop_loss' "
            "AND stop_loss_price IS NOT NULL AND stop_loss_price > 0 "
            "AND exit_price IS NOT NULL "
            "AND ( "
            "  (direction = 'LONG' AND (stop_loss_price - exit_price) / stop_loss_price > :threshold) "
            "  OR "
            "  (direction = 'SHORT' AND (exit_price - stop_loss_price) / stop_loss_price > :threshold) "
            ")"
        ).bindparams(threshold=_OVERSHOOT_THRESHOLD_PCT)
    )


def downgrade() -> None:
    # Faz 240'ın notuyla aynı gerekçe: bu migration'ın SADECE kendi
    # işaretlediği satırları geri almak güvenli değil (hangi satırların
    # başka bir mekanizma tarafından da işaretlenmiş olabileceği ayrıca
    # izlenmiyor) — koşulsuz geri alma yapılmıyor.
    pass
