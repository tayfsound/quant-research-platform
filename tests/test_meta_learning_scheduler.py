"""Faz 239-241: services/meta_learning_scheduler.py'nin insan-onay-kapısı
mantığı — test_weight_approval_e2e.py ile aynı desende, gerçek DB'ye
karşı. CMA-ES'in kendisi çok yavaş olduğu için (walk_forward_validate,
her fold'da ayrı bir CMA-ES araması yapıyor) burada
optimize_technical_agent_coefficients/walk_forward_validate monkeypatch'le
sahtelendi — bu dosyanın amacı CMA-ES matematiğini değil (bkz.
test_agent_tuner.py), ONAY KAPISI mantığını (eşik altında öneri yok, zaten
bekleyen onay varsa tekrar önerilmiyor, onaylanınca gerçekten okunabiliyor)
test etmek."""
from uuid import uuid4

import services.meta_learning_scheduler as scheduler_module
from agents.technical_agent import TechnicalAgentCoefficients
from contracts.technical import TechnicalContext
from database.repositories.agent_tuning_approval_repository import AgentTuningApprovalRepository
from database.session_factory import SessionFactory
from meta_optimizer.agent_tuner import HistoricalTechnicalRecord


def _fake_records(n: int) -> list[HistoricalTechnicalRecord]:
    ctx = TechnicalContext(trend="bullish", market_structure="higher_highs")
    return [HistoricalTechnicalRecord(ctx, "LONG", 10.0) for _ in range(n)]


def test_propose_skips_when_not_enough_historical_records(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "load_historical_technical_records",
        lambda: _fake_records(scheduler_module.MIN_RECORDS_TO_OPTIMIZE - 1),
    )
    agent_id = f"technical_agent_v1_test_{uuid4().hex[:8]}"
    result = scheduler_module.propose_technical_agent_tuning(agent_id=agent_id)
    assert result is None


def test_propose_skips_when_walk_forward_does_not_meet_sharpe_bar(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "load_historical_technical_records",
        lambda: _fake_records(scheduler_module.MIN_RECORDS_TO_OPTIMIZE + 10),
    )
    monkeypatch.setattr(
        scheduler_module, "walk_forward_validate",
        lambda records: {
            "folds": [{}], "mean_oos_sharpe_tuned": 0.1, "mean_oos_sharpe_baseline": 0.05,
            "sharpe_improvement": 0.05, "sample_count": len(records),
        },
    )
    agent_id = f"technical_agent_v1_test_{uuid4().hex[:8]}"
    result = scheduler_module.propose_technical_agent_tuning(agent_id=agent_id)
    assert result is None

    with SessionFactory.get_session() as session:
        repo = AgentTuningApprovalRepository(session)
        assert repo.has_pending(agent_id) is False


def test_propose_creates_pending_approval_when_sharpe_bar_is_met(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "load_historical_technical_records",
        lambda: _fake_records(scheduler_module.MIN_RECORDS_TO_OPTIMIZE + 10),
    )
    monkeypatch.setattr(
        scheduler_module, "walk_forward_validate",
        lambda records: {
            "folds": [{}], "mean_oos_sharpe_tuned": 0.9, "mean_oos_sharpe_baseline": 0.2,
            "sharpe_improvement": 0.7, "sample_count": len(records),
        },
    )
    tuned = TechnicalAgentCoefficients(trend_weight=1.5)
    monkeypatch.setattr(
        scheduler_module, "optimize_technical_agent_coefficients",
        lambda records: (tuned, 1.1),
    )

    agent_id = f"technical_agent_v1_test_{uuid4().hex[:8]}"
    result = scheduler_module.propose_technical_agent_tuning(agent_id=agent_id)

    assert result is not None
    assert result.status == "pending"
    assert result.sharpe_improvement == 0.7
    assert result.proposed_coefficients["trend_weight"] == 1.5

    with SessionFactory.get_session() as session:
        repo = AgentTuningApprovalRepository(session)
        assert repo.has_pending(agent_id) is True


def test_propose_does_not_duplicate_when_a_pending_approval_already_exists(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "load_historical_technical_records",
        lambda: _fake_records(scheduler_module.MIN_RECORDS_TO_OPTIMIZE + 10),
    )
    monkeypatch.setattr(
        scheduler_module, "walk_forward_validate",
        lambda records: {
            "folds": [{}], "mean_oos_sharpe_tuned": 0.9, "mean_oos_sharpe_baseline": 0.2,
            "sharpe_improvement": 0.7, "sample_count": len(records),
        },
    )
    monkeypatch.setattr(
        scheduler_module, "optimize_technical_agent_coefficients",
        lambda records: (TechnicalAgentCoefficients(), 1.1),
    )

    agent_id = f"technical_agent_v1_test_{uuid4().hex[:8]}"
    first = scheduler_module.propose_technical_agent_tuning(agent_id=agent_id)
    second = scheduler_module.propose_technical_agent_tuning(agent_id=agent_id)

    assert first is not None
    assert second is None  # dedup — zaten bekleyen bir onay var


def test_get_approved_coefficients_is_none_without_any_approval():
    agent_id = f"technical_agent_v1_test_{uuid4().hex[:8]}"
    assert scheduler_module.get_approved_technical_agent_coefficients(agent_id=agent_id) is None


def test_get_approved_coefficients_reflects_a_real_approved_row():
    agent_id = f"technical_agent_v1_test_{uuid4().hex[:8]}"
    from contracts.agent_tuning_approval import AgentTuningApproval

    tuned = TechnicalAgentCoefficients(trend_weight=1.8, confidence_divisor=6.0)
    with SessionFactory.get_session() as session:
        repo = AgentTuningApprovalRepository(session)
        approval = AgentTuningApproval(
            agent_id=agent_id,
            proposed_coefficients=dict(tuned.__dict__),
            sharpe_improvement=0.6,
            status="pending",
        )
        repo.save(approval)
        repo.approve(str(approval.id))

    result = scheduler_module.get_approved_technical_agent_coefficients(agent_id=agent_id)
    assert result is not None
    assert result.trend_weight == 1.8
    assert result.confidence_divisor == 6.0


def test_agent_registry_uses_approved_coefficients_when_present(monkeypatch):
    """agents/registry.py::create_default()'ın onaylanmış θ'yı gerçekten
    TechnicalAgent'a geçirdiğini kanıtlıyor — DB'ye hiç dokunmadan, tek
    lookup fonksiyonunu monkeypatch'leyerek."""
    from agents.registry import AgentRegistry
    from contracts.agent import AgentDomain

    tuned = TechnicalAgentCoefficients(trend_weight=1.99)
    monkeypatch.setattr(
        scheduler_module, "get_approved_technical_agent_coefficients", lambda: tuned,
    )

    registry = AgentRegistry.create_default()
    technical_agent = registry.get(AgentDomain.TECHNICAL)

    assert technical_agent.coeffs.trend_weight == 1.99


def test_agent_registry_falls_back_to_defaults_when_no_approval_exists(monkeypatch):
    from agents.registry import AgentRegistry
    from contracts.agent import AgentDomain

    monkeypatch.setattr(
        scheduler_module, "get_approved_technical_agent_coefficients", lambda: None,
    )

    registry = AgentRegistry.create_default()
    technical_agent = registry.get(AgentDomain.TECHNICAL)

    assert technical_agent.coeffs == TechnicalAgentCoefficients()
