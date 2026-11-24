"""Shared outbound HTTP client."""
from __future__ import annotations

import httpx

from ..config import APP_NAME, APP_VERSION, get_settings

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        settings = get_settings()
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout, connect=15.0),
            headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
