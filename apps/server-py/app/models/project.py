import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TextProject(Base):
    __tablename__ = "text_projects"
    __table_args__ = (
        CheckConstraint("visibility IN ('private', 'public')", name="ck_text_projects_visibility"),
        Index("ix_text_projects_user_id", "user_id"),
        Index("ix_text_projects_visibility_updated", "visibility", "updated_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="private")
    component_models: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    operation_prompts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ontology_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    creative_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    memory_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="projects")
    members: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    operations: Mapped[list["TextOperation"]] = relationship("TextOperation", back_populates="project", cascade="all, delete-orphan")
    chapters: Mapped[list["ProjectChapter"]] = relationship(
        "ProjectChapter",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectChapter.order_index",
    )
    facts: Mapped[list["ProjectFact"]] = relationship(
        "ProjectFact",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectFact.updated_at.desc()",
    )
    agent_sessions: Mapped[list["AgentSession"]] = relationship(
        "AgentSession",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="ck_project_members_role"),
        Index("ix_project_members_project_id", "project_id"),
        Index("ix_project_members_user_id", "user_id"),
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("text_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["TextProject"] = relationship("TextProject", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="project_members")


class ProjectChapter(Base):
    __tablename__ = "text_project_chapters"
    __table_args__ = (
        Index("ix_text_project_chapters_project_id", "project_id"),
        Index("ix_text_project_chapters_project_order", "project_id", "order_index"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("text_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Main Draft")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    blueprint: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    continuity_notes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["TextProject"] = relationship("TextProject", back_populates="chapters")


class ProjectFact(Base):
    __tablename__ = "project_facts"
    __table_args__ = (
        CheckConstraint("memory_status IN ('pending', 'syncing', 'ready', 'failed', 'deleted')", name="ck_project_facts_memory_status"),
        Index("ix_project_facts_project_updated", "project_id", "updated_at"),
        Index("ix_project_facts_memory_task_id", "memory_task_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("text_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_agent_session_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("agent_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    source_ref: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    ontology_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    entities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    relationships: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    memory_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    memory_task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    memory_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["TextProject"] = relationship("TextProject", back_populates="facts")
    created_by_agent_session: Mapped[Optional["AgentSession"]] = relationship(
        "AgentSession",
        foreign_keys=[created_by_agent_session_id],
    )


class TextOperation(Base):
    __tablename__ = "text_operations"
    __table_args__ = (
        Index("ix_text_operations_project_id", "project_id"),
        Index("ix_text_operations_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING / PROCESSING / COMPLETED / FAILED
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["TextProject"] = relationship("TextProject", back_populates="operations")

class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'partial')", name="ck_agent_sessions_status"),
        Index("ix_agent_sessions_project_updated", "project_id", "updated_at"),
        Index("ix_agent_sessions_project_archived_updated", "project_id", "archived_at", "updated_at"),
        Index("ix_agent_sessions_root", "root_session_id"),
        Index("ix_agent_sessions_parent", "parent_session_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="orchestrator")
    parent_session_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True)
    root_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    parent_step_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    workspace: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["TextProject"] = relationship("TextProject", back_populates="agent_sessions")
    parent: Mapped[Optional["AgentSession"]] = relationship("AgentSession", remote_side=[id], back_populates="children")
    children: Mapped[list["AgentSession"]] = relationship("AgentSession", back_populates="parent")
    messages: Mapped[list["AgentMessage"]] = relationship(
        "AgentMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentMessage.created_at",
    )
    steps: Mapped[list["AgentStep"]] = relationship(
        "AgentStep",
        foreign_keys="AgentStep.session_id",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentStep.created_at",
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        Index("ix_agent_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["AgentSession"] = relationship("AgentSession", back_populates="messages")


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        Index("ix_agent_steps_session_created", "session_id", "created_at"),
        Index("ix_agent_steps_child_session", "child_session_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    child_session_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True)
    step_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    agent_role: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tool_args: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tool_result_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    session: Mapped["AgentSession"] = relationship(
        "AgentSession",
        foreign_keys=[session_id],
        back_populates="steps",
    )
    child_session: Mapped[Optional["AgentSession"]] = relationship(
        "AgentSession",
        foreign_keys=[child_session_id],
    )
