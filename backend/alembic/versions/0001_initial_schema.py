"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-22

Schema only. Reference data (commodity groups, suppliers) is loaded by the
idempotent seed step (``app.seed``), not by migrations.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("email", name="uq_profiles_email"),
    )

    op.create_table(
        "commodity_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
    )

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    op.create_table(
        "organization_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member')", name="ck_org_member_role"
        ),
    )
    op.create_index(
        "ix_organization_members_organization_id",
        "organization_members",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_members_user_id", "organization_members", ["user_id"]
    )

    op.create_table(
        "organization_invites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("accepted_at", TIMESTAMP, nullable=True),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "email", name="uq_org_invite_email"),
        sa.UniqueConstraint("token", name="uq_org_invite_token"),
        sa.CheckConstraint("role IN ('admin', 'member')", name="ck_org_invite_role"),
    )
    op.create_index(
        "ix_organization_invites_organization_id",
        "organization_invites",
        ["organization_id"],
    )
    op.create_index("ix_organization_invites_email", "organization_invites", ["email"])
    op.create_index("ix_organization_invites_token", "organization_invites", ["token"])

    op.create_table(
        "procurement_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("requestor_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("vendor_name", sa.Text(), nullable=False),
        sa.Column("vat_id", sa.Text(), nullable=True),
        sa.Column("commodity_group_id", sa.Integer(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(), server_default=sa.text("'open'"), nullable=False
        ),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["commodity_group_id"], ["commodity_groups.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'closed')",
            name="ck_procurement_request_status",
        ),
    )
    op.create_index(
        "ix_procurement_requests_user_id", "procurement_requests", ["user_id"]
    )
    op.create_index(
        "ix_procurement_requests_status", "procurement_requests", ["status"]
    )
    op.create_index(
        "ix_procurement_requests_commodity_group_id",
        "procurement_requests",
        ["commodity_group_id"],
    )
    op.create_index(
        "ix_procurement_requests_organization_id",
        "procurement_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_procurement_requests_created_by", "procurement_requests", ["created_by"]
    )
    op.create_index(
        "ix_procurement_requests_created_at",
        "procurement_requests",
        [sa.text("created_at DESC")],
    )

    op.create_table(
        "order_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("position_description", sa.Text(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"], ["procurement_requests.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_order_lines_request_id", "order_lines", ["request_id"])

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

    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("vat_id", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP, server_default=NOW, nullable=False),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])


def downgrade() -> None:
    op.drop_table("suppliers")
    op.drop_table("status_history")
    op.drop_table("order_lines")
    op.drop_table("procurement_requests")
    op.drop_table("organization_invites")
    op.drop_table("organization_members")
    op.drop_table("organizations")
    op.drop_table("commodity_groups")
    op.drop_table("profiles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
