"""add project facts and persistent agent sessions

Revision ID: 002
Revises: 001
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(40), server_default="orchestrator", nullable=False),
        sa.Column("parent_session_id", sa.String(64), sa.ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("root_session_id", sa.String(64), nullable=True),
        sa.Column("parent_step_id", sa.String(64), nullable=True),
        sa.Column("model", sa.String(100), server_default="", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("workspace", postgresql.JSON, nullable=True),
        sa.Column("plan", postgresql.JSON, nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'partial')", name="ck_agent_sessions_status"),
    )
    op.create_index("ix_agent_sessions_project_updated", "agent_sessions", ["project_id", "updated_at"])
    op.create_index("ix_agent_sessions_project_archived_updated", "agent_sessions", ["project_id", "archived_at", "updated_at"])
    op.create_index("ix_agent_sessions_root", "agent_sessions", ["root_session_id"])
    op.create_index("ix_agent_sessions_parent", "agent_sessions", ["parent_session_id"])

    op.create_table(
        "project_facts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_agent_session_id", sa.String(64), sa.ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_kind", sa.String(40), server_default="manual", nullable=False),
        sa.Column("source_ref", postgresql.JSON, nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("metadata", postgresql.JSON, nullable=True),
        sa.Column("ontology_snapshot", postgresql.JSON, nullable=True),
        sa.Column("entities", postgresql.JSON, nullable=True),
        sa.Column("relationships", postgresql.JSON, nullable=True),
        sa.Column("content_hash", sa.String(64), server_default="", nullable=False),
        sa.Column("memory_status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("memory_task_id", sa.String(64), nullable=True),
        sa.Column("memory_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("memory_status IN ('pending', 'syncing', 'ready', 'failed', 'deleted')", name="ck_project_facts_memory_status"),
    )
    op.create_index("ix_project_facts_project_updated", "project_facts", ["project_id", "updated_at"])
    op.create_index("ix_project_facts_memory_task_id", "project_facts", ["memory_task_id"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("metadata", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_messages_session_created", "agent_messages", ["session_id", "created_at"])

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("child_session_id", sa.String(64), sa.ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("step_index", sa.Integer(), nullable=True),
        sa.Column("total_steps", sa.Integer(), nullable=True),
        sa.Column("step_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("message", sa.Text(), server_default="", nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("output_preview", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSON, nullable=True),
        sa.Column("agent_role", sa.String(40), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("tool_args", postgresql.JSON, nullable=True),
        sa.Column("tool_result_preview", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_steps_session_created", "agent_steps", ["session_id", "created_at"])
    op.create_index("ix_agent_steps_child_session", "agent_steps", ["child_session_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_steps_child_session", table_name="agent_steps")
    op.drop_index("ix_agent_steps_session_created", table_name="agent_steps")
    op.drop_table("agent_steps")
    op.drop_index("ix_agent_messages_session_created", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("ix_project_facts_memory_task_id", table_name="project_facts")
    op.drop_index("ix_project_facts_project_updated", table_name="project_facts")
    op.drop_table("project_facts")
    op.drop_index("ix_agent_sessions_project_archived_updated", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_parent", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_root", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_project_updated", table_name="agent_sessions")
    op.drop_table("agent_sessions")
