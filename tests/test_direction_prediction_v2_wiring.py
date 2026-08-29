"""GET /api/v1/direction-prediction-v2 — Cognitive Core 2.0 / M4 (Faz
519-543). Kullanıcı onayıyla (2026-08-19) 4 Grup B modülünden biri,
council'i hiç etkilemeyen bir ölçüm/rapor katmanı."""
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_direction_prediction_v2_requires_auth():
    client = _client()
    response = client.get("/api/v1/direction-prediction-v2/")
    assert response.status_code in (401, 403)


def test_direction_prediction_v2_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/direction-prediction-v2/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    assert "by_domain" in response.json()["result"]


def test_direction_prediction_v2_reports_endpoint_requires_auth():
    client = _client()
    response = client.get("/api/v1/direction-prediction-v2/reports")
    assert response.status_code in (401, 403)


def test_direction_prediction_v2_reports_endpoint_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/direction-prediction-v2/reports?limit=5", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    assert "reports" in response.json()


def test_gather_direction_prediction_v2_returns_plain_string_domain_keys():
    """Faz 282 — kritik bulgu: ilk sürüm VOTING_AGENT_DOMAINS'in ham
    AgentDomain enum objelerini dict anahtarı olarak kullanıyordu
    (JSON'da <AgentDomain.MACRO: 'macro'> gibi bozuk görünüyordu). Artık
    domain.value (düz string) kullanılıyor."""
    from services.direction_prediction_v2_gatherer import gather_direction_prediction_v2

    result = gather_direction_prediction_v2()
    for domain in result["by_domain"]:
        assert isinstance(domain, str)


def test_gather_direction_prediction_v2_computes_a_real_brier_score_from_agent_memory():
    """compute_brier_score'un gerçek (confidence, was_correct) çiftlerinden
    anlamlı bir skor ürettiğini doğruluyor — tam isabetli bir ajan 0'a
    yakın bir skor almalı."""
    from contracts.agent_performance import AgentPerformanceRecord
    from services.agent_memory import AgentMemory
    from services.direction_prediction_v2_gatherer import gather_direction_prediction_v2

    memory = AgentMemory(storage_path="test_direction_pred_v2_memory")
    try:
        for _ in range(15):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.9, was_correct=True,
            ))
        result = gather_direction_prediction_v2(agent_memory=memory)
        assert "technical" in result["by_domain"]
        assert result["by_domain"]["technical"]["brier_score"] < 0.25  # rastgeleden (0.25) iyi
    finally:
        import shutil
        shutil.rmtree("test_direction_pred_v2_memory", ignore_errors=True)


def test_gather_direction_prediction_v2_raw_brier_score_is_none_without_raw_confidence():
    """Faz 369-devam — GPT önerisi: mevcut brier_score HER ZAMAN kalibre
    edilmiş confidence'tan hesaplanıyordu, ham sinyal hiç ayrı
    ölçülemiyordu. Eski kayıtlarda (raw_confidence eklenmeden önce
    yazılmış) bu alan None — fail-closed, icat edilmiş bir sayı asla
    üretilmez."""
    from contracts.agent_performance import AgentPerformanceRecord
    from services.agent_memory import AgentMemory
    from services.direction_prediction_v2_gatherer import gather_direction_prediction_v2

    memory = AgentMemory(storage_path="test_direction_pred_v2_memory_no_raw")
    try:
        for _ in range(15):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.9, was_correct=True,
            ))
        result = gather_direction_prediction_v2(agent_memory=memory)
        assert result["by_domain"]["technical"]["raw_brier_score"] is None
    finally:
        import shutil
        shutil.rmtree("test_direction_pred_v2_memory_no_raw", ignore_errors=True)


def test_gather_direction_prediction_v2_raw_brier_score_computed_when_raw_confidence_present():
    """Faz 369-devam — raw_confidence dolu yeterli (>=10) kayıt birikince
    raw_brier_score GERÇEKTEN hesaplanır — kalibre edilmiş ve ham skor
    AYRI, bağımsız sayılar olabilir (burada kasıtlı FARKLI: ham her
    zaman 0.95 (aşırı iddialı), kalibre edilmiş 0.6 (daha temkinli) —
    ham Brier'in daha KÖTÜ çıkması beklenir, KALİBRASYONUN gerçekten
    işe yaradığının kanıtı)."""
    from contracts.agent_performance import AgentPerformanceRecord
    from services.agent_memory import AgentMemory
    from services.direction_prediction_v2_gatherer import gather_direction_prediction_v2

    memory = AgentMemory(storage_path="test_direction_pred_v2_memory_with_raw")
    try:
        for i in range(15):
            was_correct = i < 9  # %60 gerçek isabet
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG",
                confidence=0.6, raw_confidence=0.95, was_correct=was_correct,
            ))
        result = gather_direction_prediction_v2(agent_memory=memory)
        raw_score = result["by_domain"]["technical"]["raw_brier_score"]
        assert raw_score is not None
        assert raw_score["sample_size"] == 15
        # Ham (0.95, aşırı iddialı) %60 gerçek isabete karşı, kalibre
        # edilmiş (0.6, gerçeğe çok daha yakın) olandan KESİNLİKLE daha
        # kötü olmalı — kalibrasyonun gerçek etkisinin kanıtı.
        assert raw_score["brier_score"] > result["by_domain"]["technical"]["brier_score"]
    finally:
        import shutil
        shutil.rmtree("test_direction_pred_v2_memory_with_raw", ignore_errors=True)
