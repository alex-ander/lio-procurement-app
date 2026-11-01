"""add per-organization settings

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-22

Adds a JSONB ``settings`` column to ``organizations`` for per-tenant
configuration. Additive and backfilled with ``{}`` — existing rows are
preserved.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "settings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "settings")
