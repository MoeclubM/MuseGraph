"""add project chapters

Revision ID: 004_add_project_chapters
Revises: 003_add_project_oasis_and_component_models
Create Date: 2026-03-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_add_project_chapters"
down_revision: Union[str, Sequence[str], None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "text_project_chapters",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Main Draft"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["text_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_text_project_chapters_project_id", "text_project_chapters", ["project_id"], unique=False)
    op.create_index(
        "ix_text_project_chapters_project_order",
        "text_project_chapters",
        ["project_id", "order_index"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO text_project_chapters (id, project_id, title, content, order_index, created_at, updated_at)
        SELECT
            gen_random_uuid()::text,
            tp.id,
            'Main Draft',
            '',
            0,
            COALESCE(tp.created_at, now()),
            COALESCE(tp.updated_at, now())
        FROM text_projects tp
        WHERE NOT EXISTS (
            SELECT 1 FROM text_project_chapters c WHERE c.project_id = tp.id
        )
        """
    )

    op.drop_column("text_projects", "content")

    op.alter_column("text_project_chapters", "title", server_default=None)
    op.alter_column("text_project_chapters", "content", server_default=None)
    op.alter_column("text_project_chapters", "order_index", server_default=None)


def downgrade() -> None:
    op.add_column("text_projects", sa.Column("content", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE text_projects tp
        SET content = sub.content
        FROM (
            SELECT DISTINCT ON (project_id)
                project_id,
                content
            FROM text_project_chapters
            ORDER BY project_id, order_index ASC, created_at ASC
        ) AS sub
        WHERE tp.id = sub.project_id
        """
    )

    op.drop_index("ix_text_project_chapters_project_order", table_name="text_project_chapters")
    op.drop_index("ix_text_project_chapters_project_id", table_name="text_project_chapters")
    op.drop_table("text_project_chapters")
