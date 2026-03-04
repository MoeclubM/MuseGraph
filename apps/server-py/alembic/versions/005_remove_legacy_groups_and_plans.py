"""remove legacy permission-group and plan schema

Revision ID: 005_legacy_cleanup
Revises: 004_add_project_chapters
Create Date: 2026-03-03 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_legacy_cleanup"
down_revision: Union[str, Sequence[str], None] = "004_add_project_chapters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 旧权限组/套餐体系全部移除，不保留向前兼容结构。
    op.execute("DROP TABLE IF EXISTS subscriptions CASCADE")
    op.execute("DROP TABLE IF EXISTS plans CASCADE")
    op.execute("DROP TABLE IF EXISTS model_group_bindings CASCADE")
    op.execute("DROP TABLE IF EXISTS user_groups CASCADE")

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS group_id")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS plan_id")


def downgrade() -> None:
    raise RuntimeError("Irreversible migration: legacy groups/plans schema was permanently removed.")
