"""analytics/symbol_performance_sizing_repository.py — self_correction_
sizing_repository.py ile AYNI dosya-tabanlı desen."""
from analytics.symbol_performance_sizing_repository import SymbolPerformanceSizingRepository


def test_no_saved_snapshot_returns_none(tmp_path):
    repo = SymbolPerformanceSizingRepository(storage_path=str(tmp_path / "symbol_perf"))
    assert repo.get_latest() is None


def test_save_and_get_latest_roundtrip(tmp_path):
    repo = SymbolPerformanceSizingRepository(storage_path=str(tmp_path / "symbol_perf"))
    by_symbol_direction = {"ATOMUSDT_LONG": {"win_rate": 0.3171, "sample_size": 41, "total_pnl": -38204.84}}
    repo.save(by_symbol_direction)

    stored = repo.get_latest()
    assert stored is not None
    assert stored["by_symbol_direction"] == by_symbol_direction
    assert "built_at" in stored
