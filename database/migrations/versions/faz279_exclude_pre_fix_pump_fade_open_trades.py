"""Faz 279: pump_fade_v1'de hâlâ açık, iki kritik bug'dan (200-limit izleme
boşluğu + trailing stop eksikliği) ÖNCE açılmış pozisyonları, kapandıklarında
istatistiklere karışmasınlar diye şimdiden excluded_from_stats=true işaretle.

Gerçek olay (2026-08-19): close_due_positions_task'in list_open_positions
limit=200 varsayılanı yüzünden (bkz. faz "KRİTİK: açık pozisyon kontrolü
200/1000 limitine takılıyordu" commit'i) ve trailing stop mekanizmasının o
ana kadar hiç var olmaması yüzünden, pump_fade_v1 deneyinin bazı pozisyonları
uzun süre stop/trailing kontrolünden geçmeden açık kaldı. Kullanıcı bulgusu:
bu pozisyonlar önce iyi kâra geçip sonra zarara döndü, sistem müdahale
etmedi. Kullanıcı: "Bunları hiç açılmamış gibi sistemden çıkaramaz mıyız?
kapansa da elimizdeki veriyi kirletecek."

Class 2 prensibi (Faz 238/240/268ab'de de uygulanan): satırlar SİLİNMİYOR
(event sourcing/audit trail korunuyor, pozisyonlar gerçek stop/trailing
mantığıyla — artık düzeltilmiş haliyle — normal şekilde yönetilmeye devam
ediyor), sadece excluded_from_stats=true işaretleniyor. Bu alan bugüne kadar
sadece status='closed' satırlarda okunuyordu (win-rate/pnl/A-B test
agregasyonları) — burada farkı, henüz AÇIKKEN işaretlenmesi: pozisyon
kapandığında zaten var olan filtreler (decision_persistor.py,
services/ab_testing.py, vb.) otomatik olarak devreye girip bu satırları
dışarıda bırakacak.

Kapsam: experiment_bucket='pump_fade_v1' AND status='open' AND opened_at,
200-limit düzeltmesinin canlıya alındığı ana (2026-08-19 08:21:15+02,
commit a74b1b7) kadar açılmış tüm pozisyonlar — bu ana kadar açılan HER
pump_fade_v1 pozisyonu, düzeltmeden önceki eksik izleme penceresine maruz
kalmıştı (gerçek veri: bu migration çalıştığı anda mevcut olan 19 açık
pump_fade_v1 pozisyonunun TAMAMI bu eşikten önce açılmış).

Revision ID: faz279
Revises: faz278
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op

revision = "faz279"
down_revision = "faz278"
branch_labels = None
depends_on = None

# a74b1b7: "KRİTİK: açık pozisyon kontrolü 200/1000 limitine takılıyordu"
# fix'inin canlıya alındığı gerçek commit anı.
_MONITORING_FIX_LIVE_AT = "2026-08-19 08:21:15+02"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE decisions SET excluded_from_stats = true "
            "WHERE status = 'open' AND excluded_from_stats = false "
            "AND experiment_bucket = 'pump_fade_v1' "
            "AND opened_at < :cutoff"
        ).bindparams(cutoff=_MONITORING_FIX_LIVE_AT)
    )


def downgrade() -> None:
    # Faz 240/268ab'deki aynı gerekçe: bu migration'ın SADECE kendi
    # işaretlediği satırları geri almak güvenli değil — koşulsuz geri
    # alma yapılmıyor.
    pass
