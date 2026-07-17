import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from app.config import settings


async def validate_provider_base_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Provider base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("Provider base URL cannot contain credentials")
    if parsed.scheme != "https" and not settings.ALLOW_PRIVATE_PROVIDER_URLS:
        raise ValueError("Provider base URL must use HTTPS")
    addresses = await asyncio.to_thread(
        socket.getaddrinfo,
        parsed.hostname,
        parsed.port or (443 if parsed.scheme == "https" else 80),
        type=socket.SOCK_STREAM,
    )
    if not settings.ALLOW_PRIVATE_PROVIDER_URLS:
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise ValueError("Provider base URL resolves to a private or reserved address")
    return normalized
