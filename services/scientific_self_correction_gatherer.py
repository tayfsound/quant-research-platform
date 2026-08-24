"""Scientific Self-Correction'ın girdisini GERÇEK kapanmış işlemlerden
toplayan tek kaynak — Faz 356 (kullanıcı isteği: "2-3 gündür kazanma
oranım düştü, bunu sistem kendi kendine fark edip etiketleyebilsin mi").
analytics/scientific_self_correction.py::compute_hypothesis_retest()
saf (pure) kalıyor — gerçek veriye dokunan kod burada.

experiments tablosu (curiosity_id/hypothesis) bu ölçüm için kasıtlı
olarak kullanılmadı — gerçek içeriği incelendi, sadece 7 satır (hepsi
tek bir "RSI < 30" geliştirme-zamanı test kaydı), retest için anlamlı
bir veri kaynağı değil. Bunun yerine mae_mfe_confidence_gatherer.py'nin
zaten kanıtlanmış deseniyle AYNI kaynaktan (decisions tablosu, GERÇEK
kapanmış işlemler) besleniyor — "hipotez" burada somut: council'in
kendi genel/yön-bazlı/deney-kovası-bazlı isabet oranı."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from analytics.scientific_self_correction import compute_hypothesis_retest
from database.session_factory import SessionFactory
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

DEFAULT_RECENT_DAYS = 7
_BASIS_ARB_EXPERIMENT_BUCKET = "basis_arb_v1"


def _fetch_wins_and_totals(recent_days: int) -> dict:
    """Faz 268-sonrası'nın kill switch/concept drift deseniyle AYNI
    dışlama: pump_fade/basis_arb kendi risk yönetimlerine sahip mekanik
    stratejiler, council'in GERÇEKTEN yön konusunda haklı çıkıp
    çıkmadığını yansıtmıyor — dahil edilirse retest'i yanlış yöne
    çekebilir."""
    cutoff = datetime.now(UTC) - timedelta(days=recent_days)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT direction, experiment_bucket, pnl, closed_at "
                "FROM decisions "
                "WHERE status = 'closed' AND excluded_from_stats = false "
                "AND direction IN ('LONG', 'SHORT') "
                "AND (experiment_bucket IS NULL OR experiment_bucket NOT IN (:pump_fade, :basis_arb))"
            ),
            {"pump_fade": PUMP_FADE_EXPERIMENT_BUCKET, "basis_arb": _BASIS_ARB_EXPERIMENT_BUCKET},
        ).mappings().all()

    def _bucket() -> dict:
        return {"original_wins": 0, "original_n": 0, "recent_wins": 0, "recent_n": 0}

    segments: dict[str, dict] = {"overall": _bucket()}
    for row in rows:
        is_recent = row["closed_at"] is not None and row["closed_at"] >= cutoff
        win = 1 if (row["pnl"] or 0.0) > 0 else 0
        for key in (
            "overall",
            f"direction={row['direction']}",
            f"experiment_bucket={row['experiment_bucket'] or 'none'}",
        ):
            bucket = segments.setdefault(key, _bucket())
            if is_recent:
                bucket["recent_wins"] += win
                bucket["recent_n"] += 1
            else:
                bucket["original_wins"] += win
                bucket["original_n"] += 1

    return segments


def gather_scientific_self_correction(recent_days: int = DEFAULT_RECENT_DAYS) -> dict:
    segments = _fetch_wins_and_totals(recent_days)

    results: dict[str, dict] = {}
    for label, counts in segments.items():
        retest = compute_hypothesis_retest(
            original_wins=counts["original_wins"],
            original_n=counts["original_n"],
            recent_wins=counts["recent_wins"],
            recent_n=counts["recent_n"],
        )
        if retest is not None:
            results[label] = retest

    return {"recent_days": recent_days, "segments": results}
