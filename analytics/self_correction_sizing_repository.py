"""Faz 368 — kullanıcı kararı: LONG'un son dönem çöküşü (96.4%→71.5%,
hypothesis_still_valid=false) tespit edildiğinde o yönün pozisyon boyutu
kademeli küçültülsün. analytics/barrier_table_repository.py ile AYNI
dosya-tabanlı, tek "en son" anlık görüntü deseni — öğrenilmiş bir
artefakt, Class 2 audit verisi değil, bu yüzden ayrı bir Alembic
migration/DB tablosu YOK. services/scientific_self_correction_gatherer.py
zaten ucuz (~0.1sn) ama karar döngüsünde SEMBOL BAŞINA (döngü başına
değil) tekrar tekrar çağrılması gereksiz — barrier table/agent
combination reliability ile AYNI "periyodik hesapla, kaydet, karar anında
sadece oku" ilkesi."""
import json
import os
from datetime import UTC, datetime
from pathlib import Path

_DEFAULT_STORAGE_PATH = os.environ.get("SELF_CORRECTION_SIZING_STORAGE_PATH", "self_correction_sizing_history")


class SelfCorrectionSizingRepository:
    def __init__(self, storage_path: str = _DEFAULT_STORAGE_PATH):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)

    def save(self, segments: dict) -> None:
        payload = {
            "built_at": datetime.now(UTC).isoformat(),
            "segments": segments,
        }
        (self.storage_path / "latest.json").write_text(json.dumps(payload, indent=2))

    def get_latest(self) -> dict | None:
        file = self.storage_path / "latest.json"
        if not file.exists():
            return None
        try:
            return json.loads(file.read_text())
        except (json.JSONDecodeError, OSError):
            return None
