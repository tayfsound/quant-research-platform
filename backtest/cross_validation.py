"""Zaman serisi çapraz doğrulama."""
from sklearn.model_selection import TimeSeriesSplit


def time_series_cv(n_splits: int = 5):
    return TimeSeriesSplit(n_splits=n_splits)

def out_of_sample_test(data: list, train_ratio: float = 0.8) -> tuple[list, list]:
    split = int(len(data) * train_ratio)
    return data[:split], data[split:]

def rolling_window(data: list, window_size: int = 30, step: int = 1):
    for i in range(0, len(data) - window_size + 1, step):
        yield data[i:i + window_size]
