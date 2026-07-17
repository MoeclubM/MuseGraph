from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import AIProviderConfig, PricingRule
from app.services.provider_models import (
    get_provider_chat_models,
    get_provider_embedding_models,
    get_provider_reranker_models,
)


async def collect_pricing_catalog(
    db: AsyncSession,
    *,
    provider_active_only: bool,
    pricing_active_only: bool,
) -> list[dict[str, Any]]:
    provider_query = select(AIProviderConfig)
    if provider_active_only:
        provider_query = provider_query.where(AIProviderConfig.is_active == True)
    provider_result = await db.execute(provider_query)

    catalog: dict[str, dict[str, Any]] = {}
    for provider in provider_result.scalars().all():
        provider_name = str(provider.name or provider.provider or "").strip()
        for kind, models in (
            ("chat", get_provider_chat_models(provider)),
            ("embedding", get_provider_embedding_models(provider)),
            ("reranker", get_provider_reranker_models(provider)),
        ):
            for model in models:
                row = catalog.setdefault(
                    model,
                    {
                        "id": None,
                        "model": model,
                        "model_type": kind,
                        "providers": [],
                        "has_pricing": False,
                        "billing_mode": "TOKEN",
                        "input_price": 0.0,
                        "output_price": 0.0,
                        "token_unit": 1_000_000,
                        "request_price": 0.0,
                        "is_active": False,
                    },
                )
                if row["model_type"] != kind:
                    row["model_type"] = "mixed"
                if provider_name and provider_name not in row["providers"]:
                    row["providers"].append(provider_name)

    pricing_query = select(PricingRule)
    if pricing_active_only:
        pricing_query = pricing_query.where(PricingRule.is_active == True)
    pricing_result = await db.execute(pricing_query.order_by(PricingRule.model.asc()))
    for rule in pricing_result.scalars().all():
        row = catalog.setdefault(
            rule.model,
            {
                "id": None,
                "model": rule.model,
                "model_type": "unbound",
                "providers": [],
                "has_pricing": False,
                "billing_mode": "TOKEN",
                "input_price": 0.0,
                "output_price": 0.0,
                "token_unit": 1_000_000,
                "request_price": 0.0,
                "is_active": False,
            },
        )
        row.update(
            {
                "id": rule.id,
                "has_pricing": True,
                "billing_mode": str(rule.billing_mode or "TOKEN").upper(),
                "input_price": float(rule.input_price or 0),
                "output_price": float(rule.output_price or 0),
                "token_unit": int(rule.token_unit or 1_000_000),
                "request_price": float(rule.request_price or 0),
                "is_active": bool(rule.is_active),
            }
        )

    return [catalog[model] for model in sorted(catalog)]
