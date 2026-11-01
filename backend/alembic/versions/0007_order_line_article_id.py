"""link order lines to catalog articles

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-01

Adds a nullable ``article_id`` foreign key on ``order_lines`` referencing
``articles.id`` (``ON DELETE SET NULL``) so procurement request lines can be
linked to negotiated catalog articles.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "order_lines", sa.Column("article_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_order_lines_article_id",
        "order_lines",
        "articles",
        ["article_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_order_lines_article_id", "order_lines", ["article_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_order_lines_article_id", table_name="order_lines")
    op.drop_constraint(
        "fk_order_lines_article_id", "order_lines", type_="foreignkey"
    )
    op.drop_column("order_lines", "article_id")
