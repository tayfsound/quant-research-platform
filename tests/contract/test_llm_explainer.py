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
async def test_ask_with_tools_returns_message_when_no_api_key():
    critic = NvidiaDecisionCritic(api_key="")
    result = await critic.ask_with_tools("merhaba")
    assert "NVIDIA_API_KEY" in result["response"]
    assert result["tool_calls"] == []
    assert result["status"] == "no_api_key"


@pytest.mark.asyncio
async def test_ask_with_tools_returns_content_directly_when_no_tool_call_requested():
    critic = NvidiaDecisionCritic(api_key="fake-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "Genel bir cevap."}}]}
    with patch("httpx.post", return_value=mock_response):
        result = await critic.ask_with_tools("merhaba")
    assert result["response"] == "Genel bir cevap."
    assert result["tool_calls"] == []
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_ask_with_tools_executes_real_tool_function_and_feeds_result_back():
    """Model önce bir araç çağrısı istiyor (get_recent_performance_summary),
    gerçek Python fonksiyonu çalıştırılıp sonucu modele geri veriliyor,
    model ikinci turda nihai bir metin döndürüyor."""
    critic = NvidiaDecisionCritic(api_key="fake-key")

    tool_call_response = MagicMock()
    tool_call_response.json.return_value = {
        "choices": [{"message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "get_recent_performance_summary", "arguments": "{\"hours\": 24}"},
            }],
        }}]
    }
    final_response = MagicMock()
    final_response.json.return_value = {
        "choices": [{"message": {"content": "Gerçek verilere göre analiz tamamlandı."}}]
    }

    fake_summary = {"window_hours": 24, "ai_automatic_win_rate": 0.19}
    with patch("httpx.post", side_effect=[tool_call_response, final_response]), \
            patch("llm_tools.get_recent_performance_summary", return_value=fake_summary) as mock_tool:
        result = await critic.ask_with_tools("Kazanma oranı nedir?")

    mock_tool.assert_called_once_with(hours=24)
    assert result["response"] == "Gerçek verilere göre analiz tamamlandı."
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool"] == "get_recent_performance_summary"
    assert result["tool_calls"][0]["result"] == fake_summary


@pytest.mark.asyncio
async def test_ask_with_tools_stops_after_max_iterations_without_crashing():
    """Gerçek bulgu (2026-08-18): model kendiliğinden ne zaman duracağını
    bilmiyordu, tüm iterasyonları araç çağırmakla tüketip hiç sonuç
    yazmadan bitebiliyordu (llm_system_audit_task'ta gerçekten yaşandı).
    Artık SON iterasyonda tool_choice="none" gönderiliyor — model daha
    fazla araç çağıramaz. Bu mock (kasıtlı olarak) tool_choice'u hiç
    saymayan "dümdüz döngüye giren" bir model simüle ediyor — max_
    iterations=2 için SADECE 1 gerçek araç çağrısı (ilk iterasyon)
    yürütülmeli, ikinci (son) iterasyon aracı YOK SAYIP zorunlu bir metin
    cevabı üretmeli (bkz. llm_reasoner.py::_ask_with_tools_sync)."""
    critic = NvidiaDecisionCritic(api_key="fake-key")
    looping_response = MagicMock()
    looping_response.json.return_value = {
        "choices": [{"message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "call_x", "function": {"name": "search_code", "arguments": "{\"query\": \"x\"}"}}],
        }}]
    }
    with patch("httpx.post", return_value=looping_response), \
            patch("llm_tools.search_code", return_value={"query": "x", "matches": [], "truncated": False}):
        result = await critic.ask_with_tools("sonsuz döngü testi", max_iterations=2)

    assert "sınırına ulaşıldı" in result["response"]
    assert len(result["tool_calls"]) == 1
    assert result["status"] == "tool_loop_limit"


@pytest.mark.asyncio
async def test_ask_with_tools_handles_unknown_tool_gracefully():
    critic = NvidiaDecisionCritic(api_key="fake-key")
    unknown_tool_response = MagicMock()
    unknown_tool_response.json.return_value = {
        "choices": [{"message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "call_y", "function": {"name": "delete_everything", "arguments": "{}"}}],
        }}]
    }
    final_response = MagicMock()
    final_response.json.return_value = {"choices": [{"message": {"content": "O aracı kullanamam."}}]}

    with patch("httpx.post", side_effect=[unknown_tool_response, final_response]):
        result = await critic.ask_with_tools("var olmayan bir araç dene")

    assert result["tool_calls"][0]["result"]["error"].startswith("unknown_tool")
    assert result["response"] == "O aracı kullanamam."


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
