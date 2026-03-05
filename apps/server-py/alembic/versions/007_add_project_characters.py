"""add project characters table

Revision ID: 007_project_characters
Revises: 006_balance_precision
Create Date: 2026-03-05 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_project_characters"
down_revision: Union[str, Sequence[str], None] = "006_balance_precision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "text_project_characters",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.Column("profile", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["text_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_text_project_characters_project_id",
        "text_project_characters",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_text_project_characters_project_order",
        "text_project_characters",
        ["project_id", "order_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_text_project_characters_project_order", table_name="text_project_characters")
    op.drop_index("ix_text_project_characters_project_id", table_name="text_project_characters")
    op.drop_table("text_project_characters")
