"""Training Intelligence testleri."""
import json
import shutil
from pathlib import Path
from services.training_intelligence import TrainingIntelligence
from services.decision_recorder import DecisionRecorder
from services.outcome_tracker import OutcomeTracker
from contracts.context import CognitiveCycleContext
from contracts.outcome import TradeOutcome

def test_generate_training_data():
    test_path = "test_intelligence_logs"
    Path(test_path).mkdir(exist_ok=True)
    
    recorder = DecisionRecorder(storage_path=test_path)
    tracker = OutcomeTracker(storage_path=test_path)
    intelligence = TrainingIntelligence(storage_path=test_path)
    
    # 1. Karar kaydet
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "features": {"RSI": 45}},
        decision={"proposed_size": 0.1},
    )
    event = recorder.record(ctx, [])
    
    # 2. Outcome ekle
    tracker.attach_outcome(str(event.id), TradeOutcome(pnl=10.0, win=True))
    
    # 3. Eğitim verisi üret
    output_file = "test_training_dataset.jsonl"
    result = intelligence.generate_training_data(output_path=output_file)
    
    assert result["sample_count"] == 1
    assert Path(output_file).exists()
    
    # Veriyi kontrol et
    with open(output_file, "r") as f:
        data = json.loads(f.readline())
        assert data["label_pnl"] == 10.0
        assert data["features"]["market_RSI"] == 45
    
    # Temizlik
    shutil.rmtree(test_path, ignore_errors=True)
    Path(output_file).unlink(missing_ok=True)
