import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin


class ProcurementRequest(Base, TimestampMixin):
    __tablename__ = "procurement_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'closed')",
            name="ck_procurement_request_status",
        ),
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="ck_procurement_request_approval_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Request details
    requestor_name: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    vendor_name: Mapped[str] = mapped_column(Text, nullable=False)
    vat_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    commodity_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("commodity_groups.id"), nullable=True, index=True
    )
    department: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", index=True)

    # Approval: every request needs sign-off by a buyer or admin.
    approval_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", index=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Financial
    total_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Multi-tenancy (added in migration 003, nullable for backward compatibility)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    order_lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="OrderLine.line_order",
    )
    commodity_group: Mapped["CommodityGroup | None"] = relationship()


class OrderLine(Base, CreatedAtMixin):
    __tablename__ = "order_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("procurement_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    position_description: Mapped[str] = mapped_column(Text, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # NUMERIC(12, 4) since migration 004 — supports decimal quantities (e.g. 1.28 m).
    amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    line_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    request: Mapped["ProcurementRequest"] = relationship(back_populates="order_lines")


class RequestActivity(Base, CreatedAtMixin):
    """Append-only audit trail: creation, field edits, status & approval changes."""

    __tablename__ = "request_activity"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("procurement_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class RequestDocument(Base, CreatedAtMixin):
    """The original uploaded PDF for a request (stored in the DB, one per request)."""

    __tablename__ = "request_documents"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_request_document_request"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("procurement_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String, nullable=False, default="application/pdf"
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


# Imported for the type-only forward reference in relationships above.
from app.models.commodity_group import CommodityGroup  # noqa: E402,F401
