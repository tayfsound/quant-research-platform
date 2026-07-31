import os

# 1. test_integration_cycle.py -- HF Hub mock'la
with open('tests/test_integration_cycle.py', 'w') as f:
    f.write('''"""Integration test: full cycle -> belief persist + weight snapshot chain."""
from unittest.mock import patch, MagicMock
import pytest

def test_full_cycle_runs_finalize():
    """Tam cycle sonrasi finalize calismali."""
    # HF Hub model yuklemesini mock'la
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.cognitive_engine import CognitiveEngine
            from contracts.context import CognitiveCycleContext
            from contracts.outcome import TradeOutcome

            engine = CognitiveEngine()
            ctx = CognitiveCycleContext()
            ctx.market.symbol = "BTCUSDT"
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.confidence = 0.8

            ctx = engine.run(ctx, persist=False)
            ctx.outcome = TradeOutcome(pnl=100, win=True, decision="LONG", confidence_at_decision=0.8)

            with patch.object(engine, "_persist_and_learn") as mock_persist:
                engine.finalize(ctx)
                mock_persist.assert_called_once()

def test_weight_optimizer_handles_pydantic_agents():
    """WeightOptimizer Pydantic AgentOpinion objelerini isleyebilmeli."""
    from services.weight_optimizer import WeightOptimizer
    from services.agent_memory import AgentMemory
    from contracts.agent import AgentOpinion, AgentDomain

    memory = AgentMemory()
    opt = WeightOptimizer(agent_memory=memory)

    agents = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.8),
        AgentOpinion(domain=AgentDomain.MACRO, direction="LONG", confidence=0.6),
    ]

    class FakeOutcome:
        decision_score = 0.5

    weights = opt.optimize(agents, FakeOutcome())
    assert "technical" in weights
    assert "macro" in weights
    assert all(0.0 <= w <= 2.0 for w in weights.values())
''')
print('✓ test_integration_cycle.py HF Hub mock eklendi')

# 2. test_llm_explainer.py -- httpx exception'larini duzelt
with open('tests/contract/test_llm_explainer.py', 'w') as f:
    f.write('''"""OllamaExplainer contract testleri."""
import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest

from contracts.llm import LLMExplanation
from llm_reasoner import OllamaExplainer

@pytest.mark.asyncio
async def test_timeout_returns_neutral():
    """httpx timeout durumunda neutral donmeli."""
    explainer = OllamaExplainer()
    with patch("httpx.post", side_effect=httpx.ReadTimeout("timeout")):
        result = await explainer.explain({}, timeout_ms=200)
        assert result == LLMExplanation.neutral()

@pytest.mark.asyncio
async def test_http_error_returns_neutral():
    """httpx HTTPError durumunda neutral donmeli."""
    explainer = OllamaExplainer()
    with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
        result = await explainer.explain({})
        assert result == LLMExplanation.neutral()

@pytest.mark.asyncio
async def test_empty_response_returns_neutral():
    """LLM bos response donerse neutral donmeli."""
    explainer = OllamaExplainer()
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": ""}
    with patch("httpx.post", return_value=mock_response):
        result = await explainer.explain({})
        assert result == LLMExplanation.neutral()

@pytest.mark.asyncio
async def test_valid_response_parsed():
    """Gecerli JSON response parse edilmeli."""
    explainer = OllamaExplainer()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": '{"explanation": "bullish", "risks": [], "confidence_comment": "high", "risk_adjustment_factor": 0.9}'
    }
    with patch("httpx.post", return_value=mock_response):
        result = await explainer.explain({})
        assert result.explanation == "bullish"
        assert result.risk_adjustment_factor == 0.9
''')
print('✓ test_llm_explainer.py httpx exception duzeltildi')

print('\n=== TEST ===')
import subprocess
for tf in [
    'tests/contract/test_llm_explainer.py',
    'tests/test_integration_cycle.py',
]:
    r = subprocess.run(['pytest', tf, '-v', '--tb=short'], capture_output=True, text=True)
    status = '✓' if r.returncode == 0 else '✗'
    print(f'  {status} {tf}')
    if r.returncode != 0:
        print(f'    ERR: {r.stderr[:300]}')

print('\n=== GENEL TEST ===')
r = subprocess.run(['pytest', '-q'], capture_output=True, text=True)
print(r.stdout[-600:] if len(r.stdout) > 600 else r.stdout)
if r.returncode != 0:
    print('ERR:', r.stderr[:400])
