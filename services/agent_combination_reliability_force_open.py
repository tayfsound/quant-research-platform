"""Faz 392 — Ajan Kombinasyonu Force-Open deneyi (kullanıcı isteği,
2026-08-31): "Daha önce başarılı olmuş ajan kombinasyonu bir araya
gelirse sistem hiçbir engele takılmasın direkt işlem açsın."

analytics/agent_combination_reliability_gate.py'nin uzun süredir bilinçli
ertelenmiş "force-open" yarısını devreye alıyor — services/decision_
fusion.py'de negatif EV kapısını, SADECE gate_eligible (FDR + OOS-
survival + yeterli effective_sample_size) VE belirgin yüksek win_rate'e
sahip, GERÇEK geçmiş kombinasyonlar için geçersiz kılıyor.

Kullanıcının kendi argümanı: "Zaten açtığı işlem başarısız olursa
kombinasyonun başarı oranı otomatik düşeceği için gate'e takılıp kendi
kendine düzelecek" — doğru ama rapor HAFTALIK yenileniyor, yani bu
düzelme en fazla ~1 hafta gecikmeli olabilir. SIZE_MULTIPLIER ve aşağıdaki
kill switch bu gecikme penceresindeki olası zararı sınırlamak için var —
SHORT exploration'daki (services/short_exploration.py) AYNI ilke, aynı
experiment_bucket izolasyon deseni (decision_recorder.py'nin
"experiment_bucket is None" şartlı post-hoc gate'leri bu kovayı hiç
görmez)."""
from sqlalchemy import text

from database.session_factory import SessionFactory

EXPERIMENT_BUCKET = "agent_combo_force_open_v1"

# Negatif EV'yi geçersiz kılacak kadar güçlü kanıt var, ama tek bir
# yanlış sinyalin hesabı büyük yakmaması için tam boyut değil.
SIZE_MULTIPLIER = 0.5

# Rapor haftalık yenilendiği için, aynı anda çok fazla force-open pozisyon
# birikmesin (gerçek dünyada bir kombinasyon kötüye gitmeye başlarsa,
# haftalık rapor yenilenene kadar zarar sınırlı kalsın).
MAX_CONCURRENT = 5
CONSECUTIVE_LOSS_KILL_SWITCH = 3


def is_kill_switch_active() -> bool:
    """Deneyin KENDİ son N kapanmış işlemi art arda zararlıysa (fail-safe,
    ana kill switch'ten VE haftalık rapor yenilemesinden bağımsız) yeni
    force-open açılışı durur — genel LONG/SHORT davranışını etkilemez,
    sadece bu kovayı."""
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT outcome ->> 'win' AS win FROM decisions "
                "WHERE experiment_bucket = :bucket AND status = 'closed' "
                "ORDER BY closed_at DESC LIMIT :n"
            ),
            {"bucket": EXPERIMENT_BUCKET, "n": CONSECUTIVE_LOSS_KILL_SWITCH},
        ).fetchall()
    if len(rows) < CONSECUTIVE_LOSS_KILL_SWITCH:
        return False
    return all(r[0] == "false" for r in rows)


def is_concurrent_cap_reached() -> bool:
    with SessionFactory.get_session() as session:
        concurrent = session.execute(
            text("SELECT count(*) FROM decisions WHERE experiment_bucket = :bucket AND status = 'open'"),
            {"bucket": EXPERIMENT_BUCKET},
        ).scalar()
    return concurrent >= MAX_CONCURRENT


def is_eligible() -> tuple[bool, str | None]:
    """(eligible, ret_nedeni_varsa) — ret nedeni sadece loglama için."""
    if is_kill_switch_active():
        return False, "force_open_kill_switch_active"
    if is_concurrent_cap_reached():
        return False, "max_concurrent_reached"
    return True, None
