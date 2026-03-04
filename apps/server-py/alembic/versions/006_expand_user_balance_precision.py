"""expand user balance precision to 6 decimals

Revision ID: 006_balance_precision
Revises: 005_legacy_cleanup
Create Date: 2026-03-04 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_balance_precision"
down_revision: Union[str, Sequence[str], None] = "005_legacy_cleanup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "balance",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Numeric(12, 6),
        existing_nullable=False,
        postgresql_using="balance::numeric(12,6)",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "balance",
        existing_type=sa.Numeric(12, 6),
        type_=sa.Numeric(10, 4),
        existing_nullable=False,
        postgresql_using="balance::numeric(10,4)",
    )
