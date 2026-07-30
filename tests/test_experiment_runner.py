"""Experiment Runner testleri."""
from contracts.curiosity import ExperimentProposal
from contracts.memory import EpisodicMemory, SemanticMemory
from services.experiment_runner import ExperimentRunner


def test_enqueue_and_run():
    em = EpisodicMemory()
    sm = SemanticMemory()
    runner = ExperimentRunner(em, sm)

    proposal = ExperimentProposal(
        hypothesis="Test hypothesis",
        test_expression="RSI < 30",
        estimated_value=0.8,
    )
    runner.enqueue(proposal)
    assert runner.queue_size() == 1

    episodes = runner.run_all()
    assert len(episodes) == 1
    assert episodes[0].binding_expression == "RSI < 30"
    assert runner.queue_size() == 0

def test_runner_updates_semantic():
    em = EpisodicMemory()
    sm = SemanticMemory()
    sm.add_belief("RSI < 30", 0.7)
    runner = ExperimentRunner(em, sm)

    proposal = ExperimentProposal(
        hypothesis="Test",
        test_expression="RSI < 30",
        estimated_value=0.8,
    )
    runner.enqueue(proposal)
    runner.run_all()
    assert len(em.episodes) == 1
    assert sm.total_episodes >= 0
