"""Self-Designing Intelligence Guard testleri — Cognitive Core 11.0."""
import pytest

from analytics.self_designing_guard import AIProposal


def test_a_real_human_identity_can_approve():
    proposal = AIProposal(proposal_type="adaptive_barrier", payload={"sl_pct": 0.02})
    proposal.approve(approved_by="emre")
    assert proposal.status == "approved"
    assert proposal.approved_by == "emre"
    assert proposal.decided_at is not None


def test_empty_approver_is_rejected():
    proposal = AIProposal(proposal_type="moe_router", payload={})
    with pytest.raises(ValueError):
        proposal.approve(approved_by="")


def test_none_approver_is_rejected():
    proposal = AIProposal(proposal_type="moe_router", payload={})
    with pytest.raises(ValueError):
        proposal.approve(approved_by=None)


@pytest.mark.parametrize("fake_identity", ["ai", "system", "auto", "bot", "Claude", "AI", " system "])
def test_non_human_identities_cannot_self_approve(fake_identity):
    proposal = AIProposal(proposal_type="optimal_barrier", payload={})
    with pytest.raises(ValueError):
        proposal.approve(approved_by=fake_identity)


def test_reject_also_requires_a_real_human_identity():
    proposal = AIProposal(proposal_type="optimal_barrier", payload={})
    with pytest.raises(ValueError):
        proposal.reject(rejected_by="system")

    proposal.reject(rejected_by="emre")
    assert proposal.status == "rejected"
    assert proposal.approved_by == "emre"


def test_proposal_starts_pending():
    proposal = AIProposal(proposal_type="moe_router", payload={"gamma": 1.5})
    assert proposal.status == "pending"
    assert proposal.approved_by is None
