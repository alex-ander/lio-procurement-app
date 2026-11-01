"""article catalog

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-23

Adds the ``articles`` table: a reference catalog of purchasable articles, each
tied to a supplier. Reference rows are loaded by the idempotent seed step
(``app.seed``), not by this migration.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("article_number", sa.Text(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(), server_default=sa.text("'USD'"), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), server_default="1", nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_articles_article_number", "articles", ["article_number"])
    op.create_index("ix_articles_supplier_id", "articles", ["supplier_id"])


def downgrade() -> None:
    op.drop_index("ix_articles_supplier_id", table_name="articles")
    op.drop_index("ix_articles_article_number", table_name="articles")
    op.drop_table("articles")
