from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import Profile, User
from app.schemas.auth import (
    MeResponse,
    ProfileOut,
    SignInRequest,
    SignUpRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def sign_up(payload: SignUpRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()

    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # User + profile in one transaction (replaces the Supabase
    # ``handle_new_user`` trigger).
    user = User(email=email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.flush()
    db.add(Profile(id=user.id, email=email, full_name=payload.full_name))
    db.commit()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        user=UserOut.model_validate(user),
    )


@router.post("/signin", response_model=TokenResponse)
def sign_in(payload: SignInRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    profile = db.get(Profile, user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        )
    return MeResponse(
        user=UserOut.model_validate(user),
        profile=ProfileOut.model_validate(profile),
    )
