"""Shared helpers for the /api/v1 CRUD routers."""

from __future__ import annotations

import datetime
from typing import Any, TypeVar

from fastapi import HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.models.auth import UserRole
from app.api.deps import require_roles

T = TypeVar("T")

# Role gates reused by every router.
admin_only = require_roles(UserRole.SYSTEM_ADMIN)
admin_or_coordinator = require_roles(UserRole.SYSTEM_ADMIN, UserRole.COORDINATOR)


class Pagination:
    def __init__(
        self,
        limit: int = Query(100, ge=1, le=500, description="Max rows to return"),
        offset: int = Query(0, ge=0, description="Rows to skip"),
    ):
        self.limit = limit
        self.offset = offset


def get_or_404(db: DBSession, model: type[T], pk: Any, label: str) -> T:
    obj = db.get(model, pk)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return obj


def require_exists(db: DBSession, model: type, pk: Any, label: str) -> Any:
    """For foreign keys supplied in a request body: 422 (not 404) when missing."""
    obj = db.get(model, pk)
    if obj is None:
        raise HTTPException(
            422,
            detail=f"{label} {pk} does not exist",
        )
    return obj


def commit_or_409(db: DBSession, conflict_detail: str) -> None:
    """Commit; turn unique/FK violations into a clean 409 instead of a 500."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=conflict_detail)


def apply_updates(obj: Any, data: dict[str, Any], nullable: set[str] | None = None) -> None:
    """Apply a PATCH-style dict (from model_dump(exclude_unset=True)).

    An explicit null for a NOT NULL column is a client error (422), not a DB 500.
    """
    nullable = nullable or set()
    for key, value in data.items():
        if value is None and key not in nullable:
            raise HTTPException(
                422,
                detail=f"'{key}' cannot be null",
            )
        setattr(obj, key, value)


def times_overlap(
    a_start: datetime.time, a_end: datetime.time, b_start: datetime.time, b_end: datetime.time
) -> bool:
    return a_start < b_end and b_start < a_end
