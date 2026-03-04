import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SimulationRuntime(Base):
    __tablename__ = "simulation_runtimes"
    __table_args__ = (
        Index("ix_simulation_runtimes_project_id", "project_id"),
        Index("ix_simulation_runtimes_user_id", "user_id"),
        Index("ix_simulation_runtimes_status", "status"),
        Index("ix_simulation_runtimes_simulation_id", "simulation_id", unique=True),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    simulation_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    profiles: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    run_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    actions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    posts: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    comments: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    interview_history: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    env_status: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReportRuntime(Base):
    __tablename__ = "report_runtimes"
    __table_args__ = (
        Index("ix_report_runtimes_project_id", "project_id"),
        Index("ix_report_runtimes_user_id", "user_id"),
        Index("ix_report_runtimes_simulation_id", "simulation_id"),
        Index("ix_report_runtimes_status", "status"),
        Index("ix_report_runtimes_report_id", "report_id", unique=True),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    simulation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("text_projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    markdown_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    sections: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    chat_history: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    agent_log: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    console_log: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
