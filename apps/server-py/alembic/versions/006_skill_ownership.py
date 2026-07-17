"""skill ownership

Revision ID: 006
Revises: 005
Create Date: 2026-06-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prompt_skills",
        sa.Column(
            "owner_project_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_prompt_skills_owner_project",
        "prompt_skills",
        "text_projects",
        ["owner_project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Drop the global UNIQUE(slug) created in 005 so the same slug can co-exist
    # under different owner_project_id values.
    op.drop_constraint("prompt_skills_slug_key", "prompt_skills", type_="unique")
    # Two partial unique indexes keep slug uniqueness within each ownership scope.
    op.create_index(
        "ux_prompt_skills_global_slug",
        "prompt_skills",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("owner_project_id IS NULL"),
    )
    op.create_index(
        "ux_prompt_skills_project_slug",
        "prompt_skills",
        ["slug", "owner_project_id"],
        unique=True,
        postgresql_where=sa.text("owner_project_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_prompt_skills_project_slug", table_name="prompt_skills")
    op.drop_index("ux_prompt_skills_global_slug", table_name="prompt_skills")
    op.create_unique_constraint(
        "prompt_skills_slug_key", "prompt_skills", ["slug"]
    )
    op.drop_constraint(
        "fk_prompt_skills_owner_project", "prompt_skills", type_="foreignkey"
    )
    op.drop_column("prompt_skills", "owner_project_id")
