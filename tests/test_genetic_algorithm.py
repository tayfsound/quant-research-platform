from strategies.genetic_algorithm import GeneticOptimizer

def test_genetic_optimizer():
    best = GeneticOptimizer(population_size=10, generations=5).optimize(lambda i: i["confidence_min"] * 10 - i["rsi_threshold"])
    assert "rsi_threshold" in best
