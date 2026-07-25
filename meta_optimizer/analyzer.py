"""Periyodik analiz: LLMExplainerPort üzerinden (ortak logic)."""
from contracts.llm import LLMExplainerPort
from contracts.repositories import ExperimentLogRepository


class PromptAnalyzer:
    def __init__(self, repository: ExperimentLogRepository, explainer: LLMExplainerPort):
        self.repository = repository
        self.explainer = explainer

    async def analyze_and_suggest(self, current_prompt: str) -> dict:
        recent = self.repository.get_recent(50)
        if len(recent) < 10:
            return {
                "analysis": "Not enough data",
                "new_system_prompt": current_prompt,
                "expected_improvement": "N/A",
            }

        summary = []
        for log in recent:
            summary.append({
                "symbol": log.symbol,
                "direction": log.direction,
                "confidence": log.confidence,
                "explanation": log.llm_explanation.get("explanation", "")[:100],
                "was_correct": log.outcome.get("was_correct", None),
            })

        return await self.explainer.analyze_logs(summary, current_prompt)
