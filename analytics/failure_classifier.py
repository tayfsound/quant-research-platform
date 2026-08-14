"""Faz 268-sonrası — kullanıcının kendi getirdiği çerçeve: "0 TP / bütün
pozisyonlar SL" gibi bir sonuçla karşılaşınca "AI kötü karar veriyor" gibi
genel bir sonuca atlamak yerine, her kayıp işlemi GERÇEK MAE/MFE verisine
göre ayrık bir başarısızlık kategorisine ayırır:

- direction_error: fiyat hiçbir zaman hedefin anlamlı bir kısmına
  yaklaşmadı — muhtemelen gerçekten yanlış yön tahmini (kullanıcının
  "Senaryo A/C"si).
- barrier_error: fiyat hedefe YAKIN ya da onu GEÇECEK kadar lehimize
  gitti ama stop çok dar olduğu için önce ona takıldı — model hatası
  değil, bariyer (stop/target mesafesi) sorunu (kullanıcının "Senaryo
  B"si).
- insufficient_data: entry/stop/target/MAE/MFE'den biri eksikse
  (fail-closed) — kategori uydurulmaz.

Gerçek veri kaynağı: decisions.outcome->>'mae_pct'/'mfe_pct' (Faz
268-sonrası zaten hem backtest hem CANLI kapanışlarda dolduruluyor,
bkz. analytics/mae_mfe.py + services/position_closer.py)."""
from database.session_factory import SessionFactory

_REACHABILITY_THRESHOLD = 0.7  # kullanıcının kendi eşiği: "%70+ -> geometry problemi"


def classify_stop_loss_failure(
    entry_price: float | None,
    stop_loss_price: float | None,
    take_profit_price: float | None,
    mae_pct: float | None,
    mfe_pct: float | None,
) -> str:
    """Tek bir stop_loss kapanışını sınıflandırır. Girdilerden biri
    eksikse dürüstçe "insufficient_data" döner — asla uydurulmuş bir
    kategori üretilmez."""
    if not entry_price or not stop_loss_price or not take_profit_price:
        return "insufficient_data"
    if mae_pct is None or mfe_pct is None:
        return "insufficient_data"

    planned_target_pct = abs(take_profit_price - entry_price) / entry_price
    if planned_target_pct <= 0:
        return "insufficient_data"

    # reachability: fiyat, planlanan hedef mesafesinin ne kadarına
    # ulaştı (1.0 = tam hedefe, 1.0+ = hedefi geçti ama stop önce
    # tetiklendiği için trade yine de kaybetti).
    reachability = mfe_pct / planned_target_pct
    if reachability >= _REACHABILITY_THRESHOLD:
        return "barrier_error"
    return "direction_error"


def summarize_stop_loss_failures(hours: int = 90) -> dict:
    """Gerçek DB'den son `hours` saatteki TÜM stop_loss kapanışlarını
    (excluded_from_stats hariç) sınıflandırıp gerçek bir dağılım
    döndürür — kullanıcının istediği "37 kaybın 21'i X, 9'u Y" tarzı
    adli teşhisin doğrudan karşılığı."""
    from sqlalchemy import text

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT entry_price, stop_loss_price, take_profit_price, outcome "
                "FROM decisions "
                "WHERE status = 'closed' AND outcome ->> 'exit_reason' = 'stop_loss' "
                "AND opened_at >= now() - (:hours || ' hours')::interval "
                "AND (excluded_from_stats IS NULL OR excluded_from_stats = false)"
            ),
            {"hours": hours},
        ).mappings().all()

    counts = {"direction_error": 0, "barrier_error": 0, "insufficient_data": 0}
    for row in rows:
        outcome = row["outcome"] or {}
        category = classify_stop_loss_failure(
            entry_price=row["entry_price"],
            stop_loss_price=row["stop_loss_price"],
            take_profit_price=row["take_profit_price"],
            mae_pct=outcome.get("mae_pct"),
            mfe_pct=outcome.get("mfe_pct"),
        )
        counts[category] += 1

    total = len(rows)
    return {
        "window_hours": hours,
        "total_stop_loss_trades": total,
        "direction_error_count": counts["direction_error"],
        "barrier_error_count": counts["barrier_error"],
        "insufficient_data_count": counts["insufficient_data"],
        "direction_error_pct": round(counts["direction_error"] / total, 4) if total else None,
        "barrier_error_pct": round(counts["barrier_error"] / total, 4) if total else None,
        "note": (
            "direction_error: fiyat hedefin anlamlı bir kısmına hiç yaklaşmadı. "
            "barrier_error: fiyat hedefe yakın/üstünde gitti ama stop çok dar "
            "olduğu için önce ona takıldı — model değil, bariyer sorunu."
        ),
    }
