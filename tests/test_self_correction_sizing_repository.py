"""analytics/self_correction_sizing_repository.py — barrier_table_
repository.py ile AYNI dosya-tabanlı desen."""
from analytics.self_correction_sizing_repository import SelfCorrectionSizingRepository


def test_no_saved_snapshot_returns_none(tmp_path):
    repo = SelfCorrectionSizingRepository(storage_path=str(tmp_path / "self_correction_sizing"))
    assert repo.get_latest() is None


def test_save_and_get_latest_roundtrip(tmp_path):
    repo = SelfCorrectionSizingRepository(storage_path=str(tmp_path / "self_correction_sizing"))
    segments = {"direction=LONG": {"hypothesis_still_valid": False, "original_win_rate": 0.96, "recent_win_rate": 0.71}}
    repo.save(segments)

    stored = repo.get_latest()
    assert stored is not None
    assert stored["segments"] == segments
    assert "built_at" in stored
