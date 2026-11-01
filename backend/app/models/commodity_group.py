from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class CommodityGroup(Base, CreatedAtMixin):
    """Reference data: the 50 fixed procurement commodity groups."""

    __tablename__ = "commodity_groups"

    # IDs are fixed (1-50) reference values, not auto-generated.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
