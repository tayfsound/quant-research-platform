"""Sprint 17-18: Plugin System — agents/plugins/ auto-discovery, hash-gated.

Security note (roadmap, explicit): loading a .py file and instantiating a
class from it is arbitrary code execution. Default is fail-closed — a file
dropped into agents/plugins/ is NOT imported unless its exact SHA256 content
hash is already listed in TRUSTED_PLUGIN_HASHES. This is a local trust list
a human populates after reviewing the file, not a remote signing/PKI system
(that's separate, larger infra work) — but it means an unreviewed file does
nothing on its own, and a reviewed-then-tampered file (hash no longer
matches) is also skipped, not silently loaded.
"""
import hashlib
import importlib.util
from pathlib import Path

from agents.registry import AgentRegistry

PLUGINS_DIR = Path(__file__).parent / "plugins"

# filename -> expected sha256 hex digest of the file's exact bytes.
# Empty by default: nothing loads until a human reviews a plugin file and
# adds its hash here (or passes an explicit trusted_hashes dict to
# discover_plugins for tests/tooling).
TRUSTED_PLUGIN_HASHES: dict[str, str] = {}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_plugins(
    registry: AgentRegistry,
    trusted_hashes: dict[str, str] | None = None,
    plugins_dir: Path | None = None,
) -> list[str]:
    """Scans plugins_dir/*.py, imports and registers only files whose
    content hash matches trusted_hashes. Returns the filenames actually
    loaded. Untrusted, tampered, or malformed plugins are skipped, not
    raised on — one bad/unreviewed plugin file must not crash startup for
    everyone else's agents.

    A plugin module must define:
      PLUGIN_DOMAIN: AgentDomain
      PLUGIN_AGENT_CLASS: a no-arg-constructible class with .analyze(ctx)
    """
    if trusted_hashes is not None:
        trusted = trusted_hashes
    else:
        from services.plugin_trust_store import load_trusted_hashes
        trusted = {**TRUSTED_PLUGIN_HASHES, **load_trusted_hashes()}
    directory = plugins_dir if plugins_dir is not None else PLUGINS_DIR
    loaded = []

    if not directory.exists():
        return loaded

    for path in sorted(directory.glob("*.py")):
        if path.name == "__init__.py":
            continue

        expected_hash = trusted.get(path.name)
        if expected_hash is None or file_hash(path) != expected_hash:
            continue  # untrusted, unknown, or tampered — skip, fail closed

        spec = importlib.util.spec_from_file_location(f"agents.plugins.{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        domain = getattr(module, "PLUGIN_DOMAIN", None)
        agent_cls = getattr(module, "PLUGIN_AGENT_CLASS", None)
        if domain is None or agent_cls is None:
            continue  # malformed plugin (missing required exports) — skip

        registry.register(domain, agent_cls())
        loaded.append(path.name)

    return loaded
