"""OllamaExplainer contract testleri."""
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
