"""Knowledge Base — InformationGraph üzerine kurulu, deterministik bilgi deposu."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from contracts.information_graph import InformationGraph, NodeType, SourceType


class WisdomEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    category: str
    principle: str
    source: str
    confidence: float = Field(ge=0.0, le=1.0)
    validated: bool = True
    invalidated: bool = False
    validation_count: int = 0
    rejection_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class KnowledgeBase:
    """Deterministik trading bilgisi deposu. LLM kullanmaz."""

    def __init__(self):
        self.graph = InformationGraph()
        self.wisdom_entries: list[WisdomEntry] = []
        self._seed_principles()

    def _seed_principles(self):
        principles = [
            ("risk_management", "Kelly Criterion: never risk more than fraction of bankroll", "classical", 0.95),
            ("expected_value", "Expected Value > 0 is necessary but not sufficient", "classical", 0.90),
            ("risk_management", "Drawdown > 20% requires position size halving", "risk_policy", 0.85),
            ("signal_processing", "Correlated signals should not increase confidence linearly", "epistemics", 0.88),
        ]
        for category, principle, source, confidence in principles:
            self.add_wisdom(category, principle, source, confidence)

    def add_wisdom(self, category: str, principle: str, source: str, confidence: float) -> WisdomEntry:
        entry = WisdomEntry(
            category=category,
            principle=principle,
            source=source,
            confidence=confidence,
        )
        self.wisdom_entries.append(entry)
        node_id = f"wisdom_{entry.id}"
        self.graph.add_node(
            id=node_id,
            source_type=SourceType.EXPERT_OPINION,
            node_type=NodeType.TRANSFORMATION,
            description=f"[{category}] {principle}",
            parents=["technical_agent"] if "signal" in category else ["quant_agent"],
        )
        return entry

    def query_relevant(self, market_context: dict, decision_context: dict) -> list[dict]:
        symbol = market_context.get("symbol", "")
        features = market_context.get("features", {}) or {}
        regime = features.get("regime", "")

        results: list[dict] = []
        for entry in self.wisdom_entries:
            score = self._relevance_score(entry, symbol, regime, features)
            if score > 0:
                results.append({
                    "type": "wisdom",
                    "id": str(entry.id),
                    "category": entry.category,
                    "principle": entry.principle,
                    "confidence": entry.confidence,
                    "relevance": round(score, 3),
                })

        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results

    def _relevance_score(self, entry: WisdomEntry, symbol: str, regime: str, features: dict) -> float:
        score = 0.0
        principle_lower = entry.principle.lower()

        if entry.category == "risk_management":
            drawdown = features.get("drawdown", 0.0)
            if drawdown and drawdown > 0.15:
                score += 0.4
            score += 0.2

        if entry.category == "expected_value":
            score += 0.1

        if entry.category == "signal_processing":
            correlation = features.get("correlation", 0.0)
            num_signals = features.get("num_signals", 0)
            if correlation and abs(correlation) > 0.5:
                score += 0.3
            if num_signals and num_signals > 1:
                score += 0.2
            score += 0.1

        if regime and regime in principle_lower:
            score += 0.2

        if symbol and symbol.lower() in principle_lower:
            score += 0.1

        if not entry.validated or entry.invalidated:
            score = score * 0.5

        return min(score, 1.0)

    def validate_lesson(self, lesson_id: str, outcome: dict) -> bool:
        entry = self._find_entry(lesson_id)
        if entry is None:
            return False

        pnl = outcome.get("pnl", 0.0)
        was_profitable = pnl > 0

        if was_profitable:
            entry.validation_count += 1
            entry.confidence = min(1.0, entry.confidence + 0.02)
        else:
            entry.rejection_count += 1
            entry.confidence = max(0.0, entry.confidence - 0.05)

        if entry.rejection_count >= 3 and entry.rejection_count > entry.validation_count:
            entry.invalidated = True
            entry.validated = False
        elif entry.validation_count >= 3 and entry.validation_count > entry.rejection_count:
            entry.validated = True
            entry.invalidated = False

        return entry.validated and not entry.invalidated

    def _find_entry(self, lesson_id: str) -> WisdomEntry | None:
        for entry in self.wisdom_entries:
            if str(entry.id) == lesson_id:
                return entry
        return None
