import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import Usage
from app.models.config import AIProviderConfig, PricingRule, PromptTemplate
from app.models.project import TextOperation, TextProject
from app.models.user import User
from app.redis import redis_client


OPERATION_PROMPTS = {
    "CREATE": "You are a creative writing assistant. Based on the following prompt, create original content:\n\n{input}",
    "CONTINUE": "You are a creative writing assistant. Continue the following text naturally:\n\n{input}",
    "ANALYZE": "You are a text analysis expert. Analyze the following text in detail:\n\n{input}",
    "REWRITE": "You are a professional editor. Rewrite the following text to improve clarity and style:\n\n{input}",
    "SUMMARIZE": "You are a summarization expert. Provide a concise summary of the following text:\n\n{input}",
}

DEFAULT_MODEL = "gpt-4o-mini"

OPERATION_COMPONENT_KEYS = {
    "CREATE": "operation_create",
    "CONTINUE": "operation_continue",
    "ANALYZE": "operation_analyze",
    "REWRITE": "operation_rewrite",
    "SUMMARIZE": "operation_summarize",
}


def component_key_for_operation(op_type: str) -> str:
    return OPERATION_COMPONENT_KEYS.get((op_type or "").upper(), "operation_default")


def resolve_component_model(
    project: TextProject | None,
    component_key: str,
    explicit_model: str | None = None,
    fallback_model: str = DEFAULT_MODEL,
) -> str:
    candidate = (explicit_model or "").strip()
    if candidate:
        return candidate

    component_models: dict[str, Any] = {}
    if project and isinstance(project.component_models, dict):
        component_models = project.component_models

    configured = component_models.get(component_key)
    if not configured and component_key.startswith("operation_"):
        configured = component_models.get("operation_default")
    if not configured:
        configured = component_models.get("default")

    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return fallback_model


async def get_available_models(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.is_active == True)
    )
    providers = result.scalars().all()
    models = []
    for p in providers:
        if p.models:
            for model_id in p.models:
                models.append({"id": model_id, "provider": p.provider, "name": model_id})
    return models


async def get_prompt(op_type: str, input_text: str, db: AsyncSession) -> str:
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.type == op_type, PromptTemplate.is_active == True
        )
    )
    template = result.scalar_one_or_none()
    if template:
        return template.template.replace("{input}", input_text)
    return OPERATION_PROMPTS.get(op_type, "{input}").replace("{input}", input_text)


def detect_provider(model: str) -> str:
    if model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return "openai"
    if model.startswith("claude"):
        return "anthropic"
    return "openai"


async def call_llm(model: str, prompt: str, db: AsyncSession) -> dict:
    model = (model or "").strip() or DEFAULT_MODEL
    # First try to find a provider config that has this model in its models list
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.is_active == True)
    )
    configs = result.scalars().all()

    config = None
    for c in configs:
        if c.models and model in c.models:
            config = c
            break

    if not config:
        # Fall back to provider detection by model name prefix
        provider = detect_provider(model)
        for c in configs:
            if c.provider == provider:
                config = c
                break

    provider = config.provider if config else detect_provider(model)
    api_key = config.api_key if config else (
        settings.OPENAI_API_KEY if provider == "openai" else settings.ANTHROPIC_API_KEY
    )
    base_url = config.base_url if config and config.base_url else None

    # Use OpenAI-compatible client for non-anthropic providers or when base_url is set
    if provider != "anthropic" or base_url:
        import openai
        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return {
            "content": response.choices[0].message.content,
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        }
    else:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "content": response.content[0].text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }


