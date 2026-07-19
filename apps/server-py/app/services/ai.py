from __future__ import annotations

import asyncio
import json
import re
from decimal import Decimal
from typing import Any

import httpx
import litellm
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import AIProviderConfig, PaymentConfig, PricingRule
from app.models.user import User
from app.services.llm_runtime import default_llm_runtime_config, normalize_llm_runtime_config
from app.services.provider_models import (
    get_provider_chat_models,
    get_provider_embedding_models,
    get_provider_reranker_models,
)
from app.services.provider_type import is_anthropic_provider
from app.services.secret_crypto import decrypt_secret


MONEY_SCALE = Decimal("0.000001")
SUPPORTED_LLM_PROVIDERS = {"openai_compatible", "anthropic_compatible"}


async def _sanitize_openai_sdk_headers(request: httpx.Request) -> None:
    for name in list(request.headers):
        if name.lower().startswith("x-stainless-") and name.lower() != "x-stainless-raw-response":
            del request.headers[name]
    request.headers["User-Agent"] = "MuseGraph/1.0"


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_SCALE)


async def _collect_available_models(db: AsyncSession, kind: str) -> list[dict[str, str]]:
    providers = (
        await db.execute(
            select(AIProviderConfig)
            .where(AIProviderConfig.is_active.is_(True))
            .order_by(AIProviderConfig.priority.desc(), AIProviderConfig.name)
        )
    ).scalars()
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for provider in providers:
        if kind == "embedding":
            models = get_provider_embedding_models(provider)
        elif kind == "reranker":
            models = get_provider_reranker_models(provider)
        else:
            models = get_provider_chat_models(provider)
        for model in models:
            if model not in seen:
                seen.add(model)
                result.append({"id": model, "provider": provider.name, "name": model})
    return result


async def get_available_models(db: AsyncSession) -> list[dict[str, str]]:
    return await _collect_available_models(db, "chat")


async def get_available_embedding_models(db: AsyncSession) -> list[dict[str, str]]:
    return await _collect_available_models(db, "embedding")


async def get_available_reranker_models(db: AsyncSession) -> list[dict[str, str]]:
    return await _collect_available_models(db, "reranker")


async def rerank_knowledge_records(
    model: str,
    query: str,
    records: list[dict[str, Any]],
    db: AsyncSession,
) -> list[tuple[dict[str, Any], float]]:
    provider_config = next(
        (
            provider
            for provider in (
                await db.execute(
                    select(AIProviderConfig)
                    .where(AIProviderConfig.is_active.is_(True))
                    .order_by(AIProviderConfig.priority.desc(), AIProviderConfig.name)
                )
            ).scalars()
            if model in get_provider_reranker_models(provider)
        ),
        None,
    )
    if provider_config is None:
        raise ValueError(f'No active provider has registered reranker model "{model}"')
    if provider_config.provider != "openai_compatible":
        raise ValueError("Knowledge reranker provider must be OpenAI-compatible")

    runtime = await _runtime_config(db)
    async with httpx.AsyncClient(timeout=int(runtime["llm_request_timeout_seconds"])) as client:
        response = await client.post(
            f"{str(provider_config.base_url or 'https://api.openai.com/v1').rstrip('/')}/rerank",
            headers={
                "Authorization": f"Bearer {decrypt_secret(provider_config.api_key)}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "query": query,
                "documents": [
                    f"{record['id']}\n{record['title']}\n{record['content']}"
                    for record in records
                ],
                "top_n": len(records),
            },
        )
        response.raise_for_status()
        results = response.json()["results"]

    ranked: list[tuple[dict[str, Any], float]] = []
    seen: set[int] = set()
    for item in results:
        index = int(item["index"])
        if index < 0 or index >= len(records) or index in seen:
            raise RuntimeError("Reranker returned an invalid document index")
        seen.add(index)
        ranked.append((records[index], float(item["relevance_score"])))
    if len(ranked) != len(records):
        raise RuntimeError("Reranker did not return every knowledge record")
    return ranked


async def _runtime_config(db: AsyncSession) -> dict[str, Any]:
    item = (
        await db.execute(select(PaymentConfig).where(PaymentConfig.type == "llm_runtime"))
    ).scalar_one_or_none()
    if item is None:
        return default_llm_runtime_config()
    return normalize_llm_runtime_config(item.config)


def _schema_name(schema: type[BaseModel] | dict[str, Any]) -> str:
    name = schema.__name__ if isinstance(schema, type) else "structured_output"
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name)[:64]


def _schema_payload(schema: type[BaseModel] | dict[str, Any]) -> dict[str, Any]:
    return schema.model_json_schema() if isinstance(schema, type) else schema


def _response_content(response: Any) -> str:
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict)
        )
    return str(content or "")


def _tool_call_arguments(response: Any, tool_name: str) -> str:
    calls = response.choices[0].message.tool_calls or []
    if len(calls) != 1:
        raise RuntimeError(
            f'LLM must call structured output tool "{tool_name}" exactly once'
        )
    function = calls[0].function
    if function.name != tool_name:
        raise RuntimeError(
            f'LLM called "{function.name}" instead of structured output tool "{tool_name}"'
        )
    return function.arguments


def _usage_value(usage: Any, *names: str) -> int:
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value is not None:
            return int(value)
    return 0


