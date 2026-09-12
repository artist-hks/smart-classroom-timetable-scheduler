"""
Auth dependencies — SB2/US7/T1.

Three layers, used together on protected endpoints:

1. get_current_user       — decodes the JWT, loads the User row, rejects
                             expired/invalid/inactive-user tokens (401).
2. require_roles(...)     — RBAC gate: 403s if the caller's role isn't in
                             the allowed set for this endpoint.
3. DepartmentScope /
   enforce_department_scope — NFR-3's "department-level access isolation."
                             SYSTEM_ADMIN sees everything; everyone else is
                             restricted to their own department_id, both
                             for filtering list queries and for rejecting
                             direct access to another department's rows.

Usage pattern for a protected, department-scoped endpoint:

    @router.get("/sections")
    def list_sections(
        scope: int | None = Depends(department_scope),
        db: Session = Depends(get_db),
    ):
        query = db.query(Section)
        if scope is not None:          # None == SYSTEM_ADMIN, no filter
            query = query.filter(Section.department_id == scope)
        return query.all()

    @router.get("/sections/{section_id}")
    def get_section(
        section_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        section = db.get(Section, section_id)
        if section is None:
            raise HTTPException(404)
        enforce_department_scope(current_user, section.department_id)
        return section
"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session as DBSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.auth import User, UserRole

# tokenUrl is just what shows up in the OpenAPI "Authorize" dialog — the
# actual endpoint is wired up in app/api/auth.py.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: DBSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_error

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_error

    if payload.get("type") != "access":
        # Rejects someone passing a refresh token as an Authorization
        # bearer token to a normal protected endpoint.
        raise credentials_error

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    user = db.get(User, int(user_id))
    if user is None:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    return user


def require_roles(*allowed_roles: UserRole):
    """
    Dependency factory — e.g. Depends(require_roles(UserRole.SYSTEM_ADMIN))
    or Depends(require_roles(UserRole.SYSTEM_ADMIN, UserRole.COORDINATOR)).
    """

    def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not permitted to perform this action",
            )
        return current_user

    return _check


def enforce_department_scope(current_user: User, resource_department_id: int) -> None:
    """
    Raises 403 unless current_user is SYSTEM_ADMIN or belongs to the same
    department as the resource. Use this for single-resource
    read/write/delete endpoints (see docstring example above).
    """
    if current_user.role == UserRole.SYSTEM_ADMIN:
        return
    if current_user.department_id != resource_department_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this department's data",
        )


def department_scope(current_user: User = Depends(get_current_user)) -> int | None:
    """
    Use this for LIST endpoints. Returns None for SYSTEM_ADMIN (meaning:
    apply no department filter — see all departments), otherwise returns
    the caller's department_id to filter the query by.
    """
    if current_user.role == UserRole.SYSTEM_ADMIN:
        return None
    return current_user.department_id
