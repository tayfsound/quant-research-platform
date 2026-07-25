"""OllamaExplainer contract testleri."""
import asyncio
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from contracts.llm import LLMExplanation
from llm_reasoner import OllamaExplainer


@pytest.mark.asyncio
async def test_timeout_kills_process():
    explainer = OllamaExplainer()
    mock_process = MagicMock()
    mock_process.communicate.side_effect = subprocess.TimeoutExpired(cmd="ollama", timeout=0.5)
    with patch("subprocess.Popen", return_value=mock_process):
        result = await asyncio.wait_for(explainer.explain({}, timeout_ms=200), timeout=1.0)
    assert result == LLMExplanation.neutral()
    mock_process.kill.assert_called_once()

@pytest.mark.asyncio
async def test_stderr_filled_but_exit_ok():
    explainer = OllamaExplainer()
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("", "some error output")
    mock_process.returncode = 0
    with patch("subprocess.Popen", return_value=mock_process):
        result = await explainer.explain({})
    assert result == LLMExplanation.neutral()

@pytest.mark.asyncio
async def test_empty_stdout_returns_neutral():
    explainer = OllamaExplainer()
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("   ", "")
    mock_process.returncode = 0
    with patch("subprocess.Popen", return_value=mock_process):
        result = await explainer.explain({})
    assert result == LLMExplanation.neutral()
