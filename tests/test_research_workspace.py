"""Sprint 19-20 gate: through the UI/API only (no code edit, no deploy),
upload a new agent, trust it, and prove it actually runs — using
agents.plugin_loader's real hash-gate the whole way, not bypassing it."""
import shutil
from pathlib import Path
from unittest.mock import patch

from agents.plugin_loader import PLUGINS_DIR
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers

PLUGIN_SOURCE = '''
from contracts.agent import AgentDomain, AgentOpinion


class WorkspaceTestAgent:
    def analyze(self, context):
        return AgentOpinion(domain=AgentDomain.QUANT, direction="SHORT", confidence=0.55)


PLUGIN_DOMAIN = AgentDomain.QUANT
PLUGIN_AGENT_CLASS = WorkspaceTestAgent
'''

TEST_FILENAME = "workspace_test_agent.py"


def _cleanup():
    (PLUGINS_DIR / TEST_FILENAME).unlink(missing_ok=True)
    from services.plugin_trust_store import revoke_plugin
    revoke_plugin(TEST_FILENAME)


def test_upload_then_trust_activates_a_new_agent_with_no_code_change():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from fastapi.testclient import TestClient
            from api.main import app

            _cleanup()
            try:
                client = TestClient(app)
                headers = make_authed_headers(Role.ADMIN)

                upload = client.post(
                    "/api/v1/workspace/plugins/upload",
                    json={"filename": TEST_FILENAME, "source_code": PLUGIN_SOURCE},
                    headers=headers,
                )
                assert upload.status_code == 200
                assert upload.json()["trusted"] is False

                listing = client.get("/api/v1/workspace/plugins").json()
                entry = next(p for p in listing["plugins"] if p["filename"] == TEST_FILENAME)
                assert entry["trusted"] is False

                # Not yet trusted -> discover_plugins must NOT load it.
                from agents.plugin_loader import discover_plugins
                from agents.registry import AgentRegistry
                probe = AgentRegistry()
                assert TEST_FILENAME not in discover_plugins(probe)

                trust = client.post(f"/api/v1/workspace/plugins/{TEST_FILENAME}/trust", headers=headers)
                assert trust.status_code == 200
                body = trust.json()
                assert body["trusted"] is True
                assert body["activated"] is True
                assert "quant" in body["registered_domains"]

                # The real gate: a brand-new AgentRegistry.create_default()
                # (as CognitiveEngine would build) now includes this agent,
                # with zero code changes to agents/registry.py.
                from contracts.agent import AgentDomain
                registry = AgentRegistry.create_default()
                agent = registry.get(AgentDomain.QUANT)
                assert agent is not None
                opinion = agent.analyze(None)
                assert opinion.direction == "SHORT"
            finally:
                _cleanup()


def test_upload_rejects_unsafe_filenames():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from fastapi.testclient import TestClient
            from api.main import app

            client = TestClient(app)
            response = client.post(
                "/api/v1/workspace/plugins/upload",
                json={"filename": "../../evil.py", "source_code": "x = 1"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert response.status_code == 400


def test_upload_requires_admin_role():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from fastapi.testclient import TestClient
            from api.main import app

            client = TestClient(app)
            response = client.post(
                "/api/v1/workspace/plugins/upload",
                json={"filename": "harmless.py", "source_code": "x = 1"},
                headers=make_authed_headers(Role.VIEWER),
            )
            assert response.status_code == 403

            unauthenticated = client.post(
                "/api/v1/workspace/plugins/upload",
                json={"filename": "harmless.py", "source_code": "x = 1"},
            )
            assert unauthenticated.status_code == 401
