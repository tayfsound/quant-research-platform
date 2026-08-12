"""Faz 250: Live A/B Testing Framework."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.ab_testing import assign_bucket, evaluate_experiment, welch_t_test


def test_assign_bucket_returns_only_control_or_treatment():
    results = {assign_bucket() for _ in range(200)}
    assert results <= {"control", "treatment"}


def test_assign_bucket_is_roughly_balanced_over_many_trials():
    """Kesin %50/%50 değil (gerçekten rastgele), ama 2000 denemede ~%50'ye
    yakın olmalı — sistemli bir sapma (ör. hep control) yoksa."""
    control_count = sum(1 for _ in range(2000) if assign_bucket() == "control")
    assert 800 < control_count < 1200


def test_assign_bucket_respects_control_weight():
    control_count = sum(1 for _ in range(500) if assign_bucket(control_weight=0.9) == "control")
    assert control_count > 400  # ~%90 civarı, gevşek bir alt sınır


def test_welch_t_test_returns_none_for_too_few_samples():
    result = welch_t_test([1.0], [1.0, 2.0, 3.0])
    assert result["t_statistic"] is None
    assert result["p_value"] is None
    assert result["significant"] is None


def test_welch_t_test_finds_no_significance_for_identical_distributions():
    sample = [1.0, 2.0, 3.0, 4.0, 5.0] * 5
    result = welch_t_test(sample, sample)
    assert result["p_value"] == 1.0
    assert result["significant"] is False


def test_welch_t_test_finds_significance_for_clearly_different_distributions():
    import random

    rng = random.Random(7)
    low = [rng.gauss(0.0, 1.0) for _ in range(200)]
    high = [rng.gauss(10.0, 1.0) for _ in range(200)]
    result = welch_t_test(high, low)
    assert result["significant"] is True
    assert result["p_value"] < 0.05
    assert result["t_statistic"] > 0  # high > low


def test_evaluate_experiment_returns_insufficient_data_below_threshold():
    experiment = f"abtest_{uuid4().hex[:8]}"
    _seed_closed_decisions(experiment, "control", [10.0] * 5)
    _seed_closed_decisions(experiment, "treatment", [10.0] * 5)

    result = evaluate_experiment(experiment, min_samples_per_bucket=30)
    assert result["verdict"] == "insufficient_data"
    assert result["control_sample_count"] == 5
    assert result["treatment_sample_count"] == 5


def test_evaluate_experiment_promotes_treatment_when_clearly_better():
    experiment = f"abtest_{uuid4().hex[:8]}"
    _seed_closed_decisions(experiment, "control", [-5.0] * 40)
    _seed_closed_decisions(experiment, "treatment", [15.0] * 40)

    result = evaluate_experiment(experiment, min_samples_per_bucket=30)
    assert result["verdict"] == "promote_treatment"
    assert result["treatment_avg_pnl"] > result["control_avg_pnl"]


def test_evaluate_experiment_recommends_rollback_when_treatment_is_worse():
    experiment = f"abtest_{uuid4().hex[:8]}"
    _seed_closed_decisions(experiment, "control", [15.0] * 40)
    _seed_closed_decisions(experiment, "treatment", [-5.0] * 40)

    result = evaluate_experiment(experiment, min_samples_per_bucket=30)
    assert result["verdict"] == "rollback_treatment"


def test_evaluate_experiment_finds_no_significant_difference_for_similar_buckets():
    experiment = f"abtest_{uuid4().hex[:8]}"
    import random

    rng = random.Random(3)
    _seed_closed_decisions(experiment, "control", [rng.gauss(1.0, 5.0) for _ in range(50)])
    _seed_closed_decisions(experiment, "treatment", [rng.gauss(1.0, 5.0) for _ in range(50)])

    result = evaluate_experiment(experiment, min_samples_per_bucket=30)
    assert result["verdict"] == "no_significant_difference"


def _seed_closed_decisions(experiment: str, bucket: str, pnls: list[float]) -> None:
    symbol = f"ABTEST{uuid4().hex[:6]}"
    now = datetime.now(UTC)
    for pnl in pnls:
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
            final_size=1.0, confidence=0.6, status="open", entry_price=100.0, quantity=1.0,
            experiment_bucket=f"{experiment}:{bucket}",
        )
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            repo.persist(event)
            repo.close_position(decision_id=str(event.id), exit_price=100.0, pnl=pnl, closed_at=now)
