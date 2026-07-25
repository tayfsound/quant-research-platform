"""Walk‑forward doğrulama."""

class WalkForwardValidator:
    def __init__(self, train_window: int = 180, test_window: int = 30, embargo: int = 2):
        self.train_window = train_window
        self.test_window = test_window
        self.embargo = embargo

    def split(self, data: list[dict]) -> list[tuple[list[dict], list[dict]]]:
        splits = []
        i = 0
        while i + self.train_window + self.embargo + self.test_window <= len(data):
            train = data[i:i + self.train_window]
            test_start = i + self.train_window + self.embargo
            test = data[test_start:test_start + self.test_window]
            splits.append((train, test))
            i += self.test_window
        return splits
