"""Faz 268-sonrası: yerel Ollama tabanlı OllamaExplainer, NVIDIA NIM
(build.nvidia.com) tabanlı NvidiaDecisionCritic ile değiştirildi —
kullanıcı bulgusu: yerel Ollama modeliyle sonuç yetersizdi.

Gerçek bir NVIDIA_API_KEY gerektiriyor — set edilmemişse atlanır (CI'da
ve bu anahtara sahip olmayan geliştirme makinelerinde, diğer ortam
bağımlı testlerle (INFURA/HELIUS/FRED) aynı konvansiyon)."""
import pytest

from config.settings import get_settings

pytestmark = pytest.mark.asyncio


def _nvidia_key_available() -> bool:
    return bool(get_settings().NVIDIA_API_KEY)


@pytest.mark.skipif(not _nvidia_key_available(), reason="requires a real NVIDIA_API_KEY")
async def test_real_explain_call_succeeds_within_default_timeout():
    from llm_reasoner import NvidiaDecisionCritic

    critic = NvidiaDecisionCritic()
    result = await critic.explain({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "confidence": 0.82,
        "agent_votes": {"trend_agent": {"direction": "LONG", "confidence": 0.85}},
        "market_snapshot": {"price": 50250, "rsi_14": 32.5},
    })

    assert "unavailable" not in result.explanation.lower()
