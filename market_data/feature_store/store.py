"""Merkezi özellik deposu."""
from datetime import datetime
from typing import Any


class FeatureStore:
    def __init__(self):
        self._features: dict[str, dict[str, Any]] = {}
        self._definitions: dict[str, dict[str, Any]] = {}

    def register(self, name: str, version: str, definition: str, source: str):
        self._definitions[name] = {"version": version, "definition": definition, "source": source}

    def set(self, symbol: str, feature_name: str, value: float, timestamp: datetime):
        key = f"{symbol}:{feature_name}"
        self._features[key] = {"value": value, "timestamp": timestamp}

    def get(self, symbol: str, feature_name: str) -> dict[str, Any] | None:
        return self._features.get(f"{symbol}:{feature_name}")
