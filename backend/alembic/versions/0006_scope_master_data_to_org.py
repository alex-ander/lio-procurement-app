"""scope master data to organization

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-23

Master data (suppliers and articles) belongs to a single organization rather
than being shared across all tenants. Adds a non-null ``organization_id`` to
both tables. Migrations run before the (schema-only) tables are seeded, so the
tables are empty when the non-null column is added — reset the database
(``docker compose down -v``) if upgrading one that already holds seed data.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "suppliers", sa.Column("organization_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "fk_suppliers_organization_id",
        "suppliers",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_suppliers_organization_id", "suppliers", ["organization_id"]
    )

    op.add_column(
        "articles", sa.Column("organization_id", sa.Uuid(), nullable=False)
    )
    op.create_foreign_key(
        "fk_articles_organization_id",
        "articles",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_articles_organization_id", "articles", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_articles_organization_id", table_name="articles")
    op.drop_constraint("fk_articles_organization_id", "articles", type_="foreignkey")
    op.drop_column("articles", "organization_id")

    op.drop_index("ix_suppliers_organization_id", table_name="suppliers")
    op.drop_constraint("fk_suppliers_organization_id", "suppliers", type_="foreignkey")
    op.drop_column("suppliers", "organization_id")
