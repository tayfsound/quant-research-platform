"""Research Workspace API — Sprint 19-20. Upload a plugin agent file, review
its hash, explicitly trust it (activating it in AgentRegistry without a code
change/deploy), or revoke trust. The hash-gate from agents/plugin_loader.py
is never bypassed here — uploading never auto-trusts, it only writes the
file so a human can review it before the separate trust step."""
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.plugin_loader import PLUGINS_DIR, file_hash
from services.plugin_trust_store import load_trusted_hashes, revoke_plugin, trust_plugin

router = APIRouter(prefix="/workspace", tags=["workspace"])

_SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9_]+\.py$")
MAX_PLUGIN_SIZE_BYTES = 50_000


class PluginUpload(BaseModel):
    filename: str
    source_code: str


@router.get("/plugins")
async def list_plugins():
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    trusted = load_trusted_hashes()
    plugins = []
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        current_hash = file_hash(path)
        trusted_hash = trusted.get(path.name)
        plugins.append({
            "filename": path.name,
            "hash": current_hash,
            "trusted": trusted_hash == current_hash,
        })
    return {"plugins": plugins}


@router.post("/plugins/upload")
async def upload_plugin(upload: PluginUpload):
    """Writes the file only — does NOT trust/import it. Returns the hash so
    a reviewer can inspect the source and then call /trust explicitly."""
    if not _SAFE_FILENAME.match(upload.filename):
        raise HTTPException(status_code=400, detail="filename must match ^[a-zA-Z0-9_]+\\.py$")
    if len(upload.source_code.encode()) > MAX_PLUGIN_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="plugin source too large")

    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    path = PLUGINS_DIR / upload.filename
    path.write_text(upload.source_code)

    return {"filename": upload.filename, "hash": file_hash(path), "trusted": False}


@router.post("/plugins/{filename}/trust")
async def trust_plugin_endpoint(filename: str):
    path = PLUGINS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="plugin_not_found")

    trust_plugin(filename, file_hash(path))

    from agents.plugin_loader import discover_plugins
    from agents.registry import AgentRegistry
    registry = AgentRegistry()  # empty probe registry, not the live default one
    loaded = discover_plugins(registry)

    return {
        "filename": filename,
        "trusted": True,
        "activated": filename in loaded,
        "registered_domains": [d.value for d in registry.list_domains()],
    }


@router.post("/plugins/{filename}/revoke")
async def revoke_plugin_endpoint(filename: str):
    revoke_plugin(filename)
    return {"filename": filename, "trusted": False}
