"""Async OpenRouter API client.

Wraps httpx for chat completions (streaming + non-streaming),
model listing, and API key validation. Retries on 429 with
exponential backoff (3 attempts).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.logging import get_logger

logger: Any = get_logger(__name__)

# Retry configuration for 429 Too Many Requests
_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds


class OpenRouterError(Exception):
    """Raised on non-retryable OpenRouter API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class OpenRouterClient:
    """Async client for the OpenRouter API."""

    def __init__(self, api_key: str, base_url: str) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://g-lab.local",
                    "X-Title": "G-Lab",
                },
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def validate_api_key(self) -> bool:
        """Check whether the configured API key is valid.

        Calls /models as a lightweight validation probe.
        """
        try:
            await self.list_models()
            return True
        except OpenRouterError:
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        """Fetch available models from OpenRouter.

        Returns a list of model dicts with at least ``id`` and ``name``.
        """
        client = await self._get_client()
        resp = await client.get("/models")
        if resp.status_code != 200:
            raise OpenRouterError(
                f"Failed to list models: {resp.status_code}",
                status_code=resp.status_code,
            )
        body = resp.json()
        return body.get("data", [])  # type: ignore[no-any-return]

    async def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> dict[str, Any] | list[str]:
        """Send a chat completion request to OpenRouter.

        Args:
            model: Model ID (e.g. "anthropic/claude-3-haiku").
            messages: Chat messages in OpenAI format.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            stream: If True, returns a list of content chunks.

        Returns:
            Full response dict (non-streaming) or list of text chunks (streaming).
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if stream:
            return await self._stream_completion(payload)
        return await self._single_completion(payload)

    async def _single_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Non-streaming completion with 429 retry."""
        client = await self._get_client()

        for attempt in range(_MAX_RETRIES):
            resp = await client.post("/chat/completions", json=payload)

            if resp.status_code == 429:
                if attempt < _MAX_RETRIES - 1:
                    delay = _BASE_DELAY * (2**attempt)
                    logger.warning(
                        "openrouter_rate_limited",
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise OpenRouterError(
                    "Rate limited after max retries",
                    status_code=429,
                )

            if resp.status_code != 200:
                raise OpenRouterError(
                    f"Chat completion failed: {resp.status_code} {resp.text}",
                    status_code=resp.status_code,
                )

            return resp.json()  # type: ignore[no-any-return]

        raise OpenRouterError("Unexpected retry exhaustion")  # pragma: no cover

    async def _stream_completion(self, payload: dict[str, Any]) -> list[str]:
        """Streaming completion — collects text chunks into a list.

        For the real pipeline, use ``stream_completion_iter`` for an async
        iterator. This method is a convenience for simpler use cases.
        """
        chunks: list[str] = []
        async for chunk in self.stream_completion_iter(payload):
            chunks.append(chunk)
        return chunks

    async def stream_completion_iter(self, payload: dict[str, Any]) -> Any:
        """Yield text chunks from a streaming completion.

        Implements 429 retry at the connection level.
        """
        client = await self._get_client()
        payload = {**payload, "stream": True}

        for attempt in range(_MAX_RETRIES):
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                if resp.status_code == 429:
                    if attempt < _MAX_RETRIES - 1:
                        delay = _BASE_DELAY * (2**attempt)
                        logger.warning(
                            "openrouter_stream_rate_limited",
                            attempt=attempt + 1,
                            delay=delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise OpenRouterError(
                        "Rate limited after max retries",
                        status_code=429,
                    )

                if resp.status_code != 200:
                    body = await resp.aread()
                    raise OpenRouterError(
                        f"Stream failed: {resp.status_code} {body.decode()}",
                        status_code=resp.status_code,
                    )

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        return
                    try:
                        import json

                        parsed = json.loads(data)
                        choices = parsed.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                return
