import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership, get_current_user, require_org_admin
from app.db.session import get_db
from app.models import (
    Organization,
    OrganizationInvite,
    OrganizationMember,
    Profile,
    User,
)
from app.schemas.organizations import (
    InviteAccept,
    InviteCreate,
    InviteOut,
    MemberOut,
    MemberProfileOut,
    MembersResponse,
    MyOrganizationOut,
    OrganizationCreate,
    OrganizationOut,
    OrganizationSettings,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])

INVITE_EXPIRY_DAYS = 7


@router.post("", response_model=MyOrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyOrganizationOut:
    existing = db.scalar(select(Organization).where(Organization.slug == payload.slug))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "An organization with this name already exists. "
                "Please choose a different name."
            ),
        )

    # Organization + admin membership in one transaction (the original had to
    # manually roll back the org insert if the membership insert failed).
    org = Organization(name=payload.name, slug=payload.slug)
    db.add(org)
    db.flush()
    db.add(
        OrganizationMember(organization_id=org.id, user_id=user.id, role="admin")
    )
    db.commit()

    return MyOrganizationOut(
        **OrganizationOut.model_validate(org).model_dump(), role="admin"
    )


@router.get("/me", response_model=MyOrganizationOut)
def get_my_organization(
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> MyOrganizationOut:
    org = db.get(Organization, membership.organization_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )
    return MyOrganizationOut(
        **OrganizationOut.model_validate(org).model_dump(), role=membership.role
    )


@router.get("/me/settings", response_model=OrganizationSettings)
def get_settings(
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> OrganizationSettings:
    org = db.get(Organization, membership.organization_id)
    return OrganizationSettings(**(org.settings or {}))


@router.patch("/me/settings", response_model=OrganizationSettings)
def update_settings(
    payload: OrganizationSettings,
    membership: OrganizationMember = Depends(require_org_admin),
    db: Session = Depends(get_db),
) -> OrganizationSettings:
    org = db.get(Organization, membership.organization_id)
    org.settings = payload.model_dump()
    db.commit()
    return payload


@router.get("/me/members", response_model=MembersResponse)
def get_members(
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> MembersResponse:
    members = db.scalars(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == membership.organization_id)
        .order_by(OrganizationMember.created_at.asc())
    ).all()

    profiles = {
        p.id: p
        for p in db.scalars(
            select(Profile).where(Profile.id.in_([m.user_id for m in members]))
        )
    }

    invites = db.scalars(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.organization_id == membership.organization_id,
            OrganizationInvite.accepted_at.is_(None),
        )
        .order_by(OrganizationInvite.created_at.desc())
    ).all()

    member_out = [
        MemberOut(
            id=m.id,
            organization_id=m.organization_id,
            user_id=m.user_id,
            role=m.role,
            created_at=m.created_at,
            profiles=(
                MemberProfileOut.model_validate(profiles[m.user_id])
                if m.user_id in profiles
                else None
            ),
        )
        for m in members
    ]
    return MembersResponse(
        members=member_out,
        invites=[InviteOut.model_validate(i) for i in invites],
    )


@router.post(
    "/me/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED
)
def create_invite(
    payload: InviteCreate,
    membership: OrganizationMember = Depends(require_org_admin),
    db: Session = Depends(get_db),
) -> InviteOut:
    email = payload.email.lower()
    org_id = membership.organization_id

    # Already a member?
    existing_profile = db.scalar(select(Profile).where(Profile.email == email))
    if existing_profile is not None:
        existing_member = db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == existing_profile.id,
            )
        )
        if existing_member is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this organization.",
            )

    # Pending invite already exists?
    existing_invite = db.scalar(
        select(OrganizationInvite).where(
            OrganizationInvite.organization_id == org_id,
            OrganizationInvite.email == email,
            OrganizationInvite.accepted_at.is_(None),
        )
    )
    if existing_invite is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invitation has already been sent to this email.",
        )

    invite = OrganizationInvite(
        organization_id=org_id,
        email=email,
        role=payload.role,
        invited_by=membership.user_id,
        token=secrets.token_hex(32),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    db.commit()

    # NOTE: No invitation email is sent — invites are tracked in the DB only.
    return InviteOut.model_validate(invite)


@router.delete("/me/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_invite(
    invite_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_org_admin),
    db: Session = Depends(get_db),
) -> None:
    invite = db.scalar(
        select(OrganizationInvite).where(
            OrganizationInvite.id == invite_id,
            OrganizationInvite.organization_id == membership.organization_id,
        )
    )
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found"
        )
    db.delete(invite)
    db.commit()


@router.post("/invites/accept", response_model=MyOrganizationOut)
def accept_invite(
    payload: InviteAccept,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyOrganizationOut:
    invite = db.scalar(
        select(OrganizationInvite).where(
            OrganizationInvite.token == payload.token,
            OrganizationInvite.accepted_at.is_(None),
        )
    )
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired invite."
        )

    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="This invite has expired."
        )

    profile = db.get(Profile, user.id)
    if profile is None or profile.email != invite.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invite was sent to a different email address.",
        )

    db.add(
        OrganizationMember(
            organization_id=invite.organization_id,
            user_id=user.id,
            role=invite.role,
        )
    )
    invite.accepted_at = datetime.now(timezone.utc)
    db.commit()

    org = db.get(Organization, invite.organization_id)
    return MyOrganizationOut(
        **OrganizationOut.model_validate(org).model_dump(), role=invite.role
    )
