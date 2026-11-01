import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """Authentication record. Replaces Supabase's ``auth.users`` table."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)

    profile: Mapped["Profile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Profile(Base, TimestampMixin):
    """Application-facing profile data, 1:1 with :class:`User`."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="profile")
