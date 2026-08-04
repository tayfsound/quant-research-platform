"""Walk-forward index splitter with a mandatory embargo gap between train and
test windows, so a lookback-window feature computed near the train/test
boundary can never leak future (test-side) bars into a training signal, or
past (train-side) bars whose label depends on test-side outcomes.

Deliberately separate from backtest.walk_forward.WalkForwardEngine (which
operates directly on a single price list + strategy callable, embargo=0
always) rather than modifying it in place — this one just produces index
ranges over a symbol/time matrix for the vectorized engine to slice.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardSplit:
    train_start: int
    train_end: int  # exclusive
    test_start: int  # exclusive of the embargo gap
    test_end: int  # exclusive


class EmbargoWalkForwardSplitter:
    def __init__(self, train_size: int, test_size: int, step: int, embargo: int = 0):
        if train_size <= 0 or test_size <= 0 or step <= 0:
            raise ValueError("train_size, test_size, step must all be positive")
        if embargo < 0:
            raise ValueError("embargo must be >= 0")
        self.train_size = train_size
        self.test_size = test_size
        self.step = step
        self.embargo = embargo

    def split(self, n_bars: int) -> list[WalkForwardSplit]:
        splits = []
        i = 0
        while True:
            train_start = i
            train_end = i + self.train_size
            test_start = train_end + self.embargo
            test_end = test_start + self.test_size
            if test_end > n_bars:
                break
            splits.append(WalkForwardSplit(train_start, train_end, test_start, test_end))
            i += self.step
        return splits
