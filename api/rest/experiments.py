"""Live A/B Testing Framework API — Faz 250.

Faz 233'te kaldırılan experiment_registry API'sinin AKSİNE (write-only,
hiç okunmayan bir denetim kaydıydı) — bu, gerçekten okunan bir
değerlendirme uç noktası: services/ab_testing.py::evaluate_experiment'ı
gerçek zamanlı çağırır, hiçbir şey önceden hesaplayıp saklamaz."""
from fastapi import APIRouter, Depends

from services.ab_testing import evaluate_experiment
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("/{experiment_name}/evaluate")
async def evaluate(experiment_name: str, user: AuthContext = Depends(get_current_user)):
    return evaluate_experiment(experiment_name)
