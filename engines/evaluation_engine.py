"""Evaluation Engine — öz değerlendirme + merak + deney çalıştırma."""
from contracts.context import CognitiveCycleContext
from services.self_evaluator import SelfEvaluator
from services.curiosity_engine import CuriosityEngine
from services.experiment_runner import ExperimentRunner
from services.memory_consolidator import MemoryConsolidator

class EvaluationEngine:
    def __init__(self, consolidator: MemoryConsolidator):
        self.consolidator = consolidator
        self.evaluator = SelfEvaluator(consolidator.episodic, consolidator.semantic)
        self.curiosity = CuriosityEngine(consolidator.episodic)
        self.runner = ExperimentRunner(consolidator.episodic, consolidator.semantic)
        self.evaluation_count = 0

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        self.evaluation_count += 1

        if self.evaluation_count % 10 != 0:
            return ctx

        # 1. Öz değerlendirme
        analysis = self.evaluator.analyze_outcomes()
        adjustments = self.evaluator.adjust_beliefs(analysis)
        lessons = self.evaluator.generate_lessons(analysis, adjustments)

        # 2. Merak sinyalleri → deney önerileri
        proposals = self.curiosity.analyze_and_generate(analysis, adjustments)

        # 3. En yüksek öncelikli 2 deneyi kuyruğa al ve çalıştır
        top = self.curiosity.top_proposals(2)
        for p in top:
            self.runner.enqueue(p)
        self.runner.run_all()

        # 4. Sonuçları context'e yaz
        ctx.cognition.relevant_knowledge.append({
            "type": "self_evaluation",
            "data": {
                "win_rate": analysis.win_rate,
                "adjustments": len(adjustments),
                "lessons": len(lessons),
                "top_errors": analysis.top_error_conditions,
                "experiment_proposals": len(proposals),
                "experiments_run": len(top),
            }
        })

        return ctx
