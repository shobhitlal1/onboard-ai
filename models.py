"""The entire relational model: clients, documents, and workflow events."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint("status IN ('INCOMPLETE', 'READY_FOR_REVIEW')"),
        CheckConstraint("expected_monthly_volume IS NULL OR expected_monthly_volume >= 0"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    account_type: Mapped[str] = mapped_column(String(50))
    state: Mapped[str | None] = mapped_column(String(100))
    expected_monthly_volume: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="INCOMPLETE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    documents: Mapped[list["Document"]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="Document.id"
    )
    events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="WorkflowEvent.id"
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("client_id", "document_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(50))
    received: Mapped[bool] = mapped_column(Boolean, default=False)
    client: Mapped[Client] = relationship(back_populates="documents")


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    client: Mapped[Client] = relationship(back_populates="events")
