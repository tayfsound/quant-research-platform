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


def _classify_rows(rows) -> dict:
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
        "total_stop_loss_trades": total,
        "direction_error_count": counts["direction_error"],
        "barrier_error_count": counts["barrier_error"],
        "insufficient_data_count": counts["insufficient_data"],
        "direction_error_pct": round(counts["direction_error"] / total, 4) if total else None,
        "barrier_error_pct": round(counts["barrier_error"] / total, 4) if total else None,
    }


# Faz 363 — backlog #15: "kâr edip zarara dönen ('breakeven'dan çıkış')
# pozisyonların ne kadarı stop yanlış yerleştirildiği için mi, ne kadarı
# gerçek yön hatası" + "bu kaybın toplam zarardaki payı % olarak
# dashboard'a kart olarak eklenmeli (SL/likidasyon/breakeven kırılımı)".
# Gerçek dağılım ölçüldü (tüm kapanmış işlemler): stop_loss tek başına
# tüm zarar-üreten kapanışların ~%95'i, breakeven_stop/liquidation/
# reduced_loss_stop kalan ~%5'i oluşturuyor — hepsi burada kapsanıyor.
_LOSS_EXIT_REASONS = ("stop_loss", "breakeven_stop", "liquidation", "reduced_loss_stop")


def summarize_loss_breakdown(hours: int | None = None) -> dict:
    """summarize_stop_loss_failures'ın (SADECE exit_reason='stop_loss')
    genelleştirilmiş hali — TÜM zarar-üreten exit_reason'ları kapsar,
    her biri için AYNI direction_error/barrier_error sınıflandırmasını
    (classify_stop_loss_failure, gerçek MAE/MFE'ye göre) uygular, VE
    her kategorinin TOPLAM ZARAR (bu 4 kategorinin $ toplamı) içindeki
    payını hesaplar. pump_fade_v1 AYNI izolasyon disipliniyle (bkz.
    summarize_stop_loss_failures docstring'i) üst düzey sayılardan
    dışlanır."""
    from sqlalchemy import text

    hours_clause = ""
    params: dict = {}
    if hours is not None:
        hours_clause = "AND closed_at >= now() - (:hours || ' hours')::interval"
        params["hours"] = hours

    reasons_sql = ", ".join(f"'{r}'" for r in _LOSS_EXIT_REASONS)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT entry_price, stop_loss_price, take_profit_price, outcome, "
                "experiment_bucket, coalesce(pnl, 0) as pnl "
                "FROM decisions "
                "WHERE status = 'closed' "
                f"AND outcome ->> 'exit_reason' IN ({reasons_sql}) {hours_clause} "
                "AND (excluded_from_stats IS NULL OR excluded_from_stats = false)"
            ),
            params,
        ).mappings().all()

    ai_rows = [r for r in rows if r["experiment_bucket"] != "pump_fade_v1"]
    pump_fade_rows = [r for r in rows if r["experiment_bucket"] == "pump_fade_v1"]

    def _breakdown(group_rows: list) -> dict:
        by_reason: dict[str, list] = {reason: [] for reason in _LOSS_EXIT_REASONS}
        for r in group_rows:
            reason = (r["outcome"] or {}).get("exit_reason")
            if reason in by_reason:
                by_reason[reason].append(r)

        total_loss = sum(abs(r["pnl"]) for r in group_rows if r["pnl"] < 0)
        categories = {}
        for reason, reason_rows in by_reason.items():
            classified = _classify_rows(reason_rows)
            reason_loss = sum(abs(r["pnl"]) for r in reason_rows if r["pnl"] < 0)
            categories[reason] = {
                **classified,
                "total_pnl": round(sum(r["pnl"] for r in reason_rows), 2),
                "loss_pct_of_total_loss": round(reason_loss / total_loss, 4) if total_loss > 0 else None,
            }
        return {
            "total_trades": len(group_rows),
            "total_loss": round(total_loss, 2),
            "categories": categories,
        }

    result = _breakdown(ai_rows)
    result["hours"] = hours
    result["pump_fade"] = _breakdown(pump_fade_rows)
    result["note"] = (
        "direction_error: fiyat hedefin anlamlı bir kısmına hiç yaklaşmadı — gerçek yön hatası. "
        "barrier_error: fiyat hedefe yakın/üstünde gitti ama stop/hedef mesafesi (bariyer) yüzünden "
        "önce zarara takıldı — yön kararı değil, bariyer/yerleşim sorunu. loss_pct_of_total_loss: bu "
        "kategorinin, dört zarar-üreten kategorinin (stop_loss/breakeven_stop/liquidation/"
        "reduced_loss_stop) TOPLAMININ ürettiği zarar içindeki payı. Üst düzey sayaçlar SADECE AI "
        "konseyi kararlarını kapsar — pump_fade_v1 ayrı 'pump_fade' alanında raporlanır."
    )
    return result


