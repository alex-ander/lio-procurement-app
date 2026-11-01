import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str | None = None


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None = None
    department: str | None = None
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MeResponse(BaseModel):
    user: UserOut
    profile: ProfileOut
