import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.config import AIProviderConfig, PricingRule
from app.services.provider_models import get_provider_chat_models, set_provider_chat_models
from app.services.provider_type import normalize_provider_type, parse_supported_provider_types

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDER_TYPES = parse_supported_provider_types(settings.SUPPORTED_PROVIDER_TYPES)


def _resolve_provider_api_key() -> str:
    candidates = [
        settings.NEWAPI_API_KEY,
        settings.LLM_API_KEY,
        settings.OPENAI_API_KEY,
    ]
    for item in candidates:
        value = str(item or "").strip()
        if value:
            return value
    return ""


async def bootstrap_default_provider_and_pricing(db: AsyncSession) -> None:
    if not settings.AUTO_BOOTSTRAP_NEWAPI:
        return

    model = str(settings.NEWAPI_MODEL or "").strip() or str(settings.LLM_MODEL or "").strip()
    if not model:
        logger.warning("Skip default AI bootstrap: NEWAPI_MODEL/LLM_MODEL is empty.")
        return

    provider_name = str(settings.NEWAPI_PROVIDER_NAME or "").strip() or "NewAPI"
    provider_type = normalize_provider_type(
        str(settings.NEWAPI_PROVIDER_TYPE or "").strip().lower() or "openai_compatible",
        supported=SUPPORTED_PROVIDER_TYPES,
    )

    base_url = str(settings.NEWAPI_BASE_URL or "").strip() or str(settings.LLM_ENDPOINT or "").strip() or None
    api_key = _resolve_provider_api_key()
    input_price = float(settings.NEWAPI_INPUT_PRICE)
    output_price = float(settings.NEWAPI_OUTPUT_PRICE)
    priority = int(settings.NEWAPI_PROVIDER_PRIORITY)

    provider_result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.name == provider_name)
    )
    provider = provider_result.scalar_one_or_none()

    if not provider:
        provider = AIProviderConfig(
            name=provider_name,
            provider=provider_type,
            api_key=api_key,
            base_url=base_url,
            models=[model],
            is_active=True,
            priority=priority,
        )
        db.add(provider)
    else:
        provider.provider = provider_type
        provider.base_url = base_url
        provider.is_active = True
        provider.priority = priority
        if api_key:
            provider.api_key = api_key
        models = get_provider_chat_models(provider)
        if model not in models:
            models.append(model)
        set_provider_chat_models(provider, sorted(set(models)))

    rule_result = await db.execute(
        select(PricingRule).where(PricingRule.model == model)
    )
    rule = rule_result.scalar_one_or_none()
    if not rule:
        rule = PricingRule(
            model=model,
            billing_mode="TOKEN",
            input_price=input_price,
            output_price=output_price,
            token_unit=1_000_000,
            request_price=0,
            is_active=True,
        )
        db.add(rule)
    else:
        rule.billing_mode = "TOKEN"
        rule.input_price = input_price
        rule.output_price = output_price
        rule.token_unit = 1_000_000
        rule.request_price = 0
        rule.is_active = True

    await db.commit()
    logger.info(
        "Default AI bootstrap finished: provider=%s model=%s input=%s output=%s",
        provider_name,
        model,
        input_price,
        output_price,
    )
