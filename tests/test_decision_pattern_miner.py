"""Decision Pattern Miner testleri."""
import json

from services.decision_pattern_miner import DecisionPatternMiner


def test_mine_patterns_finds_winning(tmp_path):
    miner = DecisionPatternMiner(storage_path=str(tmp_path))

    for i in range(5):
        log = {
            "id": f"dec_{i}",
            "belief": {"direction": "LONG", "confidence": 0.8},
            "outcome": {"pnl": 100 if i < 4 else -50}
        }
        (tmp_path / f"decision_{i}.json").write_text(json.dumps(log))

    patterns = miner.mine_patterns(min_occurrences=3, min_win_rate=0.6)
    assert len(patterns) >= 1
    assert patterns[0]["pattern"] == "LONG_high"
    assert patterns[0]["win_rate"] == 0.8

def test_mine_patterns_empty(tmp_path):
    miner = DecisionPatternMiner(storage_path=str(tmp_path))
    patterns = miner.mine_patterns()
    assert patterns == []
