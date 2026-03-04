import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TextProject(Base):
    __tablename__ = "text_projects"
    __table_args__ = (Index("ix_text_projects_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    simulation_requirement: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    component_models: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ontology_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    oasis_analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    cognee_dataset_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="projects")
    operations: Mapped[list["TextOperation"]] = relationship("TextOperation", back_populates="project", cascade="all, delete-orphan")
    chapters: Mapped[list["ProjectChapter"]] = relationship(
        "ProjectChapter",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectChapter.order_index",
    )


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
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["TextProject"] = relationship("TextProject", back_populates="chapters")


class TextOperation(Base):
    __tablename__ = "text_operations"
    __table_args__ = (
        Index("ix_text_operations_project_id", "project_id"),
        Index("ix_text_operations_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # CREATE / CONTINUE / ANALYZE / REWRITE / SUMMARIZE
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
