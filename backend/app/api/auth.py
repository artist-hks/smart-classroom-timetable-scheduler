from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user, require_roles
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.db.session import get_db
from app.models.academic import Department
from app.models.auth import User, UserRole
from app.schemas.auth import (
    AccessTokenOnly,
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: DBSession = Depends(get_db)) -> TokenPair:
    user = db.scalar(select(User).where(User.email == payload.email))

    # Deliberately identical error for "no such user" and "wrong password"
    # — distinguishing them lets an attacker enumerate valid emails.
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
    )
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise invalid
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )

    claims = {"role": user.role.value}
    access_token = create_token(subject=str(user.user_id), token_type="access", extra_claims=claims)
    refresh_token = create_token(subject=str(user.user_id), token_type="refresh")
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AccessTokenOnly)
def refresh(payload: RefreshRequest, db: DBSession = Depends(get_db)) -> AccessTokenOnly:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
    )
    try:
        decoded = decode_token(payload.refresh_token)
    except Exception:
        raise invalid

    if decoded.get("type") != "refresh":
        raise invalid

    user_id = decoded.get("sub")
    user = db.get(User, int(user_id)) if user_id else None
    if user is None or not user.is_active:
        raise invalid

    new_access_token = create_token(
        subject=str(user.user_id), token_type="access", extra_claims={"role": user.role.value}
    )
    return AccessTokenOnly(access_token=new_access_token)


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.SYSTEM_ADMIN))],
)
def register_user(payload: UserCreate, db: DBSession = Depends(get_db)) -> User:
    """
    System-Administrator-only (§2.4: "Create/manage users", "Assign roles").
    The very first admin can't be created through this endpoint — that's a
    chicken-and-egg problem solved by app/scripts/create_admin.py instead.
    """
    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists"
        )

    # Mirrors ck_users_department_scope at the API layer so the client gets
    # a clean 422 instead of a raw DB constraint-violation 500.
    if payload.role == UserRole.SYSTEM_ADMIN and payload.department_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="SYSTEM_ADMIN users must not have a department_id",
        )
    if payload.role != UserRole.SYSTEM_ADMIN:
        if payload.department_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="department_id is required for this role",
            )
        if db.get(Department, payload.department_id) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="department_id does not reference an existing department",
            )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        department_id=payload.department_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
