"""Faz 268-sonrası — kullanıcı isteği: Adaptive Barrier Engine'i (MAE/MFE
tabanlı, koşullu SL/TP önerisi) RiskTargetStage'e wire edelim. Bu modül,
GERÇEK kapanmış işlemlerden compute_optimal_barrier()'ın beklediği
formatta veri çekip tabloyu inşa eder ve BarrierTableRepository'ye
kaydeder — services/agent_confidence_model.py / meta_label_model.py ile
AYNI "gerçek veriden öğren, yetersizse fail-closed" deseni."""
from analytics.barrier_table_repository import GROUP_BY, BarrierTableRepository
from analytics.mae_mfe import MIN_GROUP_SIZE, compute_optimal_barrier
from services.agent_confidence_model import _normalize_raw_features
from services.agent_memory import asset_class_trading_category

DEFAULT_WINDOW = 2000
# compute_optimal_barrier zaten kova başına min_group_size uyguluyor —
# bu, TÜM işlem havuzunun (kovalara bölünmeden önce) en azından birkaç
# kova doldurabilecek kadar büyük olmasını garanti eden, daha üst bir eşik.
MIN_TOTAL_SAMPLES = 200


def _extract_real_trades_for_barrier_table(window: int = DEFAULT_WINDOW) -> list[dict]:
    """decisions tablosundan, compute_optimal_barrier()'ın beklediği
    formatta gerçek kapanmış işlemleri çeker. exit_reason'a göre
    FİLTRELENMİYOR (meta_label_model.py'nin aksine) — path-relabeling
    (_counterfactual_barrier_outcome) zaten ham mae_pct/mfe_pct'ten
    kendi sonucunu yeniden türetiyor, orijinal exit_reason'a bağımlı
    değil."""
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT direction, confidence, agent_contributions, outcome, experiment_bucket, symbol, closed_at "
                "FROM decisions "
                "WHERE status = 'closed' AND excluded_from_stats = false "
                "AND outcome ->> 'mae_pct' IS NOT NULL AND outcome ->> 'mfe_pct' IS NOT NULL "
                "ORDER BY closed_at DESC LIMIT :limit"
            ),
            {"limit": window},
        ).mappings().all()

    trades = []
    for row in rows:
        direction = (row["direction"] or "").upper()
        if direction not in ("LONG", "SHORT"):
            continue

        raw_features = None
        for contribution in row["agent_contributions"]:
            if isinstance(contribution, dict) and contribution.get("type") == "market_snapshot":
                raw_features = (contribution.get("data") or {}).get("features", {})
                break
        if raw_features is None:
            continue
        feats = _normalize_raw_features(raw_features)

        outcome = row["outcome"] or {}
        trades.append({
            "direction": direction,
            "confidence": row["confidence"] or 0.0,
            "regime": feats.get("long_term_trend_regime", "unknown"),
            "volatility_regime": feats.get("volatility_regime", "unknown"),
            "asset_class": asset_class_trading_category(row["symbol"]) or "unknown",
            # Faz 368 — sadece EKLENDİ: compute_optimal_barrier'ın yeni
            # MIN_DISTINCT_DAYS kontrolü için (bkz. o modülün notu — bir
            # kova dar bir tarihsel pencereden gelmemeli).
            "closed_at": row["closed_at"],
            "mae_pct": outcome.get("mae_pct"),
            "mfe_pct": outcome.get("mfe_pct"),
            "time_to_mae_seconds": outcome.get("time_to_mae_seconds"),
            "time_to_mfe_seconds": outcome.get("time_to_mfe_seconds"),
            # compute_optimal_barrier bunu kullanmıyor ama compute_
            # conditional_mae_distribution (services/mae_mfe_confidence_
            # gatherer.py) win_rate için gerektiriyor — tek gerçek veri
            # kaynağı, iki tüketici.
            "win": outcome.get("win"),
            # Faz 367-devam — sadece EKLENDİ (compute_optimal_barrier/
            # Adaptive Barrier Engine bu alanı hiç okumuyor, davranışı
            # değişmiyor): services/mae_mfe_confidence_gatherer.py'nin
            # pump_fade_v1/basis_arb_v1'i hariç tutabilmesi için.
            "experiment_bucket": row["experiment_bucket"],
        })

    return trades


def build_and_save_barrier_table(
    window: int = DEFAULT_WINDOW,
    min_group_size: int = MIN_GROUP_SIZE,
    min_decisive_count: int = MIN_GROUP_SIZE,
    repository: BarrierTableRepository | None = None,
) -> dict | None:
    """Fail-closed: yeterli örneklem yoksa (MIN_TOTAL_SAMPLES) ya da
    hiçbir kova yeterli/kararlı veri biriktirmemişse None döner ve
    HİÇBİR ŞEY KAYDETMEZ — eski (varsa) tablo korunur, gürültüden yeni
    bir tablo üretilmez."""
    trades = _extract_real_trades_for_barrier_table(window)
    if len(trades) < MIN_TOTAL_SAMPLES:
        return None

    table = compute_optimal_barrier(
        trades, group_by=GROUP_BY, min_group_size=min_group_size, min_decisive_count=min_decisive_count,
    )
    if not table:
        return None

    repo = repository or BarrierTableRepository()
    repo.save(table, sample_count=len(trades))
    return table