async def calculate_cost(
    model: str, input_tokens: int, output_tokens: int, db: AsyncSession
) -> Decimal:
    result = await db.execute(
        select(PricingRule).where(
            PricingRule.model == model, PricingRule.is_active == True
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        return Decimal("0")
    cost = (
        Decimal(str(rule.input_price)) * input_tokens / 1000
        + Decimal(str(rule.output_price)) * output_tokens / 1000
    )
    return cost.quantize(Decimal("0.000001"))


async def run_operation(
    operation_id: str,
    project: TextProject,
    user: User,
    op_type: str,
    input_text: str,
    model: str,
    db: AsyncSession,
) -> TextOperation:
    result = await db.execute(
        select(TextOperation).where(TextOperation.id == operation_id)
    )
    operation = result.scalar_one()

    try:
        operation.status = "PROCESSING"
        operation.progress = 10
        operation.message = "Preparing prompt..."
        await db.flush()

        prompt = await get_prompt(op_type, input_text or project.content or "", db)

        # Enhance with knowledge graph prediction for CONTINUE/CREATE
        try:
            from app.services.prediction import get_enhanced_prompt
            prompt = await get_enhanced_prompt(
                project.id, op_type, input_text or project.content or "", prompt, db
            )
        except Exception:
            pass  # Fall back to base prompt

        operation.progress = 30
        operation.message = "Calling AI model..."
        await db.flush()

        llm_result = await call_llm(model, prompt, db)

        operation.progress = 80
        operation.message = "Processing result..."
        await db.flush()

        cost = await calculate_cost(
            model, llm_result["input_tokens"], llm_result["output_tokens"], db
        )

        operation.output = llm_result["content"]
        operation.input_tokens = llm_result["input_tokens"]
        operation.output_tokens = llm_result["output_tokens"]
        operation.cost = cost
        operation.status = "COMPLETED"
        operation.progress = 100
        operation.message = "Done"
        await db.flush()

        # Deduct balance
        user.balance -= cost
        await db.flush()

        # Record usage
        usage = Usage(
            user_id=user.id,
            project_id=project.id,
            operation_id=operation.id,
            model=model,
            input_tokens=llm_result["input_tokens"],
            output_tokens=llm_result["output_tokens"],
            cost=cost,
        )
        db.add(usage)
        await db.flush()

    except Exception as e:
        operation.status = "FAILED"
        operation.error = str(e)
        operation.progress = 0
        operation.message = "Failed"
        await db.flush()

    return operation


async def run_operation_async(
    operation_id: str,
    project_id: str,
    user_id: str,
    op_type: str,
    input_text: str | None,
    model: str,
):
    """Run operation in background and publish progress via Redis."""
    from app.database import async_session

    async with async_session() as db:
        try:
            result = await db.execute(
                select(TextOperation).where(TextOperation.id == operation_id)
            )
            operation = result.scalar_one()
            result = await db.execute(
                select(TextProject).where(TextProject.id == project_id)
            )
            project = result.scalar_one()
            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one()

            channel = f"operation:{operation_id}"

            operation.status = "PROCESSING"
            operation.progress = 10
            operation.message = "Preparing prompt..."
            await db.flush()
            await redis_client.publish(
                channel,
                json.dumps({
                    "progress": 10,
                    "status": "PROCESSING",
                    "message": "Preparing prompt...",
                }),
            )

            prompt = await get_prompt(
                op_type, input_text or project.content or "", db
            )

            # Enhance with knowledge graph prediction for CONTINUE/CREATE
            try:
                from app.services.prediction import get_enhanced_prompt
                prompt = await get_enhanced_prompt(
                    project.id, op_type, input_text or project.content or "", prompt, db
                )
            except Exception:
                pass  # Fall back to base prompt

            operation.progress = 30
            operation.message = "Calling AI model..."
            await db.flush()
            await redis_client.publish(
                channel,
                json.dumps({
                    "progress": 30,
                    "status": "PROCESSING",
                    "message": "Calling AI model...",
                }),
            )

            llm_result = await call_llm(model, prompt, db)

            operation.progress = 80
            operation.message = "Processing result..."
            await db.flush()
            await redis_client.publish(
                channel,
                json.dumps({
                    "progress": 80,
                    "status": "PROCESSING",
                    "message": "Processing result...",
                }),
            )

            cost = await calculate_cost(
                model, llm_result["input_tokens"], llm_result["output_tokens"], db
            )

            operation.output = llm_result["content"]
            operation.input_tokens = llm_result["input_tokens"]
            operation.output_tokens = llm_result["output_tokens"]
            operation.cost = cost
            operation.status = "COMPLETED"
            operation.progress = 100
            operation.message = "Done"

            user.balance -= cost
            usage = Usage(
                user_id=user.id,
                project_id=project.id,
                operation_id=operation.id,
                model=model,
                input_tokens=llm_result["input_tokens"],
                output_tokens=llm_result["output_tokens"],
                cost=cost,
            )
            db.add(usage)
            await db.commit()

            await redis_client.publish(
                channel,
                json.dumps({
                    "progress": 100,
                    "status": "COMPLETED",
                    "message": "Done",
                    "output": llm_result["content"],
                }),
            )

        except Exception as e:
            operation.status = "FAILED"
            operation.error = str(e)
            operation.progress = 0
            await db.commit()
            await redis_client.publish(
                channel,
                json.dumps({
                    "progress": 0,
                    "status": "FAILED",
                    "message": str(e),
                }),
            )
