"""auto-approve pending requests below threshold

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-01

Auto-approves any existing ``pending`` procurement requests whose ``total_cost``
is strictly below the default $2,000 approval threshold so buyers do not have
to sign off on sub-$2,000 requests.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE procurement_requests
        SET approval_status = 'approved',
            approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP)
        WHERE approval_status = 'pending'
          AND total_cost IS NOT NULL
          AND total_cost < 2000
        """
    )


def downgrade() -> None:
    pass
