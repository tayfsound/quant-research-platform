"""POST /api/v1/llm-critic/ask — auth kontrolü.

Gerçek NVIDIA API çağrısı gerektirdiği için (ağ bağımlı, ~90s), burada
sadece auth gate'i doğrulanıyor — llm_reasoner.py::NvidiaDecisionCritic
kendi izole testlerinde (tests/contract/test_llm_explainer.py,
tests/test_llm_reasoner_timeout.py) zaten doğrulanmış."""
from unittest.mock import patch


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_ask_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post("/api/v1/llm-critic/ask", json={"message": "test"})
        assert response.status_code in (401, 403)
