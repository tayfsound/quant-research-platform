"""RL ve GA testleri."""

def test_ga_evolution():
    from strategies.genetic_algorithm.ga import GeneticAlgorithm
    ga = GeneticAlgorithm(population_size=20)
    ga.initialize({"rsi_period": (5.0, 30.0), "ema_fast": (5.0, 50.0)})
    def dummy_fitness(params):
        return sum(params.values())
    ga.evolve(dummy_fitness, generations=3)
    assert ga.best is not None
    assert ga.best.fitness is not None

def test_ensemble_voting():
    from uuid import uuid4

    from strategies.definitions.ensemble import AgentVote, WeightedVoting
    voting = WeightedVoting()
    agent_id = uuid4()
    voting.set_weight(agent_id, 1.0)
    votes = [AgentVote(agent_id=agent_id, direction=1, confidence=0.8)]
    decision = voting.decide(votes)
    assert decision.direction == 1
