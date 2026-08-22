"""GET /api/v1/research-summary/ — Faz 326: kullanıcı isteği, Grup B
(ölçüm-only) araştırma modüllerini tek istekte, canlı hesaplanmış olarak
toplar (Faz 331'de Agent Combination Reliability eklenip 11'e çıktı)."""
from unittest.mock import patch

from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_requires_auth():
    response = _client().get("/api/v1/research-summary/")
    assert response.status_code in (401, 403)


def test_gather_research_summary_returns_all_ten_modules_in_fixed_order():
    from services.research_summary_gatherer import _MODULES, gather_research_summary

    result = gather_research_summary()
    assert [m["key"] for m in result["modules"]] == [key for key, *_ in _MODULES]
    for entry in result["modules"]:
        assert "label" in entry
        assert "view" in entry
        assert "result" in entry
        assert "error" in entry


def test_gather_research_summary_isolates_a_single_module_failure(monkeypatch):
    """Bir modülün hatası (ör. dış API zaman aşımı) diğerlerini
    engellememeli — fail-closed, sessiz değil: hata mesajı açıkça
    dönüyor, sonuç hâlâ TÜM kayıtları içeriyor."""
    from services import research_summary_gatherer as rsg

    def _boom(key, label, view, module_path, func_name):
        if key == "self_model":
            return {"key": key, "label": label, "view": view, "result": None, "error": "kasıtlı test hatası"}
        return {"key": key, "label": label, "view": view, "result": {"ok": True}, "error": None}

    monkeypatch.setattr(rsg, "_run_one", _boom)
    result = rsg.gather_research_summary()

    by_key = {m["key"]: m for m in result["modules"]}
    assert by_key["self_model"]["error"] == "kasıtlı test hatası"
    assert by_key["self_model"]["result"] is None
    assert by_key["tp_sl_confluence"]["error"] is None
    assert by_key["tp_sl_confluence"]["result"] == {"ok": True}


def test_research_summary_endpoint_returns_live_data():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/research-summary/", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        body = response.json()
        from services.research_summary_gatherer import _MODULES
        assert len(body["modules"]) == len(_MODULES)
