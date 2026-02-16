"""add ontology schema to text_projects

Revision ID: 002
Revises: 001
Create Date: 2026-02-16

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "text_projects",
        sa.Column("ontology_schema", postgresql.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("text_projects", "ontology_schema")

