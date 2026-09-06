"""Faz 415 (2026-09-06) — kullanıcı isteği: "son eklediğimiz modüllerden
aldığımız verilerin zaman içindeki tutarlılığını gösteren verileri
dashboard'da göremiyorum." Faz 407'nin (compute_stability) hiçbir
dashboard görünümü yoktu — bu testler hem saf çıkarım yardımcısını
(extract_stability_summary) hem GET /api/v1/measurement-stability/'yi
kapsıyor."""
from unittest.mock import patch

from analytics.measurement_stability import extract_stability_summary
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_extract_stability_summary_finds_nested_stability_dicts():
    result = {
        "by_domain": {
            "macro": {"brier_score": 0.38, "brier_score_stability": {"n": 4, "coefficient_of_variation": 0.3}},
            "technical": {"brier_score": 0.26, "brier_score_stability": {"n": 4, "coefficient_of_variation": 0.05}},
        },
    }
    found = extract_stability_summary(result)
    paths = {f["path"] for f in found}
    assert paths == {"by_domain.macro.brier_score_stability", "by_domain.technical.brier_score_stability"}


def test_extract_stability_summary_walks_lists():
    result = {"analogs": [
        {"win_rate": 0.9, "win_rate_stability": {"n": 2, "coefficient_of_variation": 0.08}},
        {"win_rate": 0.8, "win_rate_stability": {"n": 2, "coefficient_of_variation": 0.12}},
    ]}
    found = extract_stability_summary(result)
    assert len(found) == 2
    assert found[0]["path"] == "analogs[0].win_rate_stability"


def test_extract_stability_summary_ignores_non_stability_dicts_and_scalars():
    result = {"win_rate": 0.9, "n": 10, "note": "hello", "nested": {"foo": "bar"}}
    assert extract_stability_summary(result) == []


def test_extract_stability_summary_handles_non_string_dict_keys():
    """Gerçek bulgu: market_world_model'in block_size_sensitivity.
    by_block_size'ı int anahtarlı (5, 10, 20, 30) bir sözlük — .endswith()
    burada AttributeError ile patlıyordu, canlı taramada gerçekten oldu."""
    result = {"by_block_size": {
        5: {"win_rate": 0.5, "win_rate_stability": {"n": 3, "coefficient_of_variation": 0.1}},
        10: {"win_rate": 0.6},
    }}
    found = extract_stability_summary(result)
    assert len(found) == 1
    assert found[0]["path"] == "by_block_size.5.win_rate_stability"


def test_extract_stability_summary_requires_coefficient_of_variation_shape():
    """"_stability" ile biten ama compute_stability() şeklini taşımayan
    bir alan (ör. elle yazılmış farklı bir sözlük) yanlışlıkla
    toplanmamalı."""
    result = {"foo_stability": {"something_else": 1}}
    assert extract_stability_summary(result) == []


def test_gather_measurement_stability_summary_aggregates_research_summary_modules(monkeypatch):
    from services import measurement_stability_summary_gatherer as mssg

    def fake_research_summary():
        return {"modules": [
            {"key": "macro_thing", "label": "Macro Thing", "view": "x", "result": {
                "foo_stability": {"n": 5, "mean": 0.5, "std": 0.1, "min": 0.4, "max": 0.6, "coefficient_of_variation": 0.2},
            }, "error": None},
            {"key": "broken", "label": "Broken", "view": "y", "result": None, "error": "kasıtlı test hatası"},
        ]}

    monkeypatch.setattr(mssg, "gather_research_summary", fake_research_summary)
    monkeypatch.setattr(mssg, "_correlation_module_entry", lambda: {"key": "correlation", "label": "Korelasyon", "fields": [], "n_fields": 0, "last_computed_at": None, "error": None})
    monkeypatch.setattr(mssg, "_feature_ic_module_entry", lambda: {"key": "feature_ic", "label": "Feature IC", "fields": [], "n_fields": 0, "last_computed_at": None, "error": None})

    result = mssg.gather_measurement_stability_summary()
    by_key = {m["key"]: m for m in result["modules"]}

    assert by_key["macro_thing"]["n_fields"] == 1
    assert by_key["macro_thing"]["fields"][0]["path"] == "foo_stability"
    assert by_key["broken"]["error"] == "kasıtlı test hatası"
    assert by_key["broken"]["n_fields"] == 0
    assert "correlation" in by_key
    assert "feature_ic" in by_key
    assert result["most_volatile"][0]["module_key"] == "macro_thing"


def test_gather_measurement_stability_summary_most_volatile_requires_min_sample(monkeypatch):
    """n<5 olan bir alan "en oynak" listesine icat edilmiş bir kesinlikle girmemeli."""
    from services import measurement_stability_summary_gatherer as mssg

    def fake_research_summary():
        return {"modules": [
            {"key": "m", "label": "M", "view": "x", "result": {
                "x_stability": {"n": 2, "mean": 0.5, "std": 0.4, "min": 0.1, "max": 0.9, "coefficient_of_variation": 0.8},
            }, "error": None},
        ]}

    monkeypatch.setattr(mssg, "gather_research_summary", fake_research_summary)
    monkeypatch.setattr(mssg, "_correlation_module_entry", lambda: {"key": "correlation", "label": "Korelasyon", "fields": [], "n_fields": 0, "last_computed_at": None, "error": None})
    monkeypatch.setattr(mssg, "_feature_ic_module_entry", lambda: {"key": "feature_ic", "label": "Feature IC", "fields": [], "n_fields": 0, "last_computed_at": None, "error": None})

    result = mssg.gather_measurement_stability_summary()
    assert result["most_volatile"] == []


def test_requires_auth():
    response = _client().get("/api/v1/measurement-stability/")
    assert response.status_code in (401, 403)


def test_endpoint_returns_gatherer_output(monkeypatch):
    from api.rest import measurement_stability as ms_api

    monkeypatch.setattr(ms_api, "gather_measurement_stability_summary", lambda: {"modules": [], "most_volatile": []})
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/measurement-stability/", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        assert response.json() == {"modules": [], "most_volatile": []}
