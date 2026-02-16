"""add project component model configs and oasis analysis fields

Revision ID: 003
Revises: 002
Create Date: 2026-02-16

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "text_projects",
        sa.Column("simulation_requirement", sa.Text(), nullable=True),
    )
    op.add_column(
        "text_projects",
        sa.Column("component_models", postgresql.JSON(), nullable=True),
    )
    op.add_column(
        "text_projects",
        sa.Column("oasis_analysis", postgresql.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("text_projects", "oasis_analysis")
    op.drop_column("text_projects", "component_models")
    op.drop_column("text_projects", "simulation_requirement")
