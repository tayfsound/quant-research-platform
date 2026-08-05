"""Real bug found live in the dashboard: AIReasoning.tsx always showed
"LLM unavailable - proceeding with neutral adjustment" — not because Ollama
was down, but because OllamaExplainer.explain()'s default timeout_ms was
500, and a real local mistral:7b-instruct call (full system prompt + JSON
output) measured ~6.8s. Every real call timed out by more than 10x,
silently falling back to LLMExplanation.neutral() (which never raises, so
nothing ever surfaced this as an error — just a permanently "neutral"
explanation with no indication anything was wrong).

Needs a real local Ollama instance with the configured model — skips if
unavailable (this dev machine has it; CI does not, matching the existing
convention for other environment-dependent tests in this repo)."""
import httpx
import pytest

pytestmark = pytest.mark.asyncio


def _ollama_available() -> bool:
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_available(), reason="requires a local Ollama instance")
async def test_real_explain_call_succeeds_within_default_timeout():
    from llm_reasoner import OllamaExplainer

    explainer = OllamaExplainer()
    result = await explainer.explain({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "confidence": 0.82,
        "agent_votes": {"trend_agent": {"direction": "LONG", "confidence": 0.85}},
        "market_snapshot": {"price": 50250, "rsi_14": 32.5},
    })

    assert "unavailable" not in result.explanation.lower()
