"""Harici veri kaynakları (on‑chain, sentiment, macro) stub."""
from datetime import datetime
from typing import Any


class ExternalDataIngestor:
    async def fetch_onchain(self, metric: str) -> dict[str, Any]:
        return {"metric": metric, "value": 0.0, "timestamp": datetime.now()}

    async def fetch_sentiment(self, source: str) -> dict[str, Any]:
        return {"source": source, "score": 0.0, "timestamp": datetime.now()}

    async def fetch_macro(self, indicator: str) -> dict[str, Any]:
        return {"indicator": indicator, "value": 0.0, "timestamp": datetime.now()}
