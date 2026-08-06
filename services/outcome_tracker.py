from pathlib import Path

from services.training_dataset_builder import TrainingDatasetBuilder


class OutcomeTracker:
    """Faz 211 temizliği: attach_outcome() (LearningLoop.process_outcome()'un
    tek tüketicisiydi) kaldırıldı — hem tetikleyen tek mekanizma
    (PendingOutcomeTracker.run_scheduler) hiç başlatılmıyordu, hem de
    kendisi DecisionEvent'i agent_opinions=[] ile kuruyordu (gerçek ajan
    görüşlerini hiç okumuyordu). Gerçek pozisyon kapanışlarının öğrenme
    döngüsüne geri beslenmesi artık services/position_closer.py'de,
    doğru veriyle (decisions.agent_contributions) yapılıyor."""

    def __init__(self, storage_path="decision_logs"):
        self.storage_path = Path(storage_path)

    def build_training_dataset(self, output_path="training_data.jsonl"):
        return TrainingDatasetBuilder().build(output_path)
