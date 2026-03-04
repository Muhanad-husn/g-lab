"""Unit tests for OpenRouterClient (mocked httpx)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.copilot.openrouter import OpenRouterClient, OpenRouterError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_empty_key_raises() -> None:
    with pytest.raises(ValueError, match="API key is required"):
        OpenRouterClient(api_key="", base_url="https://example.com")


# ---------------------------------------------------------------------------
# Non-streaming completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_completion_success() -> None:
    client = OpenRouterClient(api_key="sk-test", base_url="https://example.com")
    expected = {
        "choices": [{"message": {"content": "Hello!"}}],
    }

    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.post = AsyncMock(return_value=_mock_response(200, expected))

    client._client = mock_http  # type: ignore[assignment]

    result = await client.chat_completion(
        model="test-model",
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert result == expected
    mock_http.post.assert_called_once()
    await client.close()


@pytest.mark.asyncio
async def test_429_retry_then_success() -> None:
    client = OpenRouterClient(api_key="sk-test", base_url="https://example.com")

    rate_limited = _mock_response(429)
    success = _mock_response(200, {"choices": [{"message": {"content": "ok"}}]})

    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.post = AsyncMock(side_effect=[rate_limited, success])

    client._client = mock_http  # type: ignore[assignment]

    with patch("app.services.copilot.openrouter.asyncio.sleep", new_callable=AsyncMock):
        result = await client.chat_completion(
            model="m",
            messages=[{"role": "user", "content": "Hi"}],
        )

    assert result["choices"][0]["message"]["content"] == "ok"
    assert mock_http.post.call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_429_exhausted_raises() -> None:
    client = OpenRouterClient(api_key="sk-test", base_url="https://example.com")

    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.post = AsyncMock(
        return_value=_mock_response(429),
    )

    client._client = mock_http  # type: ignore[assignment]

    with (
        patch(
            "app.services.copilot.openrouter.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        pytest.raises(OpenRouterError, match="Rate limited"),
    ):
        await client.chat_completion(
            model="m",
            messages=[{"role": "user", "content": "Hi"}],
        )

    assert mock_http.post.call_count == 3
    await client.close()


@pytest.mark.asyncio
async def test_non_200_raises() -> None:
    client = OpenRouterClient(api_key="sk-test", base_url="https://example.com")

    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.post = AsyncMock(
        return_value=_mock_response(500, text="Internal Server Error")
    )

    client._client = mock_http  # type: ignore[assignment]

    with pytest.raises(OpenRouterError, match="500"):
        await client.chat_completion(
            model="m",
            messages=[{"role": "user", "content": "Hi"}],
        )
    await client.close()


# ---------------------------------------------------------------------------
# Streaming completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_completion() -> None:
    client = OpenRouterClient(api_key="sk-test", base_url="https://example.com")

    # Build async iterator of SSE lines
    lines = [
        f'data: {json.dumps({"choices": [{"delta": {"content": "Hello"}}]})}',
        f'data: {json.dumps({"choices": [{"delta": {"content": " world"}}]})}',
        "data: [DONE]",
    ]

    async def fake_aiter_lines():  # type: ignore[no-untyped-def]
        for line in lines:
            yield line

    # Mock the streaming context manager
    mock_stream_resp = AsyncMock()
    mock_stream_resp.status_code = 200
    mock_stream_resp.aiter_lines = fake_aiter_lines

    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.stream = MagicMock(return_value=AsyncContextManagerMock(mock_stream_resp))

    client._client = mock_http  # type: ignore[assignment]

    result = await client.chat_completion(
        model="m",
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    )
    assert result == ["Hello", " world"]
    await client.close()


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_success() -> None:
    client = OpenRouterClient(api_key="sk-test", base_url="https://example.com")

    models_data = [
        {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku"},
        {"id": "openai/gpt-4o", "name": "GPT-4o"},
    ]

    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.get = AsyncMock(
        return_value=_mock_response(200, {"data": models_data})
    )

    client._client = mock_http  # type: ignore[assignment]

    result = await client.list_models()
    assert len(result) == 2
    assert result[0]["id"] == "anthropic/claude-3-haiku"
    await client.close()


@pytest.mark.asyncio
async def test_list_models_error() -> None:
    client = OpenRouterClient(api_key="sk-test", base_url="https://example.com")

    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.get = AsyncMock(return_value=_mock_response(401))

    client._client = mock_http  # type: ignore[assignment]

    with pytest.raises(OpenRouterError, match="401"):
        await client.list_models()
    await client.close()


# ---------------------------------------------------------------------------
# validate_api_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_key_valid() -> None:
    client = OpenRouterClient(api_key="sk-test", base_url="https://example.com")

    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.get = AsyncMock(return_value=_mock_response(200, {"data": []}))

    client._client = mock_http  # type: ignore[assignment]

    assert await client.validate_api_key() is True
    await client.close()


@pytest.mark.asyncio
async def test_validate_key_invalid() -> None:
    client = OpenRouterClient(api_key="sk-bad", base_url="https://example.com")

    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.get = AsyncMock(return_value=_mock_response(401))

    client._client = mock_http  # type: ignore[assignment]

    assert await client.validate_api_key() is False
    await client.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class AsyncContextManagerMock:
    """Helper to mock an async context manager (``async with client.stream(...)``)."""

    def __init__(self, return_value: object) -> None:
        self._value = return_value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, *_: object) -> None:
        pass
