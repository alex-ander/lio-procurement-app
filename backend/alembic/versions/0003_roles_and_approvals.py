"""procurement roles and request approvals

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-22

- Replaces the generic membership roles (owner/admin/member) with procurement
  roles: admin / buyer / requester. Existing rows are remapped
  (owner -> admin, member -> requester); no data is lost.
- Adds approval tracking to procurement requests: every request starts
  ``pending`` and is approved or rejected by a buyer or admin.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- membership roles ---
    op.drop_constraint("ck_org_member_role", "organization_members", type_="check")
    op.execute("UPDATE organization_members SET role = 'admin' WHERE role = 'owner'")
    op.execute(
        "UPDATE organization_members SET role = 'requester' WHERE role = 'member'"
    )
    op.create_check_constraint(
        "ck_org_member_role",
        "organization_members",
        "role IN ('admin', 'buyer', 'requester')",
    )

    # --- invite roles ---
    op.drop_constraint("ck_org_invite_role", "organization_invites", type_="check")
    op.execute(
        "UPDATE organization_invites SET role = 'requester' WHERE role = 'member'"
    )
    op.create_check_constraint(
        "ck_org_invite_role",
        "organization_invites",
        "role IN ('admin', 'buyer', 'requester')",
    )

    # --- request approvals ---
    op.add_column(
        "procurement_requests",
        sa.Column(
            "approval_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        "procurement_requests",
        sa.Column("approved_by", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "procurement_requests",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_procurement_requests_approved_by",
        "procurement_requests",
        "users",
        ["approved_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_procurement_request_approval_status",
        "procurement_requests",
        "approval_status IN ('pending', 'approved', 'rejected')",
    )
    op.create_index(
        "ix_procurement_requests_approval_status",
        "procurement_requests",
        ["approval_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_procurement_requests_approval_status", table_name="procurement_requests"
    )
    op.drop_constraint(
        "ck_procurement_request_approval_status",
        "procurement_requests",
        type_="check",
    )
    op.drop_constraint(
        "fk_procurement_requests_approved_by",
        "procurement_requests",
        type_="foreignkey",
    )
    op.drop_column("procurement_requests", "approved_at")
    op.drop_column("procurement_requests", "approved_by")
    op.drop_column("procurement_requests", "approval_status")

    op.drop_constraint("ck_org_invite_role", "organization_invites", type_="check")
    op.create_check_constraint(
        "ck_org_invite_role", "organization_invites", "role IN ('admin', 'member')"
    )

    op.drop_constraint("ck_org_member_role", "organization_members", type_="check")
    op.execute("UPDATE organization_members SET role = 'member' WHERE role IN ('requester', 'buyer')")
    op.create_check_constraint(
        "ck_org_member_role",
        "organization_members",
        "role IN ('owner', 'admin', 'member')",
    )
