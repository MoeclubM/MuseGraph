from __future__ import annotations

from typing import Iterable


DEFAULT_PROVIDER_TYPES: tuple[str, ...] = ("openai_compatible", "anthropic_compatible")


def parse_supported_provider_types(raw: str | None) -> set[str]:
    values: list[str] = []
    if isinstance(raw, str):
        for item in raw.split(","):
            token = item.strip().lower()
            if token:
                values.append(token)
    return set(values or DEFAULT_PROVIDER_TYPES)


def normalize_provider_type(value: str, *, supported: Iterable[str] | None = None) -> str:
    provider = str(value or "").strip().lower()
    if not provider:
        raise ValueError("provider is required")

    if provider == "openai":
        provider = "openai_compatible"
    elif provider == "anthropic":
        provider = "anthropic_compatible"

    supported_values = set(supported or [])
    if supported_values and provider not in supported_values:
        raise ValueError(
            "provider must be one of: " + ", ".join(sorted(supported_values))
        )
    return provider


def is_anthropic_provider(provider: str) -> bool:
    return str(provider or "").strip().lower() == "anthropic_compatible"
