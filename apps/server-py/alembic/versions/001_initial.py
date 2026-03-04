"""initial schema - all tables

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
    # ── user_groups ──────────────────────────────────────────────
    op.create_table(
        "user_groups",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── users ────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("nickname", sa.String(100), nullable=True),
        sa.Column("avatar", sa.String(500), nullable=True),
        sa.Column("balance", sa.Numeric(12, 6), server_default="0"),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false")),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user_groups.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── sessions ─────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(500), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # ── text_projects ────────────────────────────────────────────
    op.create_table(
        "text_projects",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("cognee_dataset_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_text_projects_user_id", "text_projects", ["user_id"])

    # ── text_operations ──────────────────────────────────────────
    op.create_table(
        "text_operations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("text_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("input", sa.Text, nullable=True),
        sa.Column("output", sa.Text, nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer, server_default="0"),
        sa.Column("output_tokens", sa.Integer, server_default="0"),
        sa.Column("cost", sa.Numeric(10, 6), server_default="0"),
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("progress", sa.Integer, server_default="0"),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("metadata", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_text_operations_project_id", "text_operations", ["project_id"])
    op.create_index("ix_text_operations_status", "text_operations", ["status"])

    # ── usages ───────────────────────────────────────────────────
    op.create_table(
        "usages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("operation_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer, server_default="0"),
        sa.Column("output_tokens", sa.Integer, server_default="0"),
        sa.Column("cost", sa.Numeric(10, 6), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── deposits ─────────────────────────────────────────────────
    op.create_table(
        "deposits",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(10, 4), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("payment_id", sa.String(255), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── plans ────────────────────────────────────────────────────
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("target_group_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("duration", sa.Integer, nullable=False),
        sa.Column("rate_limit", sa.Integer, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── orders ───────────────────────────────────────────────────
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_no", sa.String(100), unique=True, nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("amount", sa.Numeric(10, 4), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("payment_id", sa.String(255), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── subscriptions ────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("plans.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_renew", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── ai_provider_configs ──────────────────────────────────────
    op.create_table(
        "ai_provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("api_key", sa.String(500), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("models", postgresql.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── pricing_rules ────────────────────────────────────────────
    op.create_table(
        "pricing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("model", sa.String(100), unique=True, nullable=False),
        sa.Column("input_price", sa.Numeric(10, 6), nullable=False),
        sa.Column("output_price", sa.Numeric(10, 6), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── model_group_bindings ────────────────────────────────────
    op.create_table(
        "model_group_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("model", "group_id", name="uq_model_group_bindings_model_group"),
    )

    # ── payment_configs ──────────────────────────────────────────
    op.create_table(
        "payment_configs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── prompt_templates ─────────────────────────────────────────
    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("variables", postgresql.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("prompt_templates")
    op.drop_table("payment_configs")
    op.drop_table("model_group_bindings")
    op.drop_table("pricing_rules")
    op.drop_table("ai_provider_configs")
    op.drop_table("subscriptions")
    op.drop_table("orders")
    op.drop_table("plans")
    op.drop_table("deposits")
    op.drop_table("usages")
    op.drop_index("ix_text_operations_status", table_name="text_operations")
    op.drop_index("ix_text_operations_project_id", table_name="text_operations")
    op.drop_table("text_operations")
    op.drop_index("ix_text_projects_user_id", table_name="text_projects")
    op.drop_table("text_projects")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("user_groups")
