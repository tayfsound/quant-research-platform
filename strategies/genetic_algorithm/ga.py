"""Genetic Algorithm."""
import random
from typing import Dict, Callable, Any
from dataclasses import dataclass

@dataclass
class Individual:
    params: Dict[str, float]
    fitness: float = 0.0

class GeneticAlgorithm:
    def __init__(self, population_size: int = 20):
        self.population_size = population_size
        self.best: Individual = None
        self._population: list = []
    
    def initialize(self, param_ranges: Dict[str, tuple]) -> None:
        self._population = []
        for _ in range(self.population_size):
            params = {k: random.uniform(v[0], v[1]) for k, v in param_ranges.items()}
            self._population.append(Individual(params=params))
    
    def evolve(self, fitness_fn: Callable[[Dict[str, float]], float], generations: int = 10) -> Individual:
        for _ in range(generations):
            for ind in self._population:
                ind.fitness = fitness_fn(ind.params)
            self._population.sort(key=lambda x: x.fitness, reverse=True)
            self.best = self._population[0]
            elites = self._population[:4]
            offspring = []
            while len(offspring) < self.population_size - 4:
                p1, p2 = random.sample(elites, 2)
                child_params = {k: p1.params[k] if random.random() < 0.5 else p2.params[k] for k in p1.params}
                child_params = {k: v * random.uniform(0.9, 1.1) if random.random() < 0.1 else v for k, v in child_params.items()}
                offspring.append(Individual(params=child_params))
            self._population = elites + offspring
        return self.best
