"""Faz 268-sonrası — kullanıcı bulgusu, gerçek olay: NVIDIA API "Server
error '529 status code 529'" döndürdü. llm_reasoner.py::_post_with_retry
geçici sunucu hatalarında (429/500/502/503/504/529) kısa bir bekleyip
tekrar deniyor; kalıcı istemci hatalarında (ör. 401) hiç denemiyor."""
from unittest.mock import MagicMock, patch

import httpx

from llm_reasoner import _post_with_retry


def _response_with_status(status_code: int):
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(status_code, request=request, json={})
    return response


def test_post_with_retry_succeeds_after_transient_server_error():
    responses = [_response_with_status(529), _response_with_status(200)]
    mock_post = MagicMock(side_effect=responses)
    with patch("httpx.post", mock_post), patch("time.sleep") as mock_sleep:
        result = _post_with_retry("https://example.test", headers={}, json_payload={}, timeout_seconds=5)

    assert result.status_code == 200
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once()  # ilk deneme sonrası tek bir bekleme


def test_post_with_retry_gives_up_after_exhausting_retries_on_persistent_server_error():
    responses = [_response_with_status(529)] * 3
    mock_post = MagicMock(side_effect=responses)
    with patch("httpx.post", mock_post), patch("time.sleep"):
        try:
            _post_with_retry("https://example.test", headers={}, json_payload={}, timeout_seconds=5)
            assert False, "HTTPStatusError bekleniyordu"
        except httpx.HTTPStatusError as exc:
            assert exc.response.status_code == 529

    assert mock_post.call_count == 3  # ilk deneme + 2 retry, hepsi tükendi


def test_post_with_retry_does_not_retry_non_transient_client_error():
    """401 (yetkisiz) gibi kalıcı bir istemci hatası — tekrar denemek
    hiçbir şeyi değiştirmez, hemen fırlatılmalı."""
    mock_post = MagicMock(return_value=_response_with_status(401))
    with patch("httpx.post", mock_post), patch("time.sleep") as mock_sleep:
        try:
            _post_with_retry("https://example.test", headers={}, json_payload={}, timeout_seconds=5)
            assert False, "HTTPStatusError bekleniyordu"
        except httpx.HTTPStatusError as exc:
            assert exc.response.status_code == 401

    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


def test_post_with_retry_returns_immediately_on_first_success():
    mock_post = MagicMock(return_value=_response_with_status(200))
    with patch("httpx.post", mock_post), patch("time.sleep") as mock_sleep:
        result = _post_with_retry("https://example.test", headers={}, json_payload={}, timeout_seconds=5)

    assert result.status_code == 200
    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()
