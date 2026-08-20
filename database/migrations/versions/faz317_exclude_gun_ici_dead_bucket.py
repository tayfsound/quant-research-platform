"""Faz 317: "gün içi" (stop mesafesi %4.5-%9) kovasındaki kapanmış
işlemleri istatistiklerden hariç tut.

Kullanıcı bulgusu, gerçek veriyle doğrulandı: /performance'ın gerçek
mantığıyla ölçüldü — 401 "gün içi" işlemi, %73.1 kazanma oranına rağmen
toplam SADECE $10.69 kâr (ortalama kazanç $0.42, ortalama kayıp -$1.04 —
kayıplar kazançların ~2.5 katı). Üç bağımsız sinyal bunun gerçek, canlı
strateji performansı DEĞİL, eski/kirli test verisi olduğunu gösteriyor:
(1) %70'i (282/401) exit_reason='manual_full' — gerçek AI kararıyla değil
elle kapatılmış, sadece 2 tanesi gerçek take_profit; (2) ortalama pozisyon
büyüklüğü $27.73 (en büyüğü $97.19) — gerçek ölçekli işlemler değil;
(3) TAMAMI 2026-08-06 ile 2026-08-14 arasında, o tarihten bu yana (6 gün)
tek bir yeni "gün içi" işlem yok. Kullanıcı kararı: "Bunları sistemden
çıkaralım gün içi işlem diye bir şey kalmasın... zaten işlem almıyormuş
ölü yatırım."

Bu migration SADECE var olan kirli satırları işaretliyor (Class 2 prensibi,
Faz 238/279/280/281'de de uygulanan — silme yok). "gün içi" sınıflandırma
KATEGORİSİNİN kendisinin kod tabanından tamamen kaldırılması (scalp/swing
ikili ayrımına birleştirildi) ayrı, kod-seviyeli bir değişiklik (bkz.
api/rest/positions.py::_classify_trade_type, database/repositories/
decision_persistor.py::_breakdown_by_trade_type, Transactions.tsx,
Dashboard.tsx).

_breakdown_by_trade_type()'daki AYNI önceliklendirme SQL'i (pump_fade >
hedge > orta_vadeli > stop-mesafesi) burada da kullanılıyor — "gün içi"ye
gerçekten düşen satırları (başka bir kategoriye ait olanları YANLIŞLIKLA
işaretlemeden) doğru seçmek için.

Revision ID: faz317
Revises: faz315
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op

revision = "faz317"
down_revision = "faz315"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
            UPDATE decisions
            SET excluded_from_stats = true
            WHERE status = 'closed'
              AND excluded_from_stats = false
              AND experiment_bucket IS DISTINCT FROM 'pump_fade_v1'
              AND (timeframe IS NULL OR timeframe NOT IN ('4h', '1d'))
              AND entry_price IS NOT NULL AND stop_loss_price IS NOT NULL AND entry_price != 0
              AND abs(entry_price - stop_loss_price) / entry_price * 100 >= 4.5
              AND abs(entry_price - stop_loss_price) / entry_price * 100 < 9.0
              AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(COALESCE(agent_contributions, '[]'::jsonb)) elem
                WHERE elem->>'type' = 'market_snapshot'
                  AND elem->'data'->'raw_snapshot'->>'pairs_trade' IS NOT NULL
              )
        """)
    )


def downgrade() -> None:
    # Faz 240/268ab/279/280/281'deki aynı gerekçe: bu migration'ın SADECE
    # kendi işaretlediği satırları geri almak güvenli değil — koşulsuz
    # geri alma yapılmıyor.
    pass
