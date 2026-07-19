from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import TextProject
from app.models.runtime import ProjectAgent
from app.services.provider_models import MODEL_REFERENCE_SEPARATOR


async def provider_model_references_in_use(
    db: AsyncSession,
    provider_id: str,
) -> set[str]:
    prefix = f"{provider_id}{MODEL_REFERENCE_SEPARATOR}"
    references = {
        str(value)
        for values in (
            await db.execute(select(TextProject.component_models))
        ).scalars()
        if isinstance(values, dict)
        for value in values.values()
        if str(value).startswith(prefix)
    }
    references.update(
        str(value)
        for value in (
            await db.execute(
                select(ProjectAgent.model).where(ProjectAgent.model.is_not(None))
            )
        ).scalars()
        if str(value).startswith(prefix)
    )
    return references
