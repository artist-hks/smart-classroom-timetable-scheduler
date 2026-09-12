from __future__ import annotations

import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.auth import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=150)
    role: UserRole
    # Required for every role except SYSTEM_ADMIN — validated in the
    # endpoint (see app/api/auth.py) against ck_users_department_scope's
    # same rule, so the API rejects bad input before it ever reaches the DB.
    department_id: int | None = None


class UserOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    role: UserRole
    department_id: int | None
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenOnly(BaseModel):
    access_token: str
    token_type: str = "bearer"