async def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    db: AsyncSession,
) -> Decimal:
    rule = (
        await db.execute(
            select(PricingRule).where(
                PricingRule.model == model,
                PricingRule.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if rule is None:
        return _money(0)
    if rule.billing_mode == "REQUEST":
        return _money(rule.request_price)
    return _money(
        Decimal(str(rule.input_price)) * max(0, input_tokens) / rule.token_unit
        + Decimal(str(rule.output_price)) * max(0, output_tokens) / rule.token_unit
    )


async def call_llm(
    model: str,
    prompt: str,
    db: AsyncSession,
    max_tokens: int = 1024,
    *,
    billing_user_id: str | None = None,
    billing_project_id: str | None = None,
    billing_operation_id: str | None = None,
    prefer_stream_override: bool | None = None,
    minimum_timeout_seconds: int | None = None,
    response_schema: type[BaseModel] | dict[str, Any] | None = None,
    response_schema_name: str | None = None,
    stream_callback: Any = None,
    thinking_stream_callback: Any = None,
    reasoning_effort_override: str | None = None,
) -> dict[str, Any]:
    del prefer_stream_override, stream_callback, thinking_stream_callback
    selected_model = model.strip()
    if not selected_model:
        raise ValueError("A model must be selected for this Agent run")

    providers = list(
        (
            await db.execute(
                select(AIProviderConfig)
                .where(AIProviderConfig.is_active.is_(True))
                .order_by(AIProviderConfig.priority.desc(), AIProviderConfig.name)
            )
        ).scalars()
    )
    provider_config = next(
        (
            provider
            for provider in providers
            if selected_model in get_provider_chat_models(provider)
        ),
        None,
    )
    if provider_config is None:
        raise ValueError(f'No active provider has registered model "{selected_model}"')
    provider = provider_config.provider.strip().lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")

    api_key = decrypt_secret(provider_config.api_key)
    if not api_key:
        raise ValueError(f'Provider "{provider_config.name}" has no API key')
    runtime = await _runtime_config(db)
    timeout = int(runtime["llm_request_timeout_seconds"])
    if minimum_timeout_seconds is not None:
        timeout = max(timeout, int(minimum_timeout_seconds))

    request_prompt = prompt
    structured_tool_name: str | None = None
    kwargs: dict[str, Any] = {
        "model": selected_model,
        "messages": [{"role": "user", "content": request_prompt}],
        "max_tokens": max_tokens,
        "api_key": api_key,
        "custom_llm_provider": "anthropic" if is_anthropic_provider(provider) else "openai",
        "extra_headers": {"User-Agent": "MuseGraph/1.0"},
    }
    if provider_config.base_url:
        api_base = provider_config.base_url.rstrip("/")
        kwargs["api_base"] = (
            api_base.removesuffix("/v1")
            if is_anthropic_provider(provider)
            else api_base
        )
    if selected_model.startswith("deepseek-v4-") and (
        response_schema is not None or not reasoning_effort_override
    ):
        if is_anthropic_provider(provider):
            kwargs["thinking"] = {"type": "disabled"}
            kwargs["allowed_openai_params"] = ["thinking"]
        else:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    if reasoning_effort_override:
        kwargs["reasoning_effort"] = reasoning_effort_override
        kwargs["allowed_openai_params"] = [
            *kwargs.get("allowed_openai_params", []),
            "reasoning_effort",
        ]
    if response_schema is not None:
        schema_name = response_schema_name or _schema_name(response_schema)
        schema = _schema_payload(response_schema)
        if is_anthropic_provider(provider):
            kwargs["messages"] = [
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\nReturn only JSON matching this schema:\n"
                        f"{json.dumps(schema, ensure_ascii=False)}"
                    ),
                },
                {"role": "assistant", "content": "{"},
            ]
        else:
            structured_tool_name = f"submit_{schema_name}"[:64]
            parameters = (
                schema
                if schema.get("type") == "object"
                else {"type": "object", **schema}
            )
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": structured_tool_name,
                        "description": "Submit the response matching the required schema.",
                        "parameters": parameters,
                    },
                }
            ]
            kwargs["tool_choice"] = {
                "type": "function",
                "function": {"name": structured_tool_name},
            }

    if is_anthropic_provider(provider):
        response = await asyncio.wait_for(litellm.acompletion(**kwargs), timeout=timeout)
    else:
        async with httpx.AsyncClient(
            event_hooks={"request": [_sanitize_openai_sdk_headers]}
        ) as http_client:
            kwargs["client"] = AsyncOpenAI(
                api_key=api_key,
                base_url=provider_config.base_url or "https://api.openai.com/v1",
                http_client=http_client,
                timeout=timeout,
                max_retries=0,
            )
            response = await asyncio.wait_for(litellm.acompletion(**kwargs), timeout=timeout)
    content = (
        _tool_call_arguments(response, structured_tool_name)
        if structured_tool_name
        else _response_content(response)
    )
    if not content.strip():
        raise RuntimeError(f'LLM returned empty content for model "{selected_model}"')
    usage = getattr(response, "usage", None)
    input_tokens = _usage_value(usage, "prompt_tokens", "input_tokens")
    output_tokens = _usage_value(usage, "completion_tokens", "output_tokens")
    cost = await calculate_cost(selected_model, input_tokens, output_tokens, db)

    if billing_user_id:
        from app.services.usage_records import create_usage_record, resolve_billing_mode

        user = (
            await db.execute(select(User).where(User.id == billing_user_id))
        ).scalar_one()
        await create_usage_record(
            db=db,
            user_id=billing_user_id,
            model=selected_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            project_id=billing_project_id,
            operation_id=billing_operation_id,
            provider=provider,
            billing_mode=await resolve_billing_mode(selected_model, db),
            source="llm",
            user_balance_holder=user,
        )

    return {
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "provider": provider,
        "model": selected_model,
        "cost": cost,
        "usage_recorded": billing_user_id is not None,
    }
