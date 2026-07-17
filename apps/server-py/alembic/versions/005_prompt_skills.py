"""prompt skills catalog

Revision ID: 005
Revises: 004
Create Date: 2026-06-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_skills",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("icon", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("scope", postgresql.JSON, nullable=True),
        sa.Column("tags", postgresql.JSON, nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("allowed_tools", postgresql.JSON, nullable=True),
        sa.Column("default_model_component", sa.String(64), nullable=True),
        sa.Column("params_schema", postgresql.JSON, nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_prompt_skills_active_sort", "prompt_skills", ["is_active", "sort_order"])


def downgrade() -> None:
    op.drop_index("ix_prompt_skills_active_sort", table_name="prompt_skills")
    op.drop_table("prompt_skills")
