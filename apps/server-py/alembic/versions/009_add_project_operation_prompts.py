"""add project operation prompts

Revision ID: 009_project_operation_prompts
Revises: 008_glossary_worldbook
Create Date: 2026-04-30 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009_project_operation_prompts"
down_revision: Union[str, Sequence[str], None] = "008_glossary_worldbook"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "text_projects",
        sa.Column("operation_prompts", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("text_projects", "operation_prompts")