def summarize_stop_loss_failures(hours: int = 90) -> dict:
    """Gerçek DB'den son `hours` saatteki TÜM stop_loss kapanışlarını
    (excluded_from_stats hariç) sınıflandırıp gerçek bir dağılım
    döndürür — kullanıcının istediği "37 kaybın 21'i X, 9'u Y" tarzı
    adli teşhisin doğrudan karşılığı.

    Faz 282 — kritik bulgu ("A/B kanal izolasyonu"): pump_fade_v1,
    AI konseyinden TAMAMEN yalıtık, mekanik bir fade stratejisi (bkz.
    services/pump_fade_strategy.py) — kendi doğası gereği (kasıtlı
    contrarian giriş) çok farklı bir stop-loss örüntüsüne sahip.
    Bu fonksiyon önceden pump_fade_v1'in kapanışlarını AI konseyinin
    kapanışlarıyla harmanlıyordu — LLM denetçisi "AI'ın yön tahmini
    sistematik olarak bozuk" gibi yanlış bir teşhise varabilirdi, oysa
    sorun (varsa) tamamen ayrı bir karar mekanizmasından kaynaklanıyor
    olabilirdi. Aynı izolasyon disiplini kill switch/Concept Drift'te
    zaten uygulanıyordu (bkz. decision_persistor.py::list_closed_trades
    exclude_experiment_bucket) — üst düzey alanlar artık SADECE AI
    konseyi kapanışlarını sayıyor, pump_fade_v1 ayrı bir alt sözlükte."""
    from sqlalchemy import text

    with SessionFactory.get_session() as session:
        # Faz 268-sonrası — gerçek kullanıcı bulgusu: opened_at'a göre
        # filtrelemek "son N saatte AÇILMIŞ VE stop'a takılmış" işlemleri
        # sayıyordu — pozisyonlar günlerce açık kalabildiği için "son
        # dönemde KAPANAN stop-loss'lar" sorusuna (fonksiyonun kendi
        # amacı) yanlış cevap veriyordu. closed_at'a göre filtreleniyor.
        rows = session.execute(
            text(
                "SELECT entry_price, stop_loss_price, take_profit_price, outcome, experiment_bucket "
                "FROM decisions "
                "WHERE status = 'closed' AND outcome ->> 'exit_reason' = 'stop_loss' "
                "AND closed_at >= now() - (:hours || ' hours')::interval "
                "AND (excluded_from_stats IS NULL OR excluded_from_stats = false)"
            ),
            {"hours": hours},
        ).mappings().all()

    pump_fade_rows = [r for r in rows if r["experiment_bucket"] == "pump_fade_v1"]
    ai_rows = [r for r in rows if r["experiment_bucket"] != "pump_fade_v1"]

    result = _classify_rows(ai_rows)
    result["window_hours"] = hours
    result["pump_fade"] = _classify_rows(pump_fade_rows)
    result["note"] = (
        "direction_error: fiyat hedefin anlamlı bir kısmına hiç yaklaşmadı. "
        "barrier_error: fiyat hedefe yakın/üstünde gitti ama stop çok dar "
        "olduğu için önce ona takıldı — model değil, bariyer sorunu. "
        "Üst düzey sayaçlar SADECE AI konseyi kararlarını kapsar — pump_fade_v1 "
        "(AI konseyinden tamamen yalıtık, mekanik bir fade stratejisi) ayrı "
        "'pump_fade' alanında raporlanır, üst düzey sayılara karıştırılmaz."
    )
    return result
