"""current development schema

Revision ID: 001
Revises:
Create Date: 2026-02-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("nickname", sa.String(100), nullable=True),
        sa.Column("avatar", sa.String(500), nullable=True),
        sa.Column("balance", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(500), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "text_projects",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(20), server_default="private", nullable=False),
        sa.Column("component_models", postgresql.JSON, nullable=True),
        sa.Column("operation_prompts", postgresql.JSON, nullable=True),
        sa.Column("ontology_schema", postgresql.JSON, nullable=True),
        sa.Column("creative_state", postgresql.JSON, nullable=True),
        sa.Column("memory_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("visibility IN ('private', 'public')", name="ck_text_projects_visibility"),
    )
    op.create_index("ix_text_projects_user_id", "text_projects", ["user_id"])
    op.create_index("ix_text_projects_visibility_updated", "text_projects", ["visibility", "updated_at"])

    op.create_table(
        "project_members",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="ck_project_members_role"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])

    op.create_table(
        "text_project_chapters",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), server_default="Main Draft", nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("blueprint", postgresql.JSON, nullable=True),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("continuity_notes", postgresql.JSON, nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_text_project_chapters_project_id", "text_project_chapters", ["project_id"])
    op.create_index("ix_text_project_chapters_project_order", "text_project_chapters", ["project_id", "order_index"])

    op.create_table(
        "text_project_characters",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("profile", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_text_project_characters_project_id", "text_project_characters", ["project_id"])
    op.create_index("ix_text_project_characters_project_order", "text_project_characters", ["project_id", "order_index"])

    op.create_table(
        "text_project_glossary_terms",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term", sa.String(255), nullable=False),
        sa.Column("definition", sa.Text(), server_default="", nullable=False),
        sa.Column("aliases", postgresql.JSON, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_text_project_glossary_terms_project_id", "text_project_glossary_terms", ["project_id"])
    op.create_index("ix_text_project_glossary_terms_project_order", "text_project_glossary_terms", ["project_id", "order_index"])

    op.create_table(
        "text_project_worldbook_entries",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(120), nullable=True),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("tags", postgresql.JSON, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_text_project_worldbook_entries_project_id", "text_project_worldbook_entries", ["project_id"])
    op.create_index("ix_text_project_worldbook_entries_project_order", "text_project_worldbook_entries", ["project_id", "order_index"])

    op.create_table(
        "text_operations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("metadata", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_text_operations_project_id", "text_operations", ["project_id"])
    op.create_index("ix_text_operations_status", "text_operations", ["status"])

    op.create_table(
        "usages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("operation_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "deposits",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 4), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("payment_id", sa.String(255), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_no", sa.String(100), unique=True, nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(10, 4), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("payment_id", sa.String(255), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "ai_provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("api_key", sa.String(500), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("models", postgresql.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "pricing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("model", sa.String(100), unique=True, nullable=False),
        sa.Column("billing_mode", sa.String(20), server_default="TOKEN", nullable=False),
        sa.Column("input_price", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column("output_price", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column("token_unit", sa.Integer(), server_default="1000000", nullable=False),
        sa.Column("request_price", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "payment_configs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("prompt_templates")
    op.drop_table("payment_configs")
    op.drop_table("pricing_rules")
    op.drop_table("ai_provider_configs")
    op.drop_table("orders")
    op.drop_table("deposits")
    op.drop_table("usages")
    op.drop_table("text_operations")
    op.drop_table("text_project_worldbook_entries")
    op.drop_table("text_project_glossary_terms")
    op.drop_table("text_project_characters")
    op.drop_table("text_project_chapters")
    op.drop_table("project_members")
    op.drop_table("text_projects")
    op.drop_table("sessions")
    op.drop_table("users")
