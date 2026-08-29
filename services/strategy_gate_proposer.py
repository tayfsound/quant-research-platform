"""Strategy Gate Approval'ın önerici (proposer) katmanı — Faz 366.
Kullanıcı isteği: "ürettiği strateji insan onayına sunulur böyle bir
yapı ayarlamıştık" — strategy_hypothesis_scanner.py'nin ölçüm-only
çıktısını (Faz 346) weight_optimizer.py ile AYNI propose→pending→
approve/reject döngüsüne bağlıyor. Kasıtlı olarak periyodik bir görev
(Celery beat) — pozisyon kapanışında değil, tarama pahalı (FDR + OOS
walk-forward), her kapanışta tekrar hesaplamaya gerek yok."""
from analytics.strategy_hypothesis_scanner import scan_for_gate_candidates, validate_candidate_out_of_sample
from services.strategy_regime_compatibility_gatherer import _strategy_label


def _fetch_records_sorted_by_time(limit: int) -> list[dict]:
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                """
                SELECT experiment_bucket, market_regime, direction, pnl, entry_price, stop_loss_price,
                       agent_contributions
                FROM decisions
                WHERE status = 'closed' AND excluded_from_stats = false
                  AND market_regime IS NOT NULL
                ORDER BY closed_at ASC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).fetchall()

    return [
        {
            "strategy": _strategy_label(
                r.experiment_bucket, r.direction, r.entry_price, r.stop_loss_price, r.agent_contributions,
            ),
            "market_regime": r.market_regime,
            "win": (r.pnl or 0.0) > 0,
        }
        for r in rows
    ]


def propose_strategy_gate_candidates(limit: int = 5000) -> dict:
    """Gerçek kapanmış kararlardan (zaman sırasına göre, en eski ilk)
    scan_for_gate_candidates + validate_candidate_out_of_sample'ı
    çalıştırır. SADECE gerçekten replicated_out_of_sample=True olan VE
    daha önce önerilmemiş/karar verilmemiş adaylar (has_pending_or_
    approved dedup, weight_approval'daki AYNI Faz 229 disiplini) yeni
    bir pending StrategyGateApproval satırı olarak kaydedilir."""
    from database.repositories.strategy_gate_approval_repository import StrategyGateApprovalRepository
    from database.session_factory import SessionFactory
    from contracts.strategy_gate_approval import StrategyGateApproval

    records = _fetch_records_sorted_by_time(limit)
    candidates = scan_for_gate_candidates(records)

    proposed = []
    for candidate in candidates:
        oos = validate_candidate_out_of_sample(records, candidate)
        if not oos["replicated_out_of_sample"]:
            continue

        with SessionFactory.get_session() as session:
            repo = StrategyGateApprovalRepository(session)
            if repo.has_pending_or_blocked(candidate["strategy"], candidate["market_regime"]):
                continue
            approval = StrategyGateApproval(
                strategy=candidate["strategy"],
                market_regime=candidate["market_regime"],
                sample_size=candidate["sample_size"],
                win_rate=candidate["win_rate"],
                rest_win_rate=candidate["rest_win_rate"],
                delta_vs_rest=candidate["delta_vs_rest"],
                p_value=candidate["p_value"],
                replicated_out_of_sample=True,
            )
            repo.save(approval)
            proposed.append({"strategy": approval.strategy, "market_regime": approval.market_regime})

    return {"n_records_analyzed": len(records), "n_candidates_found": len(candidates), "n_proposed": len(proposed), "proposed": proposed}
