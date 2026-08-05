"""Ensemble → LLM Reasoner REST endpoint."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from llm_reasoner import OllamaExplainer
from services.auth_service import AuthContext, get_current_user

router = APIRouter()
explainer = OllamaExplainer()

class EnsembleOutput(BaseModel):
    symbol: str
    direction: str
    confidence: float
    agent_votes: dict = {}
    market_snapshot: dict = {}
    onchain_signals: dict = {}
    macro_context: dict = {}

@router.post("/reasoning/explain")
async def explain_decision(output: EnsembleOutput, user: AuthContext = Depends(get_current_user)):
    result = await explainer.explain(output.model_dump())
    return result
