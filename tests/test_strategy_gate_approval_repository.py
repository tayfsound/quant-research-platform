"""database/repositories/strategy_gate_approval_repository.py — Faz 366.
weight_approval_repository ile AYNI dedup ilkesi (Faz 229)."""
from uuid import uuid4

from contracts.strategy_gate_approval import StrategyGateApproval
from database.repositories.strategy_gate_approval_repository import (
    StrategyGateApprovalModel,
    StrategyGateApprovalRepository,
)
from database.session_factory import SessionFactory


def _approval(strategy: str, regime: str, status: str = "pending") -> StrategyGateApproval:
    return StrategyGateApproval(
        strategy=strategy, market_regime=regime,
        sample_size=50, win_rate=0.5, rest_win_rate=0.8, delta_vs_rest=-0.3, p_value=0.001,
        replicated_out_of_sample=True, status=status,
    )


def test_save_and_get_pending_roundtrip():
    strategy = f"test_strategy_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        repo.save(_approval(strategy, "bullish_high"))
        pending = repo.get_pending(limit=1000)
        assert any(p.strategy == strategy for p in pending)


def test_has_pending_or_blocked_true_for_pending():
    strategy = f"test_strategy_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        assert repo.has_pending_or_blocked(strategy, "bullish_high") is False
        repo.save(_approval(strategy, "bullish_high"))
        assert repo.has_pending_or_blocked(strategy, "bullish_high") is True
        # Farklı rejim etkilenmemeli
        assert repo.has_pending_or_blocked(strategy, "bearish_low") is False


def test_has_pending_or_blocked_true_for_blocked():
    strategy = f"test_strategy_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        repo.save(_approval(strategy, "bullish_high", status="blocked"))
        assert repo.has_pending_or_blocked(strategy, "bullish_high") is True


def test_has_pending_or_blocked_false_for_dismissed():
    strategy = f"test_strategy_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        repo.save(_approval(strategy, "bullish_high", status="dismissed"))
        assert repo.has_pending_or_blocked(strategy, "bullish_high") is False


def test_approve_sets_status_to_blocked_and_list_blocked_pairs_includes_it():
    strategy = f"test_strategy_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        approval = _approval(strategy, "bullish_high")
        repo.save(approval)
        repo.approve(str(approval.id), approved_by="test_human")

        row = session.query(StrategyGateApprovalModel).filter_by(id=approval.id).first()
        assert row.status == "blocked"
        assert row.approved_by == "test_human"

        pairs = repo.list_blocked_pairs()
        assert (strategy, "bullish_high") in pairs


def test_auto_reject_stale_dismisses_old_pending_rows():
    strategy = f"test_strategy_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        repo.save(_approval(strategy, "bullish_high"))
        dismissed_count = repo.auto_reject_stale(max_age_seconds=0)
        assert dismissed_count >= 1

        row = session.query(StrategyGateApprovalModel).filter_by(strategy=strategy).first()
        assert row.status == "dismissed"
