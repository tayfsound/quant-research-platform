"""Genetik algoritma motoru."""
import random
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import numpy as np


@dataclass
class Genome:
    id: UUID = field(default_factory=uuid4)
    parameters: dict[str, float] = field(default_factory=dict)
    fitness: float | None = None
    generation: int = 0
    parent_ids: list[UUID] = field(default_factory=list)

class GeneticAlgorithm:
    def __init__(self, population_size: int = 100, mutation_rate: float = 0.1, crossover_rate: float = 0.7):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.population: list[Genome] = []

    def initialize(self, base_params: dict[str, tuple[float, float]]):
        self.population = []
        for _ in range(self.population_size):
            params = {k: random.uniform(v[0], v[1]) for k, v in base_params.items()}
            self.population.append(Genome(parameters=params))

    def evaluate_fitness(self, fitness_func):
        for genome in self.population:
            genome.fitness = fitness_func(genome.parameters)

    def select_parents(self) -> list[Genome]:
        fitnesses = [g.fitness or 0.0 for g in self.population]
        total = sum(fitnesses)
        if total == 0:
            return random.sample(self.population, 2)
        probs = [f / total for f in fitnesses]
        indices = np.random.choice(len(self.population), size=2, p=probs, replace=False)
        return [self.population[i] for i in indices]

    def crossover(self, p1: Genome, p2: Genome) -> Genome:
        child_params = {}
        for key in p1.parameters:
            if random.random() < 0.5:
                child_params[key] = p1.parameters[key]
            else:
                child_params[key] = p2.parameters[key]
        return Genome(parameters=child_params, parent_ids=[p1.id, p2.id])

    def mutate(self, genome: Genome) -> Genome:
        for key in genome.parameters:
            if random.random() < self.mutation_rate:
                genome.parameters[key] *= random.uniform(0.8, 1.2)
        return genome

    def evolve(self, fitness_func, generations: int = 10):
        self.evaluate_fitness(fitness_func)
        for gen in range(generations):
            new_population: list[Genome] = []
            # Elitizm: en iyi 2 birey olduğu gibi kalsın
            self.population.sort(key=lambda g: g.fitness or 0.0, reverse=True)
            new_population.append(self.population[0])
            new_population.append(self.population[1])

            while len(new_population) < self.population_size:
                parents = self.select_parents()
                child = self.crossover(parents[0], parents[1])
                child = self.mutate(child)
                child.generation = gen + 1
                new_population.append(child)

            self.population = new_population
            self.evaluate_fitness(fitness_func)

    @property
    def best(self) -> Genome | None:
        if not self.population:
            return None
        return max(self.population, key=lambda g: g.fitness or 0.0)
