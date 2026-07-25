"""Ensemble → LLM Reasoner REST endpoint."""
from fastapi import APIRouter
from pydantic import BaseModel

from llm_reasoner import OllamaExplainer

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
async def explain_decision(output: EnsembleOutput):
    result = await explainer.explain(output.model_dump())
    return result
