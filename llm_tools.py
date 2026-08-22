"""Faz 270 — kullanıcı isteği: "LLM'in herşeyi görüp takip edebiliyor
olması lazım." Respond sekmesindeki NvidiaDecisionCritic'e gerçek, canlı
DB/kod erişimi veren araç (tool-calling) fonksiyonları.

Somut, gerçek olay bu özelliği doğrudan doğurdu: LLM'e "kodu ve işlem
geçmişini taradım" dedirtip stop/TP mesafeleri gibi TAMAMEN uydurma
sayılar ürettirdiği yakalandı (ne DB'ye ne dosya sistemine erişimi
yoktu). Artık üç salt-okunur araç GERÇEK veri döndürüyor, hiçbir zaman
uydurmuyor (fail-closed — veri yoksa boş/None döner, asla rastgele bir
sayı üretilmez). Dördüncü (yazma) araç ise HİÇBİR ZAMAN diske yazmıyor
— sadece code_change_proposals tablosuna "pending" bir öneri ekliyor;
gerçek dosya değişikliği daima ayrı, insan onaylı bir adım (bkz.
migration faz270 docstring'i, "teşhis + öneri kuyruğu evet, otomatik
self-deploy hayır")."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

_ALLOWED_SEARCH_EXTENSIONS = {".py", ".ts", ".tsx", ".md"}
_EXCLUDED_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".pytest_cache", "htmlcov",
}
# Gerçek sır/kimlik bilgisi içerebilecek dosyalar — LLM'e ASLA okutulmuyor,
# ismi ne olursa olsun (path traversal/sızıntı riskine karşı fail-closed).
_BLOCKED_FILENAME_PATTERNS = (".env", "secret", "credential", ".pem", ".key")
_MAX_FILE_READ_LINES = 400
_MAX_SEARCH_RESULTS = 25


def _closed_trade_counts(session, hours: int, bucket_filter_sql: str) -> dict:
    from sqlalchemy import text

    row = session.execute(
        text(
            "SELECT "
            "count(*) FILTER (WHERE status = 'closed' AND closed_at >= now() - (:hours || ' hours')::interval AND outcome ->> 'exit_reason' NOT IN ('manual_full','manual_partial')) AS ai_closed_count, "
            "count(*) FILTER (WHERE status = 'closed' AND closed_at >= now() - (:hours || ' hours')::interval AND outcome ->> 'exit_reason' NOT IN ('manual_full','manual_partial') AND pnl > 0) AS ai_wins, "
            "count(*) FILTER (WHERE status = 'closed' AND closed_at >= now() - (:hours || ' hours')::interval AND outcome ->> 'exit_reason' = 'take_profit') AS tp_count, "
            "count(*) FILTER (WHERE status = 'closed' AND closed_at >= now() - (:hours || ' hours')::interval AND outcome ->> 'exit_reason' = 'stop_loss') AS sl_count, "
            "count(*) FILTER (WHERE status = 'closed' AND closed_at >= now() - (:hours || ' hours')::interval AND outcome ->> 'exit_reason' = 'breakeven_stop') AS breakeven_count, "
            "count(*) FILTER (WHERE status = 'closed' AND closed_at >= now() - (:hours || ' hours')::interval AND outcome ->> 'exit_reason' IN ('manual_full','manual_partial')) AS manual_count "
            "FROM decisions "
            "WHERE (excluded_from_stats IS NULL OR excluded_from_stats = false) "
            + bucket_filter_sql
        ),
        {"hours": hours},
    ).mappings().one()

    ai_closed = row["ai_closed_count"] or 0
    ai_wins = row["ai_wins"] or 0
    return {
        "ai_automatic_closed_trades": ai_closed,
        "ai_automatic_win_rate": round(ai_wins / ai_closed, 4) if ai_closed else None,
        "take_profit_exits": row["tp_count"] or 0,
        "stop_loss_exits": row["sl_count"] or 0,
        "breakeven_stop_exits": row["breakeven_count"] or 0,
        "manually_closed_trades": row["manual_count"] or 0,
    }


def get_recent_performance_summary(hours: int = 24) -> dict:
    """Gerçek DB'den, son N saatteki kararların özeti — manuel kapatılan
    pozisyonları (kullanıcının elle kâr almak için kapattığı, AI'ın
    OTONOM kararı OLMAYAN işlemler) ayrı sayıyor, çünkü bu ayrım
    yapılmadan hesaplanan bir kazanma oranı bu oturumda gerçek bir hataya
    yol açmıştı (bkz. context — manuel kapatılan TP'ler AI performansı
    gibi sayılmıştı).

    Faz 282 — kritik bulgu ("A/B kanal izolasyonu"): pump_fade_v1 AI
    konseyinden tamamen yalıtık, mekanik bir fade stratejisi — üst düzey
    ai_automatic_* alanları önceden onun kapanışlarını da harmanlıyordu.
    analytics/failure_classifier.py::summarize_stop_loss_failures'daki
    AYNI izolasyon burada da uygulanıyor: üst düzey alanlar SADECE AI
    konseyi kapanışlarını sayar, pump_fade_v1 ayrı 'pump_fade' alanında."""
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        # Faz 268-sonrası — gerçek kullanıcı bulgusu: bu sorgu opened_at'a
        # göre filtreliyordu, yani sadece "son N saatte AÇILMIŞ VE ZATEN
        # kapanmış" pozisyonları sayıyordu — pozisyonlar günlerce açık
        # kalabildiği için son 24 saatte KAPANAN (TP/SL dahil) işlemlerin
        # büyük çoğunluğu, GÜNLER önce açılmış oldukları için tamamen
        # görünmez oluyordu ("get_recent_performance_summary" adının
        # vaat ettiği "son dönem performansı" sorusuna yanlış cevap).
        # Artık kapanışla ilgili her sayaç closed_at'a göre filtreleniyor
        # — "ne zaman kapandı" sorusu "ne zaman açıldı"dan ayrıştırıldı.
        # open_count ise zaman penceresinden bağımsız, o ANKİ gerçek açık
        # pozisyon sayısı.
        open_count = session.execute(
            text("SELECT count(*) FROM decisions WHERE status = 'open'")
        ).scalar()

        ai_counts = _closed_trade_counts(session, hours, "AND (experiment_bucket IS NULL OR experiment_bucket != 'pump_fade_v1')")
        pump_fade_counts = _closed_trade_counts(session, hours, "AND experiment_bucket = 'pump_fade_v1'")

        # Faz 307 — gerçek bulgu: bu ham SQL, app_settings tablosunda satırı
        # OLMAYAN (hiç .set() ile değiştirilmemiş, hâlâ kod-içi varsayılanda
        # kalan — bu dört anahtarın hepsi bu durumda) bir anahtar için sessizce
        # None döndürüyordu; AppSettingsRepository.get()'in DEFAULTS'a düşen
        # fallback'i burada YOKTU. Sonuç: bu araç LLM'e "stop/target ATR
        # çarpanı null" diye rapor ediyordu, oysa GERÇEK canlı risk hattı
        # (engines/cognitive_pipeline.py::_load_multipliers) AppSettingsRepository.
        # get()'i kullandığı için hiçbir zaman null almıyor, DEFAULTS'taki
        # 2.5/1.4/0.045'e düzgün düşüyor — LLM'e yanlış veri gösteren bir
        # teşhis-aracı hatasıydı, canlı stop/target hesaplamasını etkilemiyordu.
        from database.repositories.app_settings_repository import DEFAULTS as _APP_SETTINGS_DEFAULTS

        settings_row = session.execute(
            text("SELECT key, value FROM app_settings WHERE key IN "
                 "('stop_atr_mult_long', 'target_atr_mult_long', 'stop_atr_mult_short', "
                 "'target_atr_mult_short', 'min_stop_pct', 'kill_switch_consecutive_losses')")
        ).fetchall()
        settings = {**_APP_SETTINGS_DEFAULTS, **{r[0]: r[1] for r in settings_row}}

    return {
        "window_hours": hours,
        "open_positions": open_count or 0,
        **ai_counts,
        "pump_fade": pump_fade_counts,
        "current_stop_atr_mult_long": settings.get("stop_atr_mult_long"),
        "current_target_atr_mult_long": settings.get("target_atr_mult_long"),
        "current_stop_atr_mult_short": settings.get("stop_atr_mult_short"),
        "current_target_atr_mult_short": settings.get("target_atr_mult_short"),
        "current_min_stop_pct": settings.get("min_stop_pct"),
        "current_kill_switch_consecutive_losses": settings.get("kill_switch_consecutive_losses"),
        "note": (
            "ai_automatic_* alanları SADECE AI'ın kendi başına verdiği "
            "otomatik kapanışları sayar — kullanıcının elle kapattığı "
            "işlemler (manually_closed_trades) hariçtir, bu ayrım "
            "gerçek AI performansını ölçmek için zorunludur. pump_fade_v1 "
            "(AI konseyinden tamamen yalıtık, mekanik bir fade stratejisi) "
            "de üst düzey sayılara karışmaz, ayrı 'pump_fade' alanındadır."
        ),
    }


def _is_path_allowed(resolved: Path) -> bool:
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return False
    name_lower = resolved.name.lower()
    return not any(pattern in name_lower for pattern in _BLOCKED_FILENAME_PATTERNS)


def read_source_file(path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
    """Repo kök dizininin DIŞINA çıkamaz (path traversal engellenir), .env/
    secret/credential/.pem/.key adlı hiçbir dosya okunamaz. En fazla 400
    satır döner (daha büyükse start_line/end_line ile dilimlenmeli)."""
    candidate = (REPO_ROOT / path).resolve()
    if not _is_path_allowed(candidate):
        return {"error": "path_not_allowed"}
    if not candidate.is_file():
        return {"error": "file_not_found"}

    try:
        lines = candidate.read_text(errors="replace").splitlines()
    except Exception as exc:
        return {"error": f"read_failed: {exc}"}

    total_lines = len(lines)
    start = max(1, start_line or 1)
    end = min(total_lines, end_line or total_lines)
    if end - start + 1 > _MAX_FILE_READ_LINES:
        end = start + _MAX_FILE_READ_LINES - 1

    snippet = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, min(end, total_lines) + 1))
    return {
        "path": path,
        "total_lines": total_lines,
        "returned_lines": f"{start}-{min(end, total_lines)}",
        "content": snippet,
    }


def search_code(query: str, max_results: int = _MAX_SEARCH_RESULTS) -> dict:
    """Repo genelinde (.py/.ts/.tsx/.md) düz metin arama — dış bir ikili
    dosyaya (ripgrep vb.) bağımlı değil, saf Python. En fazla max_results
    eşleşme döner (fazlası varsa truncated=true ile belirtilir)."""
    max_results = min(max_results, _MAX_SEARCH_RESULTS)
    matches: list[dict] = []
    truncated = False

    for root, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIR_NAMES and not d.startswith(".")]
        for filename in filenames:
            if Path(filename).suffix not in _ALLOWED_SEARCH_EXTENSIONS:
                continue
            file_path = Path(root) / filename
            try:
                with open(file_path, errors="replace") as fh:
                    for line_no, line in enumerate(fh, start=1):
                        if query.lower() in line.lower():
                            matches.append({
                                "path": str(file_path.relative_to(REPO_ROOT)),
                                "line": line_no,
                                "text": line.strip()[:300],
                            })
                            if len(matches) >= max_results:
                                truncated = True
                                break
            except Exception:
                continue
            if truncated:
                break
        if truncated:
            break

    return {"query": query, "matches": matches, "truncated": truncated}


def classify_recent_stop_loss_failures(hours: int = 90) -> dict:
    """Gerçek DB'den son N saatteki TÜM stop_loss kapanışlarını MAE/MFE
    verisine göre direction_error/barrier_error diye sınıflandırır —
    kullanıcının "37 kaybın 21'i yön hatası, 9'u bariyer hatası" tarzı
    adli teşhisinin doğrudan karşılığı."""
    from analytics.failure_classifier import summarize_stop_loss_failures

    return summarize_stop_loss_failures(hours=hours)


def train_and_evaluate_meta_label_model(window: int = 1000, min_samples: int = 100) -> dict:
    """Gerçek kapanmış işlemlerden P(TP before SL) meta-labeling
    modelini eğitir ve GERÇEK OOS (train/test) doğrulama metriklerini
    döndürür (test_accuracy, test_auc, taban oranı). Bu model HİÇBİR
    canlı karara bağlı değil — sadece "kendi edge'ini kanıtladı mı"
    sorusuna gerçek veriyle cevap vermek için."""
    from services.meta_label_model import train_meta_label_model

    model = train_meta_label_model(window=window, min_samples=min_samples)
    if model is None:
        return {"trained": False, "reason": "insufficient_samples_or_single_class"}
    return {
        "trained": True,
        "sample_count": model.sample_count,
        "baseline_correctness_rate": model.baseline_correctness_rate,
        "train_accuracy": model.train_accuracy,
        "test_accuracy": model.test_accuracy,
        "test_auc": model.test_auc,
        # Etiketler dengesiz olabilir (ör. TP oranı %28 ise "hep SL de"
        # diyen saf bir sınıflandırıcı %72 doğrulukla "kazanır") —
        # gerçek taban, ham TP oranı değil, ÇOĞUNLUK SINIFININ kendisi.
        # AUC (sınıf dengesizliğinden etkilenmez) bu yüzden burada daha
        # güvenilir bir sinyal — accuracy'nin yanında ayrıca bildiriliyor.
        "beats_naive_majority_class_baseline": model.test_accuracy > max(
            model.baseline_correctness_rate, 1 - model.baseline_correctness_rate,
        ),
        "note": (
            "Bu model canlı kararlara bağlı DEĞİL — sadece araştırma/doğrulama amaçlı. "
            "Etiketler dengesizse (TP oranı taban oranından çok farklıysa) accuracy yanıltıcı "
            "olabilir — test_auc (0.5=rastgele, 1.0=mükemmel) daha güvenilir bir sinyaldir."
        ),
    }


def get_shadow_mode_comparison(min_sample_size: int = 100) -> dict:
    """Faz 282 — kullanıcı isteği: "Shadow mode sonuçlarını LLM audit
    prompt'una besle." services/macro_shadow_tracker.py, council'in
    GERÇEK kararlarını hiç etkilemeden, SADECE macro ajanının kendi
    yönüne göre sanal (paper) pozisyon açıp kapatıyor — 100+ kapanmış
    örneklem birikince bu gölge stratejinin gerçek performansını (win_
    rate, avg_pnl_pct) tam council'inkiyle AYNI ölçekte (fiyat getirisi
    yüzdesi) karşılaştırmak mümkün. GET /shadow/comparison ile AYNI
    hesap — LLM'in konseyin genel yönlü karar kalitesini, tek bir
    ajanın (macro) yalın performansına karşı denetlemesi için."""
    from api.rest.shadow import council_comparison_summary
    from database.repositories.shadow_position_repository import ShadowPositionRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        macro_only = ShadowPositionRepository(session).comparison_summary(
            source="macro", min_sample_size=min_sample_size
        )
        council = council_comparison_summary(session, min_sample_size)

    return {
        "macro_only": macro_only,
        "council": council,
        "note": (
            "macro_only: council kararlarını hiç etkilemeyen, SADECE macro ajanının "
            "yönüne göre açılan sanal (paper) pozisyonların gerçek performansı. "
            "sample_size_sufficient=False ise (yeterli kapanmış örneklem yok) "
            "bu sayılardan mimari bir sonuç ÇIKARMA — sadece ölçüm amaçlı."
        ),
    }


def propose_code_change(file_path: str, title: str, description: str, diff: str, rationale: str) -> dict:
    """HİÇBİR ZAMAN diske yazmaz — sadece code_change_proposals'a
    "pending" bir satır ekler. Gerçek dosya değişikliği daima ayrı, insan
    onaylı bir adımdır."""
    from contracts.code_change_proposal import CodeChangeProposal
    from database.repositories.code_change_proposal_repository import CodeChangeProposalRepository
    from database.session_factory import SessionFactory

    proposal = CodeChangeProposal(
        title=title, file_path=file_path, description=description,
        diff=diff, rationale=rationale,
    )
    with SessionFactory.get_session() as session:
        CodeChangeProposalRepository(session).save(proposal)

    return {
        "proposal_id": str(proposal.id),
        "status": "pending",
        "note": "Bu öneri diske YAZILMADI — kullanıcı onayı bekleyen bir kuyruğa eklendi.",
    }


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_recent_performance_summary",
            "description": (
                "Sistemin son N saatteki GERÇEK karar/işlem performansını döndürür "
                "(AI'ın otonom kapanışları ile kullanıcının manuel kapattığı işlemler "
                "AYRI sayılır — sadece AI'ın kendi kararlarının kalitesini ölçmek için). "
                "Ayrıca güncel stop/target ATR çarpanlarını ve kill switch eşiğini döndürür."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "Kaç saatlik pencere (varsayılan 24)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_source_file",
            "description": "Repodaki gerçek bir kaynak dosyasını okur (path repo köküne göre, ör. 'services/decision_fusion.py').",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Repo genelinde bir metni/sembolü arar, eşleşen dosya:satır ve içeriği döndürür.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_recent_stop_loss_failures",
            "description": (
                "Son N saatteki tüm stop_loss kapanışlarını gerçek MAE/MFE verisine göre "
                "direction_error (yön tahmini kötüydü) / barrier_error (stop çok dardı, "
                "fiyat aslında hedefe ulaşmıştı) diye sınıflandırır."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "Kaç saatlik pencere (varsayılan 90)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "train_and_evaluate_meta_label_model",
            "description": (
                "Gerçek kapanmış işlemlerden P(TP before SL) meta-labeling modelini eğitir, "
                "GERÇEK OOS doğrulama metriklerini (test_accuracy, test_auc, taban oranı) döndürür. "
                "Canlı kararlara bağlı değil — sadece bu modelin gerçekten bir edge'i olup olmadığını sormak için."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "window": {"type": "integer", "description": "Kaç kapalı işlem (varsayılan 1000)"},
                    "min_samples": {"type": "integer", "description": "Min. eğitim örneklemi (varsayılan 100)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_shadow_mode_comparison",
            "description": (
                "Macro ajanının, council kararlarından tamamen bağımsız (sanal/paper) "
                "kendi yönlü kararlarının gerçek performansını (win_rate, avg_pnl_pct) "
                "tüm council'in gerçek performansıyla AYNI ölçekte karşılaştırır. "
                "sample_size_sufficient=False ise henüz yeterli kanıt yok demektir."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "min_sample_size": {"type": "integer", "description": "Yeterli sayılacak min. kapanmış örneklem (varsayılan 100)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_code_change",
            "description": (
                "Bir kod değişikliği ÖNERİR — asla diske yazmaz, sadece kullanıcının "
                "onayını bekleyen bir kuyruğa ekler. Gerçek bir sorun bulduğunda ve "
                "somut bir düzeltme önerebildiğinde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "diff": {"type": "string", "description": "Unified diff formatında önerilen değişiklik"},
                    "rationale": {"type": "string"},
                },
                "required": ["file_path", "title", "description", "diff", "rationale"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "get_recent_performance_summary": get_recent_performance_summary,
    "read_source_file": read_source_file,
    "search_code": search_code,
    "classify_recent_stop_loss_failures": classify_recent_stop_loss_failures,
    "train_and_evaluate_meta_label_model": train_and_evaluate_meta_label_model,
    "get_shadow_mode_comparison": get_shadow_mode_comparison,
    "propose_code_change": propose_code_change,
}
