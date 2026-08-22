"""Gap #15 (P0): ctx.risk.limits used to be populated by nothing in
production, so RiskEngine always rejected every real decision with
MISSING_LIMIT — the CognitiveEngine path never actually approved a trade.
This proves the real fix end to end over HTTP: an ADMIN sets a signed risk
limit via POST /risk-limits, and POST /cognitive/run picks it up for real
(no more MISSING_LIMIT), using the DB-backed RiskLimitRepository — not a
test-only FakeLimit."""
from unittest.mock import patch

from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def test_admin_set_risk_limit_is_picked_up_by_cognitive_run():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)

        set_resp = client.post(
            "/api/v1/risk-limits/max_position_size?value=1.0",
            headers=make_authed_headers(Role.ADMIN),
        )
        assert set_resp.status_code == 200
        assert set_resp.json()["value"] == 1.0

        list_resp = client.get(
            "/api/v1/risk-limits/",
            headers=make_authed_headers(Role.VIEWER),
        )
        assert list_resp.status_code == 200
        limits = {row["limit_type"]: row["value"] for row in list_resp.json()["limits"]}
        assert limits["max_position_size"] == 1.0

        run_resp = client.post(
            "/api/v1/cognitive/run",
            headers=make_authed_headers(Role.OPERATOR),
        )
        assert run_resp.status_code == 200
        body = run_resp.json()
        # The real bug this closes: this used to be "rejected" with
        # MISSING_LIMIT on every single call, regardless of what the
        # agents actually decided.
        assert "MISSING_LIMIT" not in body["risk_reasons"]


def test_operator_cannot_set_risk_limit():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/risk-limits/max_position_size?value=1.0",
        headers=make_authed_headers(Role.OPERATOR),
    )
    assert resp.status_code == 403
