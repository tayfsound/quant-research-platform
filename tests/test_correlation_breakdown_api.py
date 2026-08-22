"""GET /api/v1/correlation-breakdown/ — auth kontrolü.

Algoritmanın kendi doğruluğu tests/test_correlation_breakdown.py'nin izole
birim testlerinde zaten kanıtlanmış. Uç nokta gerçek Binance ağ isteği
yaptığı için burada sadece auth gate'i doğrulanıyor — ağa bağımlı bir
entegrasyon testi yazmak (BinanceAdapter'ın connect/fetch_ohlcv/disconnect
async akışını taklit etmek) bu uç noktanın asıl riskini (algoritma değil,
ağ çağrısı) test etmiş olmazdı."""
from unittest.mock import patch


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_correlation_breakdown_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/correlation-breakdown/")
        assert response.status_code in (401, 403)
