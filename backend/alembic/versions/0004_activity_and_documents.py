"""request activity log and stored documents

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-22

- Replaces the narrow ``status_history`` table with a general
  ``request_activity`` audit log (creation, field edits, status and approval
  changes).
- Adds ``request_documents`` to store the original uploaded PDF per request.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    # status_history -> request_activity
    op.drop_index("ix_status_history_request_id", table_name="status_history")
    op.drop_table("status_history")

    op.create_table(
        "request_activity",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"], ["procurement_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_request_activity_request_id", "request_activity", ["request_id"]
    )

    op.create_table(
        "request_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column(
            "content_type",
            sa.String(),
            nullable=False,
            server_default=sa.text("'application/pdf'"),
        ),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"], ["procurement_requests.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("request_id", name="uq_request_document_request"),
    )
    op.create_index(
        "ix_request_documents_request_id", "request_documents", ["request_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_request_documents_request_id", table_name="request_documents")
    op.drop_table("request_documents")

    op.drop_index("ix_request_activity_request_id", table_name="request_activity")
    op.drop_table("request_activity")

    op.create_table(
        "status_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("old_status", sa.Text(), nullable=True),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"], ["procurement_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_status_history_request_id", "status_history", ["request_id"])
