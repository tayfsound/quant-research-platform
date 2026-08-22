"""Basit genetik algoritma."""
import random
from collections.abc import Callable


class GeneticOptimizer:
    def __init__(self, population_size: int = 20, generations: int = 10, mutation_rate: float = 0.1):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate

    def _random_individual(self) -> dict[str, float]:
        return {
            "rsi_threshold": random.uniform(20, 40),
            "confidence_min": random.uniform(0.5, 0.9),
            "position_size": random.uniform(0.1, 1.0),
        }

    def _fitness(self, individual: dict, evaluator: Callable) -> float:
        return evaluator(individual)

    def _crossover(self, a: dict, b: dict) -> dict:
        return {k: a[k] if random.random() < 0.5 else b[k] for k in a}

    def _mutate(self, individual: dict) -> dict:
        return {k: v * random.uniform(0.9, 1.1) if random.random() < self.mutation_rate else v for k, v in individual.items()}

    def optimize(self, evaluator: Callable) -> dict[str, float]:
        population = [self._random_individual() for _ in range(self.population_size)]
        for _ in range(self.generations):
            scored = sorted([(self._fitness(ind, evaluator), i, ind) for i, ind in enumerate(population)], reverse=True)
            elites = [ind for _, _, ind in scored[:4]]
            offspring = []
            while len(offspring) < self.population_size - 4:
                p1, p2 = random.sample(elites, 2)
                offspring.append(self._mutate(self._crossover(p1, p2)))
            population = elites + offspring
        return max(population, key=lambda x: self._fitness(x, evaluator))
