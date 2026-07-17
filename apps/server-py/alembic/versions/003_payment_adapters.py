"""payment adapters and order binding

Revision ID: 003
Revises: 002
Create Date: 2026-06-12

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_adapters",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("adapter_type", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("config", postgresql.JSON, nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_payment_adapters_type_enabled", "payment_adapters", ["adapter_type", "enabled"])

    op.add_column(
        "orders",
        sa.Column("payment_adapter_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_payment_adapter_id",
        "orders",
        "payment_adapters",
        ["payment_adapter_id"],
        ["id"],
        ondelete="SET NULL",
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT name, config, is_active FROM payment_configs WHERE type = 'epay'")
    ).fetchall()
    for row in rows:
        cfg = row.config if isinstance(row.config, dict) else {}
        conn.execute(
            sa.text(
                """
                INSERT INTO payment_adapters (id, adapter_type, display_name, config, enabled, sort_order)
                VALUES (gen_random_uuid(), 'epay', :display_name, CAST(:config AS jsonb), :enabled, 0)
                """
            ),
            {
                "display_name": str(row.name or "EPay"),
                "config": json.dumps(cfg),
                "enabled": bool(row.is_active),
            },
        )

    conn.execute(sa.text("DELETE FROM payment_configs WHERE type = 'epay'"))


def downgrade() -> None:
    op.drop_constraint("fk_orders_payment_adapter_id", "orders", type_="foreignkey")
    op.drop_column("orders", "payment_adapter_id")
    op.drop_index("ix_payment_adapters_type_enabled", table_name="payment_adapters")
    op.drop_table("payment_adapters")