"""Sprint 19-20: persisted, runtime-mutable trust store for the plugin
system — lets an operator "trust" a plugin through the Research Workspace UI
without a code change/deploy (the roadmap's own gate), while keeping the
hash-gate from agents/plugin_loader.py intact: trusting still requires the
file to already exist on disk (uploaded/reviewed first), and only pins the
hash that exists AT THE MOMENT of trusting — a later edit to the file
invalidates trust again, same as the hardcoded dict did.
"""
import json
from pathlib import Path

TRUST_FILE = Path(__file__).parent.parent / "agents" / "plugins" / "TRUSTED_HASHES.json"


def load_trusted_hashes() -> dict[str, str]:
    if not TRUST_FILE.exists():
        return {}
    return json.loads(TRUST_FILE.read_text())


def trust_plugin(filename: str, content_hash: str) -> None:
    trusted = load_trusted_hashes()
    trusted[filename] = content_hash
    TRUST_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRUST_FILE.write_text(json.dumps(trusted, indent=2))


def revoke_plugin(filename: str) -> None:
    trusted = load_trusted_hashes()
    trusted.pop(filename, None)
    TRUST_FILE.write_text(json.dumps(trusted, indent=2))
