"""GET /api/v1/liquidity-var/ — auth kontrolü.

Algoritmanın kendi doğruluğu tests/test_liquidity_adjusted_var.py'nin
izole birim testlerinde zaten kanıtlanmış. Uç nokta gerçek Binance ağ
isteği yaptığı için burada sadece auth gate'i doğrulanıyor (bkz.
test_correlation_breakdown_api.py'deki AYNI gerekçe)."""
from unittest.mock import patch


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_liquidity_var_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/liquidity-var/")
        assert response.status_code in (401, 403)
