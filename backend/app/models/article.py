import uuid

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin


class Article(Base, CreatedAtMixin):
    """Reference catalog of purchasable articles, each tied to a supplier."""

    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    article_number: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=1)

    supplier: Mapped["Supplier"] = relationship()


# Imported for the type-only forward reference in the relationship above.
from app.models.supplier import Supplier  # noqa: E402,F401
