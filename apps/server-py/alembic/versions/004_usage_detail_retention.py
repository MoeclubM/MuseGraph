"""usage detail columns and retention config

Revision ID: 004
Revises: 003
Create Date: 2026-06-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usages", sa.Column("provider", sa.String(100), nullable=True))
    op.add_column("usages", sa.Column("billing_mode", sa.String(20), nullable=True))
    op.add_column("usages", sa.Column("request_id", sa.String(128), nullable=True))
    op.add_column("usages", sa.Column("status", sa.String(32), server_default="SUCCESS", nullable=False))
    op.add_column("usages", sa.Column("source", sa.String(32), server_default="llm", nullable=False))
    op.add_column("usages", sa.Column("metadata", postgresql.JSON, nullable=True))

    op.create_index("ix_usages_user_id_created_at", "usages", ["user_id", "created_at"])
    op.create_index("ix_usages_model", "usages", ["model"])
    op.create_index("ix_usages_created_at", "usages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_usages_created_at", table_name="usages")
    op.drop_index("ix_usages_model", table_name="usages")
    op.drop_index("ix_usages_user_id_created_at", table_name="usages")
    op.drop_column("usages", "metadata")
    op.drop_column("usages", "source")
    op.drop_column("usages", "status")
    op.drop_column("usages", "request_id")
    op.drop_column("usages", "billing_mode")
    op.drop_column("usages", "provider")