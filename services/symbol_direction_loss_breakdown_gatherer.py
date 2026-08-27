"""Backlog #14 (2026-08-26) — kullanıcı örneği: "BTC LONG'da 100 pozisyon,
15'i stop olmuş, 13'ü yön hatası, 2'si stop süpürülüp sonra hedefe
gitmiş." Gerçek hesaplama analytics/failure_classifier.py::
summarize_loss_breakdown_by_symbol_direction()'da — services/
loss_breakdown_gatherer.py ile AYNI ince wrapper deseni, Genel Özet
panelinin diğer modülleriyle tutarlı."""
from analytics.failure_classifier import summarize_loss_breakdown_by_symbol_direction


def gather_symbol_direction_loss_breakdown() -> dict:
    return summarize_loss_breakdown_by_symbol_direction(hours=None)
