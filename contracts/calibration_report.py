"""Probability Calibration (ECE) haftalık rapor kaydı — Cognitive Core 2.0 / M4.

analytics/calibration_uncertainty.py::compute_expected_calibration_error()
gerçek zamanlı çalışıyor (GET /calibration/) ama hiçbir geçmişi yoktu — bu
tablo periyodik (haftalık) anlık görüntüleri saklıyor, Feature IC/LLM
Audit ile AYNI desen.

Kasıtlı olarak SADECE ölçüm/rapor — council'in hiçbir kararını etkilemiyor,
hiçbir agent'ın confidence'ını otomatik düzeltmiyor. "Ajan %70 dediğinde
gerçekten %70 mi doğru çıkıyor" sorusuna insan-okunur bir cevap."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CalibrationReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # compute_expected_calibration_error()'ın çıktısı: {"expected_calibration_error": float, "sample_size": int, "bins": [...]}
    result: dict | None = None
    total_closed_trades: int = 0
