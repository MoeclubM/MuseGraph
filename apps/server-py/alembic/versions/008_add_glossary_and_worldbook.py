"""add glossary terms and worldbook entries

Revision ID: 008_glossary_worldbook
Revises: 007_project_characters
Create Date: 2026-03-05 00:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008_glossary_worldbook"
down_revision: Union[str, Sequence[str], None] = "007_project_characters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "text_project_glossary_terms",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False, server_default=""),
        sa.Column("aliases", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["text_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_text_project_glossary_terms_project_id",
        "text_project_glossary_terms",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_text_project_glossary_terms_project_order",
        "text_project_glossary_terms",
        ["project_id", "order_index"],
        unique=False,
    )

    op.create_table(
        "text_project_worldbook_entries",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["text_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_text_project_worldbook_entries_project_id",
        "text_project_worldbook_entries",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_text_project_worldbook_entries_project_order",
        "text_project_worldbook_entries",
        ["project_id", "order_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_text_project_worldbook_entries_project_order", table_name="text_project_worldbook_entries")
    op.drop_index("ix_text_project_worldbook_entries_project_id", table_name="text_project_worldbook_entries")
    op.drop_table("text_project_worldbook_entries")

    op.drop_index("ix_text_project_glossary_terms_project_order", table_name="text_project_glossary_terms")
    op.drop_index("ix_text_project_glossary_terms_project_id", table_name="text_project_glossary_terms")
    op.drop_table("text_project_glossary_terms")
