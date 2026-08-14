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
import re
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


def get_recent_performance_summary(hours: int = 24) -> dict:
    """Gerçek DB'den, son N saatteki kararların özeti — manuel kapatılan
    pozisyonları (kullanıcının elle kâr almak için kapattığı, AI'ın
    OTONOM kararı OLMAYAN işlemler) ayrı sayıyor, çünkü bu ayrım
    yapılmadan hesaplanan bir kazanma oranı bu oturumda gerçek bir hataya
    yol açmıştı (bkz. context — manuel kapatılan TP'ler AI performansı
    gibi sayılmıştı)."""
    from database.session_factory import SessionFactory
    from sqlalchemy import text

    with SessionFactory.get_session() as session:
        cutoff = text("now() - (:hours || ' hours')::interval")
        row = session.execute(
            text(
                "SELECT "
                "count(*) FILTER (WHERE status = 'open') AS open_count, "
                "count(*) FILTER (WHERE status = 'closed' AND outcome ->> 'exit_reason' NOT IN ('manual_full','manual_partial')) AS ai_closed_count, "
                "count(*) FILTER (WHERE status = 'closed' AND outcome ->> 'exit_reason' NOT IN ('manual_full','manual_partial') AND pnl > 0) AS ai_wins, "
                "count(*) FILTER (WHERE status = 'closed' AND outcome ->> 'exit_reason' = 'take_profit') AS tp_count, "
                "count(*) FILTER (WHERE status = 'closed' AND outcome ->> 'exit_reason' = 'stop_loss') AS sl_count, "
                "count(*) FILTER (WHERE status = 'closed' AND outcome ->> 'exit_reason' = 'breakeven_stop') AS breakeven_count, "
                "count(*) FILTER (WHERE status = 'closed' AND outcome ->> 'exit_reason' IN ('manual_full','manual_partial')) AS manual_count "
                "FROM decisions "
                "WHERE opened_at >= now() - (:hours || ' hours')::interval "
                "AND (excluded_from_stats IS NULL OR excluded_from_stats = false)"
            ),
            {"hours": hours},
        ).mappings().one()

        settings_row = session.execute(
            text("SELECT key, value FROM app_settings WHERE key IN "
                 "('stop_atr_mult', 'target_atr_mult', 'min_stop_pct', 'kill_switch_consecutive_losses')")
        ).fetchall()
        settings = {r[0]: r[1] for r in settings_row}

    ai_closed = row["ai_closed_count"] or 0
    ai_wins = row["ai_wins"] or 0
    return {
        "window_hours": hours,
        "open_positions": row["open_count"] or 0,
        "ai_automatic_closed_trades": ai_closed,
        "ai_automatic_win_rate": round(ai_wins / ai_closed, 4) if ai_closed else None,
        "take_profit_exits": row["tp_count"] or 0,
        "stop_loss_exits": row["sl_count"] or 0,
        "breakeven_stop_exits": row["breakeven_count"] or 0,
        "manually_closed_trades": row["manual_count"] or 0,
        "current_stop_atr_mult": settings.get("stop_atr_mult"),
        "current_target_atr_mult": settings.get("target_atr_mult"),
        "current_min_stop_pct": settings.get("min_stop_pct"),
        "current_kill_switch_consecutive_losses": settings.get("kill_switch_consecutive_losses"),
        "note": (
            "ai_automatic_* alanları SADECE AI'ın kendi başına verdiği "
            "otomatik kapanışları sayar — kullanıcının elle kapattığı "
            "işlemler (manually_closed_trades) hariçtir, bu ayrım "
            "gerçek AI performansını ölçmek için zorunludur."
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
    "propose_code_change": propose_code_change,
}
