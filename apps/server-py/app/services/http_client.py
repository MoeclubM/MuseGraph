"""Shared HTTP client helpers for Docker/WSL environments without working IPv6 egress."""

from __future__ import annotations

import httpx
import litellm

_IPV4_CONFIGURED = False


def configure_litellm_ipv4() -> None:
    """Force LiteLLM to use IPv4-only httpx transport (avoids Docker IPv6 hang)."""
    global _IPV4_CONFIGURED
    if _IPV4_CONFIGURED:
        return
    litellm.force_ipv4 = True
    litellm.disable_aiohttp_transport = True
    _IPV4_CONFIGURED = True


def create_async_http_client(**kwargs) -> httpx.AsyncClient:
    """Create an httpx AsyncClient bound to IPv4 (local_address=0.0.0.0)."""
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    return httpx.AsyncClient(transport=transport, **kwargs)