"""Faz 372 — SHORT Exploration deneyi (kullanıcı tasarımı, 2026-08-29):
kontrollü örnekleme, GLOBAL EV kapısını asla gevşetmiyor.

Bağlam: analytics/mae_mfe.py::compute_optimal_barrier iki bağımsız ölçümde
(1098 ve 1851 kapanmış işlem) SHORT'un (en büyük kova: bear_trend+low+
crypto) gerçek bir kenarı olmadığını gösterdi — ama services/decision_
fusion.py'nin EV kapısı SHORT'u sürekli reddettiği için YENİ (bugünkü
düzeltmelerden SONraki) outcome verisi hiç birikemiyor. Kullanıcının kendi
tarifiyle: klasik bir exploration/exploitation kilidi —

    SHORT -> EV reddediyor -> trade açılmıyor -> yeni outcome oluşmuyor
    -> reliability güncellenmiyor -> EV hâlâ eski veriye bakıyor -> ...

Bu modül NORMAL SHORT yolunu (EV kapısı dahil) HİÇ değiştirmiyor. Ayrı,
küçük, sıkı-uygun, hard-cap'li bir "exploration" kovası açıyor — amaç
"SHORT kârlı mı" değil, "SHORT karar mekanizması gerçekten predictive
bilgi üretiyor mu" sorusuna taze veriyle cevap aramak. experiment_bucket
ile TAM izole (decision_recorder.py'nin "if opens_position and
experiment_bucket is None" desenindeki TÜM post-hoc gate'ler — signal_
persistence/pyramid/position_pool/mae_mfe_bucket_gate vb. — bu kovayı
hiç görmez, tamamen ayrı ve saf bir örneklem kalır)."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from database.session_factory import SessionFactory

EXPERIMENT_BUCKET = "short_exploration_v1"

# Sabit, küçük boyut — normal proposed_size'ın bir kesri. "Deneyin
# şartları" (kullanıcı): "Sabit düşük pozisyon boyutu."
SIZE_MULTIPLIER = 0.1

# Hard cap'ler (kullanıcı: "aynı anda en fazla 1-2", "günlük/haftalık bütçe").
MAX_CONCURRENT = 2
MAX_PER_WEEK = 10
# Aynı sembol art arda tekrar etmesin (kullanıcı: "aynı sembolde sürekli
# tekrar etmeyen adaylar") — çeşitlilik, tek bir sembolün gürültüsüne
# aşırı ağırlık vermemek için.
SYMBOL_COOLDOWN_DAYS = 3
# Deneyin KENDİ kill switch'i (kullanıcı: "Exploration'ın kendisine ayrı
# stop koşulu") — genel kill switch'ten (engines/risk_engine.py) BAĞIMSIZ,
# sadece bu kovayı durdurur.
CONSECUTIVE_LOSS_KILL_SWITCH = 3
# Sabit bir eşik değil, GÜNCEL confidence dağılımının üst yüzdeliği
# (kullanıcı: "confidence dağılımı değiştiğinde deney saçma şekilde ya
# çok fazla ya da hiç örnek üretmez").
CONFIDENCE_PERCENTILE = 85
MIN_RECENT_SAMPLES_FOR_PERCENTILE = 20


def _recent_short_confidences(limit: int = 200) -> list[float]:
    """Son N SHORT kararının (deney kovası HARİÇ — kendi kendini
    beslememesi için) confidence'ları — dinamik eşik hesabı için."""
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT confidence FROM decisions "
                "WHERE direction = 'SHORT' AND confidence IS NOT NULL "
                "AND (experiment_bucket IS NULL OR experiment_bucket != :bucket) "
                "ORDER BY timestamp DESC LIMIT :limit"
            ),
            {"bucket": EXPERIMENT_BUCKET, "limit": limit},
        ).fetchall()
    return [r[0] for r in rows]


def _dynamic_confidence_threshold() -> float | None:
    """Yeterli örneklem yoksa None (fail-closed — eşik icat edilmez, o
    döngüde kimse eligible olmaz)."""
    import numpy as np

    confidences = _recent_short_confidences()
    if len(confidences) < MIN_RECENT_SAMPLES_FOR_PERCENTILE:
        return None
    return float(np.percentile(confidences, CONFIDENCE_PERCENTILE))


def _kill_switch_triggered() -> bool:
    """Deneyin KENDİ son N kapanmış işlemi art arda zararlıysa (fail-safe,
    ana kill switch'ten bağımsız) yeni exploration açılışı durur — genel
    SHORT davranışını etkilemez, sadece bu kovayı."""
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


def is_eligible(symbol: str, confidence: float) -> tuple[bool, str | None]:
    """(eligible, ret_nedeni_varsa) döner — ret nedeni sadece loglama/
    açıklanabilirlik için, karar mantığını etkilemez."""
    threshold = _dynamic_confidence_threshold()
    if threshold is None:
        return False, "insufficient_recent_short_samples_for_percentile"
    if confidence < threshold:
        return False, "below_dynamic_confidence_percentile"

    if _kill_switch_triggered():
        return False, "exploration_kill_switch_active"

    with SessionFactory.get_session() as session:
        concurrent = session.execute(
            text(
                "SELECT count(*) FROM decisions WHERE experiment_bucket = :bucket AND status = 'open'"
            ),
            {"bucket": EXPERIMENT_BUCKET},
        ).scalar()
        weekly = session.execute(
            text(
                "SELECT count(*) FROM decisions WHERE experiment_bucket = :bucket "
                "AND status = 'open' AND opened_at > :since"
            ),
            {"bucket": EXPERIMENT_BUCKET, "since": datetime.now(UTC) - timedelta(days=7)},
        ).scalar()
        last_symbol_open = session.execute(
            text(
                "SELECT max(opened_at) FROM decisions WHERE experiment_bucket = :bucket AND symbol = :symbol"
            ),
            {"bucket": EXPERIMENT_BUCKET, "symbol": symbol},
        ).scalar()

    if concurrent >= MAX_CONCURRENT:
        return False, "max_concurrent_reached"
    if weekly >= MAX_PER_WEEK:
        return False, "weekly_budget_exhausted"
    if last_symbol_open is not None and (datetime.now(UTC) - last_symbol_open) < timedelta(days=SYMBOL_COOLDOWN_DAYS):
        return False, "symbol_cooldown_active"

    return True, None
