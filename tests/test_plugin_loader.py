"""Sprint 17-18: plugin auto-discovery, hash-gated. Uses tmp_path for an
isolated plugins directory rather than the real agents/plugins/ — proves
the trust mechanism itself: unknown files are skipped, tampered files are
skipped even under their original filename, and only an exact-hash-matched
file is imported and registered."""
from agents.plugin_loader import discover_plugins, file_hash
from agents.registry import AgentRegistry

VALID_PLUGIN_SOURCE = '''
from contracts.agent import AgentDomain, AgentOpinion


class QuantPluginAgent:
    def analyze(self, context):
        return AgentOpinion(domain=AgentDomain.QUANT, direction="LONG", confidence=0.6)


PLUGIN_DOMAIN = AgentDomain.QUANT
PLUGIN_AGENT_CLASS = QuantPluginAgent
'''

MALFORMED_PLUGIN_SOURCE = "x = 1\n"  # no PLUGIN_DOMAIN / PLUGIN_AGENT_CLASS


def test_untrusted_plugin_is_skipped(tmp_path):
    plugin_file = tmp_path / "quant_plugin.py"
    plugin_file.write_text(VALID_PLUGIN_SOURCE)

    registry = AgentRegistry()
    loaded = discover_plugins(registry, trusted_hashes={}, plugins_dir=tmp_path)

    assert loaded == []
    from contracts.agent import AgentDomain
    assert registry.get(AgentDomain.QUANT) is None


def test_trusted_plugin_with_matching_hash_is_loaded_and_registered():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        plugins_dir = Path(tmp)
        plugin_file = plugins_dir / "quant_plugin.py"
        plugin_file.write_text(VALID_PLUGIN_SOURCE)

        real_hash = file_hash(plugin_file)
        registry = AgentRegistry()
        loaded = discover_plugins(
            registry, trusted_hashes={"quant_plugin.py": real_hash}, plugins_dir=plugins_dir
        )

        assert loaded == ["quant_plugin.py"]
        from contracts.agent import AgentDomain
        agent = registry.get(AgentDomain.QUANT)
        assert agent is not None
        opinion = agent.analyze(None)
        assert opinion.direction == "LONG"


def test_tampered_plugin_is_skipped_even_with_a_previously_trusted_filename(tmp_path):
    """The whole point of hash-gating: if a file changes after being
    reviewed/trusted, it must NOT load just because the filename matches."""
    plugin_file = tmp_path / "quant_plugin.py"
    plugin_file.write_text(VALID_PLUGIN_SOURCE)
    original_hash = file_hash(plugin_file)

    # tamper with the file after the hash was recorded
    plugin_file.write_text(VALID_PLUGIN_SOURCE + "\n# malicious change\n")

    registry = AgentRegistry()
    loaded = discover_plugins(
        registry, trusted_hashes={"quant_plugin.py": original_hash}, plugins_dir=tmp_path
    )

    assert loaded == []


def test_malformed_trusted_plugin_is_skipped_not_crashed_on(tmp_path):
    plugin_file = tmp_path / "broken_plugin.py"
    plugin_file.write_text(MALFORMED_PLUGIN_SOURCE)
    real_hash = file_hash(plugin_file)

    registry = AgentRegistry()
    loaded = discover_plugins(
        registry, trusted_hashes={"broken_plugin.py": real_hash}, plugins_dir=tmp_path
    )

    assert loaded == []


def test_nonexistent_plugins_dir_returns_empty_without_error(tmp_path):
    registry = AgentRegistry()
    loaded = discover_plugins(registry, trusted_hashes={}, plugins_dir=tmp_path / "does_not_exist")
    assert loaded == []


def test_create_default_actually_calls_plugin_discovery():
    """Proves discover_plugins is wired into the real registry construction
    path, not just a standalone utility nothing calls."""
    from unittest.mock import patch

    with patch("agents.plugin_loader.discover_plugins") as mock_discover:
        AgentRegistry.create_default()
        mock_discover.assert_called_once()
