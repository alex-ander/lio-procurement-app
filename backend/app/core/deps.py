import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import OrganizationMember, User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the Bearer token (port of ``requireAuth``)."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized - Please sign in",
        )

    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject"
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    return user


def get_current_membership(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationMember:
    """The current user's organization membership. 403 if they have none.

    Port of the ``organization_members`` lookup every server action performed.
    """
    membership = db.scalar(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not part of any organization",
        )
    return membership


def require_org_admin(
    membership: OrganizationMember = Depends(get_current_membership),
) -> OrganizationMember:
    """Admin role required (member/invite management, organization settings)."""
    if membership.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
    return membership


def require_buyer_or_admin(
    membership: OrganizationMember = Depends(get_current_membership),
) -> OrganizationMember:
    """Buyer or admin role required (approving procurement requests)."""
    if membership.role not in ("buyer", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only buyers and admins can approve requests.",
        )
    return membership
