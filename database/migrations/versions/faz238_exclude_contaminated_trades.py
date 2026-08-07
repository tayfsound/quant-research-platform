"""Faz 238: kirli geçmiş veriyi (aşırı capital testleri) istatistiklerden
dürüstçe hariç tut — silmeden.

Kullanıcı bulgusu: kendi deneyleri sırasında (starting_capital'ı 10-500
milyar gibi aşırı test değerlerine çekti) decisions tablosunda ölçek dışı
bir dönem birikti — "kirli geçmiş veriyi temizle" isteği. Gerçek ölçüm:
sane hedef notional ~$1333/işlem iken, bu dönemde bazı işlemler $36
milyon - $58 milyon notional'a ulaşmıştı (entry_price*quantity > $10,000
eşiği, 17 satır — tarih aralığı DEĞİL, çünkü kirlenme tek bir bloğa
denk gelmiyordu, sane ve kirli işlemler zaman içinde iç içe geçmişti).

Class 2 prensibi (backtest_runs'ta da uygulanan: "hiç silinmez, her zaman
bağımsız doğrulanabilir") burada da uygulanıyor — satırlar SİLİNMİYOR,
yeni excluded_from_stats kolonuyla işaretleniyor. Performance/Transactions
agregatları bunu filtreliyor, ham veri (isteyen için) hâlâ tabloda duruyor.

Revision ID: faz238
Revises: faz233
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op

revision = "faz238"
down_revision = "faz233"
branch_labels = None
depends_on = None

# Gerçek ölçümle bulunan eşik: sane hedef notional ~$1333/işlem, bu
# değerin ~7 katı bile normal koşullarda hiçbir zaman aşılmıyor (gerçek
# veride en yüksek sane notional ~$4275 idi, PAXGUSDT/XAUTUSDT gibi
# pahalı varlıklarda bile).
_CONTAMINATION_THRESHOLD_USD = 10_000


def upgrade() -> None:
    op.add_column(
        "decisions",
        sa.Column("excluded_from_stats", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        sa.text(
            "UPDATE decisions SET excluded_from_stats = true "
            "WHERE status = 'closed' AND entry_price * quantity > :threshold"
        ).bindparams(threshold=_CONTAMINATION_THRESHOLD_USD)
    )


def downgrade() -> None:
    op.drop_column("decisions", "excluded_from_stats")
