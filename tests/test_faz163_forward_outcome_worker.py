"""Faz 163: ForwardOutcome Worker.

Faz 211 temizliği: PendingOutcomeTracker'ı egzersiz eden testler kaldırıldı
— tracker'ın kendisi silindi (bkz. services/position_closer.py'nin gerçek
kapanış öğrenme bağlantısı, hiç başlatılmayan bu eski scheduler'ın yerini
aldı)."""
from market_data.ingestion.mock_adapter import MockOHLCVAdapter
from services.forward_outcome import ForwardOutcome

def test_forward_outcome_with_fee():
    fo = ForwardOutcome(bars_forward=5)
    adapter = MockOHLCVAdapter(seed=42)
    data = adapter.generate(10)

    result = fo.calculate(100.0, "LONG", data, fee=0.001)
    assert result["pending"] is False
    assert "gross_pnl" in result
    assert "fee" in result
    assert result["pnl"] == result["gross_pnl"] - result["fee"]
    assert result["fee"] > 0
