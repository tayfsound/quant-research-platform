"""Faz 363 — backlog #15: "kâr edip zarara dönen pozisyonların ne kadarı
stop yanlış yerleştirildiği için, ne kadarı gerçek yön hatası" + "bu
kaybın toplam zarardaki payı % olarak dashboard'a kart olarak eklenmeli
(SL/likidasyon/breakeven kırılımı)". Gerçek hesaplama analytics/
failure_classifier.py::summarize_loss_breakdown()'da — burada, Genel
Özet panelinin (services/research_summary_gatherer.py) diğer 15 modülüyle
AYNI ince wrapper deseni."""
from analytics.failure_classifier import summarize_loss_breakdown


def gather_loss_breakdown() -> dict:
    return summarize_loss_breakdown(hours=None)
