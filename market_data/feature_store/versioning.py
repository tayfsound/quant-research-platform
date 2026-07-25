"""Özellik versiyonlama ve backfill yardımcısı."""
from datetime import datetime


class FeatureVersion:
    def __init__(self, name: str, version: str, definition_hash: str):
        self.name = name
        self.version = version
        self.definition_hash = definition_hash
        self.created_at = datetime.now()

    def is_compatible(self, other: "FeatureVersion") -> bool:
        return self.definition_hash == other.definition_hash
