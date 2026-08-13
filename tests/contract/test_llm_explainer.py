"""NvidiaDecisionCritic sözleşme testleri."""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from contracts.llm import LLMExplanation
from llm_reasoner import NvidiaDecisionCritic


@pytest.mark.asyncio
async def test_missing_api_key_returns_neutral():
    """NVIDIA_API_KEY set edilmemişse fail-closed — sessizce nötr döner."""
    critic = NvidiaDecisionCritic(api_key="")
    result = await critic.explain({})
    assert result == LLMExplanation.neutral()


@pytest.mark.asyncio
async def test_timeout_returns_neutral():
    """httpx timeout durumunda neutral donmeli."""
    critic = NvidiaDecisionCritic(api_key="fake-key")
    with patch("httpx.post", side_effect=httpx.ReadTimeout("timeout")):
        result = await critic.explain({}, timeout_ms=200)
        assert result == LLMExplanation.neutral()

@pytest.mark.asyncio
async def test_http_error_returns_neutral():
    """httpx HTTPError durumunda neutral donmeli."""
    critic = NvidiaDecisionCritic(api_key="fake-key")
    with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
        result = await critic.explain({})
        assert result == LLMExplanation.neutral()

@pytest.mark.asyncio
async def test_empty_response_returns_neutral():
    """LLM bos response donerse neutral donmeli."""
    critic = NvidiaDecisionCritic(api_key="fake-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": ""}}]}
    with patch("httpx.post", return_value=mock_response):
        result = await critic.explain({})
        assert result == LLMExplanation.neutral()

@pytest.mark.asyncio
async def test_ask_returns_message_when_no_api_key():
    critic = NvidiaDecisionCritic(api_key="")
    result = await critic.ask("merhaba")
    assert "NVIDIA_API_KEY" in result


@pytest.mark.asyncio
async def test_ask_returns_content_from_openai_compatible_response():
    critic = NvidiaDecisionCritic(api_key="fake-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "Merhaba, size nasıl yardımcı olabilirim?"}}]}
    with patch("httpx.post", return_value=mock_response):
        result = await critic.ask("merhaba")
        assert result == "Merhaba, size nasıl yardımcı olabilirim?"


@pytest.mark.asyncio
async def test_ask_returns_error_message_on_timeout():
    critic = NvidiaDecisionCritic(api_key="fake-key")
    with patch("httpx.post", side_effect=httpx.ReadTimeout("timeout")):
        result = await critic.ask("merhaba", timeout_ms=200)
        assert "aşımı" in result.lower() or "hata" in result.lower()


@pytest.mark.asyncio
async def test_valid_response_parsed():
    """Gecerli JSON response (OpenAI-uyumlu choices[].message.content) parse edilmeli."""
    critic = NvidiaDecisionCritic(api_key="fake-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {
            "content": '{"explanation": "bullish", "risks": [], "confidence_comment": "high", "risk_adjustment_factor": 0.9}'
        }}]
    }
    with patch("httpx.post", return_value=mock_response):
        result = await critic.explain({})
        assert result.explanation == "bullish"
        assert result.risk_adjustment_factor == 0.9
