import random


class ReplaySeedManager:

    def set_seed(self, seed: int):
        random.seed(seed)

    def generate(self) -> int:
        return random.randint(
            1,
            2**31 - 1
        )
