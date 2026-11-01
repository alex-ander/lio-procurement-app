import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin

# JSONB on Postgres, plain JSON on SQLite (used by the test suite).
_JSON = JSONB().with_variant(JSON(), "sqlite")


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # Per-organization configuration (multi-tenant settings). Free-form JSON;
    # validated at the API edge by the OrganizationSettings schema.
    settings: Mapped[dict] = mapped_column(
        _JSON, nullable=False, default=dict, server_default=text("'{}'")
    )

    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    invites: Mapped[list["OrganizationInvite"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationMember(Base, TimestampMixin):
    """Membership with a procurement role.

    - ``requester`` — can create and track requests
    - ``buyer`` — can additionally approve requests
    - ``admin`` — can additionally manage members, invites, and settings
    """

    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
        CheckConstraint(
            "role IN ('admin', 'buyer', 'requester')", name="ck_org_member_role"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="members")


class OrganizationInvite(Base, CreatedAtMixin):
    __tablename__ = "organization_invites"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_org_invite_email"),
        CheckConstraint(
            "role IN ('admin', 'buyer', 'requester')", name="ck_org_invite_role"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organization: Mapped["Organization"] = relationship(back_populates="invites")
