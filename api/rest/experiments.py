"""Experiment Registry API — Faz 159 sorgulanabilirlik."""
from fastapi import APIRouter
from database.session_factory import SessionFactory
from database.repositories.experiment_registry_repository import ExperimentRegistryRepository

router = APIRouter(prefix="/experiments", tags=["experiments"])

@router.get("/")
async def list_experiments(limit: int = 20):
    with SessionFactory.get_session() as session:
        repo = ExperimentRegistryRepository(session)
        rows = repo.get_by_git_sha("")  # Tümü için boş sha — repo'ya all method ekle
        return {"experiments": []}  # Placeholder — gerçek implementasyon sonra

@router.get("/{git_sha}")
async def get_by_git_sha(git_sha: str):
    with SessionFactory.get_session() as session:
        repo = ExperimentRegistryRepository(session)
        rows = repo.get_by_git_sha(git_sha)
        return {"git_sha": git_sha, "count": len(rows), "experiments": [{"id": str(r.id), "timestamp": r.timestamp.isoformat()} for r in rows]}
