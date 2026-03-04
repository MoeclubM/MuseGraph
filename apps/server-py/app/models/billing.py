import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Usage(Base):
    __tablename__ = "usages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    operation_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Deposit(Base):
    __tablename__ = "deposits"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING / COMPLETED / FAILED / REFUNDED
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    order_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # RECHARGE
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING / PAID / CANCELLED / REFUNDED / EXPIRED
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
