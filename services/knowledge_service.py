"""Knowledge Service — append-only bilgi deposu."""
from contracts.knowledge import KnowledgeEntry


class KnowledgeService:
    def __init__(self):
        self._entries: list[KnowledgeEntry] = []

    def record(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        self._entries.append(entry)
        return entry

    def query(self, category: str | None = None, symbol: str | None = None) -> list[KnowledgeEntry]:
        results = self._entries
        if category:
            results = [e for e in results if e.category == category]
        if symbol:
            results = [e for e in results if e.symbol == symbol]
        return results

    def get_statistics(self, symbol: str | None = None) -> dict:
        entries = self.query(symbol=symbol)
        trade_entries = [e for e in entries if e.category == "trade_result"]
        total = len(trade_entries)
        wins = sum(1 for e in trade_entries if e.result.get("pnl", 0) > 0)
        return {
            "total_entries": len(entries),
            "total_trades": total,
            "win_rate": wins / total if total > 0 else 0.0,
            "avg_confidence": sum(e.result.get("confidence", 0) for e in trade_entries) / total if total > 0 else 0.0,
        }
