import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AIProviderConfig(Base):
    __tablename__ = "ai_provider_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    models: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    model: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # TOKEN: price per `token_unit` tokens; REQUEST: fixed price per request
    billing_mode: Mapped[str] = mapped_column(String(20), default="TOKEN", nullable=False)
    input_price: Mapped[float] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    output_price: Mapped[float] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    token_unit: Mapped[int] = mapped_column(Integer, default=1_000_000, nullable=False)
    request_price: Mapped[float] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaymentConfig(Base):
    __tablename__ = "payment_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PromptSkill(Base):
    """Reusable agent prompt preset (built-in or user-defined).

    A skill is a thin profile that customizes the agent loop entry point:
    it injects an extra system prompt, narrows the visible tool catalog,
    and optionally pins a default model component. Skills are *not* tied
    to a fixed text type; that decision is still made by the agent at run
    time based on project content.
    """

    __tablename__ = "prompt_skills"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL → global built-in (catalogue). Non-null → project-scoped custom skill.
    # Uniqueness is enforced via two partial indexes (see migration 006).
    owner_project_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("text_projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Where this skill is offered: one of {"chat", "suggest", "operation"}.
    # A skill may apply to multiple surfaces; we keep this as JSON list.
    scope: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional whitelist of tools to expose to the agent loop. Empty/None
    # means "no extra restriction beyond the default orchestrator set".
    allowed_tools: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    # Optional component key (e.g. "operation_continue") used to route the
    # skill through a specific project model component.
    default_model_component: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Free-form params schema accompanying skill-specific UI inputs.
    params_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
