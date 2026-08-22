"""Meta-Learning Effectiveness'ın girdisini GERÇEK onaylı ajan ayarlama
turlarından toplayan tek kaynak — Cognitive Core 2.0 (Faz 744-768).
analytics/meta_learning_effectiveness.py::compute_meta_learning_trend()
saf (pure) kalıyor — gerçek veriye dokunan kod burada."""
from analytics.meta_learning_effectiveness import compute_meta_learning_trend


def gather_meta_learning_effectiveness() -> dict:
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT sharpe_improvement FROM agent_tuning_approvals "
                "WHERE status = 'approved' ORDER BY timestamp ASC"
            )
        ).all()

    sharpe_improvements = [r[0] for r in rows if r[0] is not None]
    return {
        "trend": compute_meta_learning_trend(sharpe_improvements),
        "n_approved_rounds": len(sharpe_improvements),
    }
